import pytest

from server.recommendation.contracts import Assignment, Rules
from server.recommendation.solver import solve
from server.recommendation.solver_test import changed, tiny
from server.validator.lineup import lineup_facts


def test_integer_objective_uses_integer_maximization_bound():
    from math import inf, nextafter

    from server.validator.lineup import validate_result

    data = tiny()
    result = solve(data)
    primary = result.stages[0]
    for bound, valid in [
        (nextafter(float(primary.objective), inf), True),
        (float(primary.objective) + 0.75, True),
        (float(primary.objective) + 1, False),
        (nextafter(float(primary.objective), -inf), False),
    ]:
        altered = result.model_copy(
            update={
                "stages": (primary.model_copy(update={"best_bound": bound}), *result.stages[1:])
            }
        )
        if valid:
            validate_result(data, altered)
        else:
            with pytest.raises(ValueError):
                validate_result(data, altered)


@pytest.mark.parametrize(
    "fault",
    [
        "unknown",
        "duplicate",
        "fixed",
        "required",
        "avoid",
        "exclude",
        "salary",
        "teams",
        "slot",
        "slate",
        "quarantine",
        "unavailable",
        "locked",
        "missing",
    ],
)
def test_validator_rejects_independently(fault: str) -> None:
    data = tiny()
    assignments = solve(data).assignments
    selected = next(a for a in assignments if a.slot == "QB")
    if fault == "unknown":
        assignments = (Assignment(slot="QB", entry="unknown"),) + assignments[1:]
    elif fault == "duplicate":
        assignments = (Assignment(slot="QB", entry=assignments[1].entry),) + assignments[1:]
    elif fault == "fixed":
        data = data.model_copy(update={"fixed": (Assignment(slot="QB", entry="e10"),)})
    elif fault == "required":
        data = data.model_copy(update={"required": ("e10",)})
    elif fault in ("avoid", "exclude"):
        data = data.model_copy(update={fault: (selected.entry,)})
    elif fault == "salary":
        data = data.model_copy(update={"rules": Rules(salary_cap_cents=899)})
    elif fault == "teams":
        data = data.model_copy(update={"rules": Rules(min_teams=4)})
    elif fault == "slot":
        a, b = assignments[:2]
        assignments = (
            Assignment(slot=a.slot, entry=b.entry),
            Assignment(slot=b.slot, entry=a.entry),
        ) + assignments[2:]
    else:
        updates = {
            "slate": {"game": "outside"},
            "quarantine": {"quarantined": True},
            "unavailable": {"available": False},
            "locked": {"locked": True},
            "missing": {"projection": None},
        }
        data = changed(data, selected.entry, **updates[fault])
    with pytest.raises(ValueError):
        lineup_facts(data, assignments)
