"""Fresh actual-slot CP-SAT model with separate, exact lexicographic passes."""

from collections.abc import Callable
from time import perf_counter

import ortools
from ortools.sat.python import cp_model

from server.recommendation.contracts import (
    ELIGIBILITY,
    SLOTS,
    Assignment,
    SolveInput,
    SolveResult,
    Stage,
    Status,
    exact_units,
    input_hash,
    validate_input,
)
from server.validator.lineup import lineup_facts, validate_result


def map_status(status: cp_model.CpSolverStatus) -> Status:
    return {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "INVALID",
    }.get(status, "INVALID")


def canonical_slots(
    data: SolveInput, members: set[str], deadline: float
) -> tuple[tuple[Assignment, ...], int]:
    """At most 9! exact matchings; maximize preserved slots then minimize slot vector."""
    entries = {e.key: e for e in data.entries}
    fixed = {a.slot: a.entry for a in data.fixed}
    working = {a.slot: a.entry for a in data.working if a.slot not in fixed}
    best: tuple[int, tuple[str, ...]] | None = None

    def visit(vector: tuple[str, ...], unused: set[str], preserved: int) -> None:
        nonlocal best
        if perf_counter() >= deadline:
            raise TimeoutError("slot enumeration exhausted shared budget")
        if len(vector) == 9:
            score = (-preserved, vector)
            if best is None or score < best:
                best = score
            return
        slot = SLOTS[len(vector)]
        for key in sorted(unused):
            if slot in fixed and key != fixed[slot]:
                continue
            if not set(entries[key].positions) & set(ELIGIBILITY[slot]):
                continue
            visit(vector + (key,), unused - {key}, preserved + (working.get(slot) == key))

    visit((), members, 0)
    if best is None:
        raise ValueError("selected membership has no legal slot assignment")
    return tuple(Assignment(slot=s, entry=k) for s, k in zip(SLOTS, best[1])), -best[0]


