"""Independent exhaustive oracle for tiny complete nine-slot instances."""

from itertools import combinations
from time import perf_counter

import pytest
from ortools.sat.python import cp_model

from server.recommendation import solver
from server.recommendation.contracts import (
    Assignment,
    Entry,
    Rules,
    SolveInput,
    SolveResult,
    exact_units,
    validate_input,
)
from server.validator.lineup import validate_result


def tiny() -> SolveInput:
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DEF", "RB", "QB"]
    return SolveInput(
        manifest="tiny-v1",
        evaluation_time="2026-01-01T00:00:00Z",
        lock_evidence="synthetic",
        slate_games=("game",),
        entries=tuple(
            Entry(
                key=f"e{i:02}",
                team=f"T{i % 3}",
                game="game",
                positions=(position,),
                salary_cents=100,
                projection="1.0000",
            )
            for i, position in enumerate(positions)
        ),
    )


def changed(data: SolveInput, key: str, **updates: object) -> SolveInput:
    return data.model_copy(
        update={
            "entries": tuple(
                e.model_copy(update=updates) if e.key == key else e for e in data.entries
            )
        }
    )


def oracle(data: SolveInput) -> tuple[Assignment, ...] | None:
    """Brute force subsets then independent slot matching, without CP model/validator helpers."""
    slots = ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DEF")
    permitted = (
        ("QB",),
        ("RB",),
        ("RB",),
        ("WR",),
        ("WR",),
        ("WR",),
        ("TE",),
        ("RB", "WR", "TE"),
        ("DEF",),
    )
    fixed = {a.slot: a.entry for a in data.fixed}
    fixed_ids = set(fixed.values())
    working = {a.slot: a.entry for a in data.working}
    best = None
    answer = None
    for subset in combinations(data.entries, 9):
        ids = {e.key for e in subset}
        if not fixed_ids | set(data.keep + data.required + data.include) <= ids:
            continue
        if (ids - fixed_ids) & set(data.exclude + data.avoid):
            continue
        if any(
            e.quarantined
            or e.game not in data.slate_games
            or (e.key not in fixed_ids and (not e.available or e.locked or e.projection is None))
            for e in subset
        ):
            continue
        if sum(e.salary_cents for e in subset) > data.rules.salary_cap_cents:
            continue
        teams = [e.team for e in subset]
        if len(set(teams)) < data.rules.min_teams:
            continue
        if max(teams.count(team) for team in teams) > data.rules.max_per_team:
            continue
        points = sum(
            exact_units(e.projection)
            for e in subset
            if e.key not in fixed_ids and e.projection is not None
        )
        prefix = (-points, -len(ids & set(working.values())), tuple(sorted(ids)))

        def assign(vector: tuple[str, ...]) -> None:
            nonlocal best, answer
            i = len(vector)
            if i == 9:
                preserved = sum(
                    working.get(s) == k for s, k in zip(slots, vector) if s not in fixed
                )
                score = (*prefix, -preserved, vector)
                if best is None or score < best:
                    best = score
                    answer = tuple(Assignment(slot=s, entry=k) for s, k in zip(slots, vector))
                return
            for entry in subset:
                if entry.key in vector or not set(entry.positions) & set(permitted[i]):
                    continue
                if slots[i] in fixed and fixed[slots[i]] != entry.key:
                    continue
                assign(vector + (entry.key,))

        assign(())
    return answer


