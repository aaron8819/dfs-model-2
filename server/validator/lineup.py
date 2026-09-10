"""Checks canonical facts directly. No optimizer imports or prefiltered pool dependency."""

from collections import Counter
from math import floor, isfinite
from time import perf_counter

from server.recommendation.contracts import (
    ELIGIBILITY,
    SLOTS,
    Assignment,
    SolveInput,
    SolveResult,
    exact_units,
    input_hash,
    validate_input,
)


def lineup_facts(data: SolveInput, assignments: tuple[Assignment, ...]) -> dict[str, object]:
    validate_input(data)
    entries = {e.key: e for e in data.entries}
    if len(assignments) != 9 or {a.slot for a in assignments} != set(SLOTS):
        raise ValueError("exactly the nine actual slots required")
    members = {a.entry for a in assignments}
    if len(members) != 9 or not members <= entries.keys():
        raise ValueError("duplicate or unknown result entry")
    actual = {a.slot: a.entry for a in assignments}
    fixed = {a.entry for a in data.fixed}
    if any(actual[a.slot] != a.entry for a in data.fixed):
        raise ValueError("fixed slot changed")
    if not set(data.required + data.keep + data.include) <= members:
        raise ValueError("required member absent")
    if members & (set(data.avoid) - fixed) or members & (set(data.exclude) - fixed):
        raise ValueError("excluded proposed member")
    salary = 0
    teams: Counter[str] = Counter()
    editable = known = 0
    missing = []
    for a in assignments:
        e = entries[a.entry]
        if e.game not in data.slate_games or e.quarantined:
            raise ValueError("outside slate or disputed canonical facts")
        if not set(e.positions) & set(ELIGIBILITY[a.slot]):
            raise ValueError("ineligible actual slot")
        if e.key not in fixed and (not e.available or e.locked or e.projection is None):
            raise ValueError("proposed member unavailable, locked or missing projection")
        salary += e.salary_cents
        teams[e.team] += 1
        if e.projection is None:
            missing.append(e.key)
        else:
            units = exact_units(e.projection)
            known += units
            if e.key not in fixed:
                editable += units
    if salary > data.rules.salary_cap_cents:
        raise ValueError("salary cap exceeded")
    if len(teams) < data.rules.min_teams or max(teams.values()) > data.rules.max_per_team:
        raise ValueError("team rules violated")
    return {
        "salary_cents": salary,
        "editable_units": editable,
        "known_total_units": known,
        "whole_total_units": None if missing else known,
        "missing_fixed": tuple(sorted(missing)),
    }


def validate_result(data: SolveInput, result: SolveResult) -> float:
    start = perf_counter()
    if result.input_hash != input_hash(data):
        raise ValueError("result belongs to another input")
    if any(s.proven != (s.status == "OPTIMAL") for s in result.stages):
        raise ValueError("inconsistent stage proof")
    if not result.assignments:
        if result.status in ("OPTIMAL", "FEASIBLE") or result.primary_proven or result.tie_complete:
            raise ValueError("solution status without roster")
        if (
            any(
                getattr(result, key) is not None
                for key in (
                    "editable_units",
                    "known_total_units",
                    "whole_total_units",
                    "salary_cents",
                )
            )
            or result.missing_fixed
        ):
            raise ValueError("totals without roster")
        if result.status == "INFEASIBLE" and (
            not result.stages
            or result.stages[0].name != "points"
            or result.stages[0].status != "INFEASIBLE"
        ):
            raise ValueError("infeasibility lacks primary solver evidence")
        return perf_counter() - start
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        raise ValueError("roster with non-solution status")
    facts = lineup_facts(data, result.assignments)
    if any(getattr(result, key) != value for key, value in facts.items()):
        raise ValueError("canonical recomputed totals differ")
    if result.primary_proven != (result.status == "OPTIMAL"):
        raise ValueError("inconsistent primary status")
    if not result.stages or result.stages[0].name != "points":
        raise ValueError("missing primary solver evidence")
    primary = result.stages[0]
    if primary.proven != result.primary_proven or primary.status != result.status:
        raise ValueError("primary proof disagrees with result")
    if primary.objective != result.editable_units:
        raise ValueError("primary objective differs from recomputation")
    # Only the points stage uses the exact 1/10000-point integer lattice. No
    # fractional-objective or later-stage proof may inherit this flooring rule.
    if primary.best_bound is not None and (
        not isfinite(primary.best_bound) or primary.best_bound < result.editable_units
    ):
        raise ValueError("invalid maximization upper bound")
    if primary.proven and (
        primary.best_bound is None or floor(primary.best_bound) != result.editable_units
    ):
        raise ValueError("proven primary bound differs")
    if result.tie_complete:
        expected = (
            ["points", "retained"]
            + [f"entry_{i}" for i in range(9)]
            + ["preserved_slots", "slot_order"]
        )
        if not result.primary_proven or [s.name for s in result.stages] != expected:
            raise ValueError("incomplete tie evidence")
        if not all(s.proven for s in result.stages):
            raise ValueError("unproven canonical tie stage")
        members = {a.entry for a in result.assignments}
        working = {a.slot: a.entry for a in data.working}
        fixed_slots = {a.slot for a in data.fixed}
        ranks = {e.key: i for i, e in enumerate(sorted(data.entries, key=lambda e: e.key))}
        if result.stages[1].objective != len(members & set(working.values())):
            raise ValueError("retained-members objective differs")
        if [s.objective for s in result.stages[2:11]] != [ranks[k] for k in sorted(members)]:
            raise ValueError("entry-rank objectives differ")
        preserved = sum(
            working.get(a.slot) == a.entry for a in result.assignments if a.slot not in fixed_slots
        )
        if result.stages[11].objective != preserved:
            raise ValueError("preserved-slot objective differs")
    return perf_counter() - start