def solve(
    data: SolveInput,
    budget_seconds: float = 30.0,
    publish: Callable[[SolveResult], None] | None = None,
) -> SolveResult:
    start = perf_counter()
    deadline = start + budget_seconds
    validate_input(data)
    model = cp_model.CpModel()
    entries = sorted(data.entries, key=lambda e: e.key)
    fixed = {a.entry for a in data.fixed}
    required = set(data.required + data.keep + data.include)
    excluded = set(data.avoid + data.exclude) - fixed
    y = {e.key: model.new_bool_var("member_" + e.key) for e in entries}
    x = {
        (e.key, slot): model.new_bool_var(e.key + "_" + slot)
        for e in entries
        for slot in SLOTS
        if set(e.positions) & set(ELIGIBILITY[slot])
    }
    for slot in SLOTS:
        model.add(sum(v for (key, s), v in x.items() if s == slot) == 1)
    for e in entries:
        model.add(sum(x[e.key, s] for s in SLOTS if (e.key, s) in x) == y[e.key])
        blocked = (
            e.quarantined
            or e.game not in data.slate_games
            or (
                e.key not in fixed
                and (not e.available or e.locked or e.projection is None or e.key in excluded)
            )
        )
        if blocked:
            model.add(y[e.key] == 0)
        if e.key in required:
            model.add(y[e.key] == 1)
    for assignment in data.fixed:
        model.add(x[assignment.entry, assignment.slot] == 1)
    model.add(sum(e.salary_cents * y[e.key] for e in entries) <= data.rules.salary_cap_cents)
    indicators = []
    for team in sorted({e.team for e in entries}):
        count = sum(y[e.key] for e in entries if e.team == team)
        indicator = model.new_bool_var("team_" + team)
        model.add(count >= indicator)
        model.add(count <= data.rules.max_per_team * indicator)
        indicators.append(indicator)
    model.add(sum(indicators) >= data.rules.min_teams)
    points = sum(
        exact_units(e.projection) * y[e.key]
        for e in entries
        if e.projection is not None and e.key not in fixed
    )
    engine = cp_model.CpSolver()
    engine.parameters.num_search_workers = 1
    engine.parameters.random_seed = 0
    engine.parameters.absolute_gap_limit = 0
    engine.parameters.relative_gap_limit = 0
    engine.parameters.linearization_level = 2
    stages: list[Stage] = []
    result = SolveResult(
        input_hash=input_hash(data),
        status="UNKNOWN",
        termination="budget",
        solver_version=ortools.__version__,
        model_variables=len(model.proto.variables),
        model_constraints=len(model.proto.constraints),
    )

    def emit(candidate: SolveResult) -> SolveResult:
        checked = candidate.model_copy(
            update={
                "stages": tuple(stages),
                "elapsed_seconds": perf_counter() - start,
                "model_variables": len(model.proto.variables),
                "model_constraints": len(model.proto.constraints),
            }
        )
        elapsed = validate_result(data, checked)
        checked = checked.model_copy(
            update={
                "validator_seconds": elapsed,
                "elapsed_seconds": perf_counter() - start,
            }
        )
        if publish:
            publish(checked)
        return checked

    def run_stage(name: str, objective: cp_model.LinearExpr | int, maximize: bool) -> Stage:
        remaining = deadline - perf_counter()
        if remaining <= 0:
            stage = Stage(name=name, status="UNKNOWN", proven=False, elapsed_seconds=0.0)
        else:
            if maximize:
                model.maximize(objective)
            else:
                model.minimize(objective)
            engine.parameters.max_time_in_seconds = remaining
            stage_start = perf_counter()
            status = map_status(engine.solve(model))
            has_solution = status in ("OPTIMAL", "FEASIBLE")
            stage = Stage(
                name=name,
                status=status,
                proven=status == "OPTIMAL",
                elapsed_seconds=perf_counter() - stage_start,
                objective=int(engine.value(objective)) if has_solution else None,
                best_bound=float(engine.best_objective_bound) if has_solution else None,
            )
        stages.append(stage)
        return stage

    primary = run_stage("points", points, True)
    if primary.status not in ("OPTIMAL", "FEASIBLE"):
        return emit(
            result.model_copy(
                update={
                    "status": primary.status,
                    "termination": (
                        "completed"
                        if primary.status == "INFEASIBLE"
                        else ("invalid" if primary.status == "INVALID" else "budget")
                    ),
                }
            )
        )
    assignments = tuple(
        Assignment(slot=slot, entry=key)
        for (key, slot), variable in x.items()
        if engine.value(variable)
    )
    result = emit(
        result.model_copy(
            update={
                "status": primary.status,
                "primary_proven": primary.proven,
                "assignments": assignments,
                **lineup_facts(data, assignments),
            }
        )
    )
    if not primary.proven:
        return result
    model.add(points == primary.objective)
    retained = sum(y[a.entry] for a in data.working)
    stage = run_stage("retained", retained, True)
    if not stage.proven:
        return emit(result)
    model.add(retained == stage.objective)
    # Each pass fixes the next smallest selected ASCII entry key. No epsilon weights.
    last = -1
    for rank in range(9):
        next_rank = model.new_int_var(0, 2 * len(entries), "rank_" + str(rank))
        model.add_min_equality(
            next_rank,
            [i + len(entries) * (1 - y[e.key]) for i, e in enumerate(entries) if i > last],
        )
        stage = run_stage(f"entry_{rank}", next_rank, False)
        if not stage.proven:
            return emit(result)
        chosen = stage.objective
        assert chosen is not None
        for i in range(last + 1, chosen):
            model.add(y[entries[i].key] == 0)
        model.add(y[entries[chosen].key] == 1)
        last = chosen
    members = {e.key for e in entries if engine.value(y[e.key])}
    slot_start = perf_counter()
    try:
        assignments, preserved = canonical_slots(data, members, deadline)
    except TimeoutError:
        stages.append(
            Stage(
                name="preserved_slots",
                status="UNKNOWN",
                proven=False,
                elapsed_seconds=perf_counter() - slot_start,
            )
        )
        return emit(result)
    stages.extend(
        [
            Stage(
                name="preserved_slots",
                status="OPTIMAL",
                proven=True,
                elapsed_seconds=perf_counter() - slot_start,
                objective=preserved,
            ),
            Stage(name="slot_order", status="OPTIMAL", proven=True, elapsed_seconds=0.0),
        ]
    )
    return emit(
        result.model_copy(
            update={
                "assignments": assignments,
                "tie_complete": True,
                "termination": "completed",
                **lineup_facts(data, assignments),
            }
        )
    )