@pytest.mark.parametrize(
    "scenario",
    [
        "four_wr",
        "precision",
        "negative_zero_missing",
        "team_min",
        "team_max",
        "fixed_slot",
        "fixed_unavailable_avoid",
        "fixed_missing",
        "retained",
        "preserved",
        "lex_slots",
        "infeasible",
        "required_unavailable",
        "locked",
        "quarantine",
        "slate",
        "temporary",
    ],
)
def test_exhaustive_contract(scenario: str) -> None:
    data = tiny()
    if scenario == "precision":
        data = changed(data, "e10", projection="1.0001")
    elif scenario == "negative_zero_missing":
        data = changed(
            changed(changed(data, "e00", projection="-1"), "e10", projection=None),
            "e03",
            projection="0",
        )
    elif scenario == "team_min":
        data = data.model_copy(update={"rules": Rules(min_teams=4)})
    elif scenario == "team_max":
        data = changed(data, "e00", team="T1").model_copy(update={"rules": Rules(max_per_team=3)})
    elif scenario == "fixed_slot":
        data = data.model_copy(update={"fixed": (Assignment(slot="FLEX", entry="e01"),)})
    elif scenario == "fixed_unavailable_avoid":
        data = changed(data, "e00", available=False, locked=True).model_copy(
            update={"fixed": (Assignment(slot="QB", entry="e00"),), "avoid": ("e00",)}
        )
    elif scenario == "fixed_missing":
        data = changed(data, "e00", projection=None).model_copy(
            update={"fixed": (Assignment(slot="QB", entry="e00"),)}
        )
    elif scenario == "retained":
        data = data.model_copy(update={"working": (Assignment(slot="QB", entry="e10"),)})
    elif scenario in ("preserved", "lex_slots"):
        data = data.model_copy(
            update={
                "working": (
                    Assignment(slot="WR1", entry="e05"),
                    Assignment(slot="RB1", entry="e02"),
                )
            }
        )
    elif scenario == "infeasible":
        data = data.model_copy(update={"keep": ("e00", "e10")})
    elif scenario == "required_unavailable":
        data = changed(data, "e00", available=False).model_copy(update={"required": ("e00",)})
    elif scenario == "locked":
        data = changed(data, "e00", locked=True)
    elif scenario == "quarantine":
        data = changed(data, "e00", quarantined=True)
    elif scenario == "slate":
        data = changed(data, "e00", game="outside")
    elif scenario == "temporary":
        data = data.model_copy(update={"include": ("e09",), "exclude": ("e00",)})
    expected = oracle(data)
    result = solver.solve(data)
    validate_result(data, result)
    if expected is None:
        assert result.status == "INFEASIBLE"
        assert not result.assignments and not result.primary_proven and not result.tie_complete
    else:
        assert result.assignments == expected
        assert result.primary_proven and result.tie_complete
        if scenario == "fixed_missing":
            assert result.missing_fixed == ("e00",) and result.whole_total_units is None
            assert result.editable_units == 80000
        if scenario == "precision":
            assert result.whole_total_units == 90001
        if scenario == "four_wr":
            assert next(a.entry for a in result.assignments if a.slot == "FLEX") == "e07"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.00010", 10001),
        ("-0.0001", -1),
        ("-0", 0),
        ("0.00000", 0),
        ("1000000", 10_000_000_000),
        (".25", 2500),
    ],
)
def test_exact_numbers(text: str, expected: int) -> None:
    assert exact_units(text) == expected


@pytest.mark.parametrize(
    "text", ["NaN", "Infinity", "1e2", "1.00001", "1000000.0001", "", " 1", "1,000", "1" * 129, 1.2]
)
def test_invalid_numbers(text: str) -> None:
    with pytest.raises(ValueError):
        exact_units(text)


@pytest.mark.parametrize("constraint", ["keep", "required", "include"])
def test_missing_required_blocks(constraint: str) -> None:
    data = changed(tiny(), "e00", projection=None).model_copy(update={constraint: ("e00",)})
    with pytest.raises(ValueError, match="lacks projection"):
        solver.solve(data)


def test_input_conflicts_and_roundtrip() -> None:
    data = tiny()
    assert SolveInput.model_validate_json(data.model_dump_json()) == data
    for update in (
        {"keep": ("e00",), "avoid": ("e00",)},
        {"exclude": ("missing",)},
    ):
        with pytest.raises(ValueError):
            validate_input(data.model_copy(update=update))
    with pytest.raises(ValueError):
        SolveInput.model_validate_json(data.model_dump_json().replace('"version":1', '"version":2'))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (cp_model.OPTIMAL, "OPTIMAL"),
        (cp_model.FEASIBLE, "FEASIBLE"),
        (cp_model.INFEASIBLE, "INFEASIBLE"),
        (cp_model.UNKNOWN, "UNKNOWN"),
        (cp_model.MODEL_INVALID, "INVALID"),
    ],
)
def test_status_mapping(raw: cp_model.CpSolverStatus, expected: str) -> None:
    assert solver.map_status(raw) == expected


def test_controlled_primary_feasible_and_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    original = solver.map_status
    monkeypatch.setattr(
        solver,
        "map_status",
        lambda status: ("FEASIBLE" if status == cp_model.OPTIMAL else original(status)),
    )
    result = solver.solve(tiny())
    assert result.status == "FEASIBLE" and not result.primary_proven and not result.tie_complete
    assert len(result.stages) == 1
    monkeypatch.setattr(solver, "map_status", lambda _: "UNKNOWN")
    result = solver.solve(tiny())
    assert result.status == "UNKNOWN" and not result.assignments
    monkeypatch.setattr(solver, "map_status", lambda _: "INVALID")
    assert solver.solve(tiny()).status == "INVALID"


def test_tie_interruption_keeps_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    original = solver.map_status
    calls = 0

    def controlled(status: cp_model.CpSolverStatus) -> str:
        nonlocal calls
        calls += 1
        return "UNKNOWN" if calls == 3 else original(status)

    monkeypatch.setattr(solver, "map_status", controlled)
    result = solver.solve(tiny())
    assert result.status == "OPTIMAL" and result.primary_proven and not result.tie_complete
    assert result.stages[-1].name == "entry_0" and not result.stages[-1].proven
    validate_result(tiny(), result)


def test_slot_budget_and_repeatability() -> None:
    data = tiny()
    results = [solver.solve(data) for _ in range(3)]
    assert all(r.assignments == results[0].assignments for r in results)
    with pytest.raises(TimeoutError):
        solver.canonical_slots(data, {a.entry for a in results[0].assignments}, perf_counter() - 1)
    with pytest.raises(ValueError):
        solver.canonical_slots(data, {"e00"}, perf_counter() + 1)


def test_retained_and_slot_stage_interruptions(monkeypatch: pytest.MonkeyPatch) -> None:
    original = solver.map_status
    calls = 0

    def interrupted(status: cp_model.CpSolverStatus) -> str:
        nonlocal calls
        calls += 1
        return "UNKNOWN" if calls == 2 else original(status)

    monkeypatch.setattr(solver, "map_status", interrupted)
    result = solver.solve(tiny())
    assert result.primary_proven and not result.tie_complete
    assert result.stages[-1].name == "retained"
    monkeypatch.setattr(solver, "map_status", original)

    def exhausted(*args: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(solver, "canonical_slots", exhausted)
    result = solver.solve(tiny())
    assert result.primary_proven and not result.tie_complete
    assert result.stages[-1].name == "preserved_slots"
    # Deterministic exhausted-budget path, no timing-sensitive expected CP status.
    assert solver.solve(tiny(), budget_seconds=0.0).status == "UNKNOWN"


def test_reject_malformed_result() -> None:
    data = tiny()
    result = solver.solve(data)
    for update in (
        {"editable_units": result.editable_units + 1},
        {"salary_cents": 0},
        {"assignments": result.assignments[:-1]},
        {"input_hash": "wrong"},
        {"primary_proven": False},
        {"stages": result.stages[:1]},
        {"status": "INFEASIBLE"},
        {"missing_fixed": ("e00",)},
    ):
        with pytest.raises(ValueError):
            validate_result(data, result.model_copy(update=update))
    with pytest.raises(ValueError):
        SolveResult.model_validate_json(
            result.model_dump_json().replace('"salary_cents":900', '"salary_cents":900.5')
        )
    primary = result.stages[0].model_copy(update={"best_bound": 0.0})
    with pytest.raises(ValueError, match="bound"):
        validate_result(data, result.model_copy(update={"stages": (primary,) + result.stages[1:]}))
