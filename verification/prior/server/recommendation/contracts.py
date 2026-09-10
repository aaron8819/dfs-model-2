"""Version 1 offline snapshot contract; no provider or application configuration access."""

import hashlib
import json
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SLOTS = ("QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DEF")
ELIGIBILITY = {
    "QB": ("QB",),
    "RB1": ("RB",),
    "RB2": ("RB",),
    "WR1": ("WR",),
    "WR2": ("WR",),
    "WR3": ("WR",),
    "TE": ("TE",),
    "FLEX": ("RB", "WR", "TE"),
    "DEF": ("DEF",),
}
Status = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "INVALID"]


def exact_units(text: str, places: int = 4, maximum: int = 1_000_000) -> int:
    """Bounded lexical decimal parsing, independent of Decimal context and binary floats."""
    if not isinstance(text, str) or len(text) > 128:
        raise ValueError("decimal must be a bounded string")
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", text):
        raise ValueError("expected finite decimal notation")
    value = Decimal(text)
    sign, digits, exponent = value.as_tuple()
    coefficient = int("".join(map(str, digits)))
    shift = int(exponent) + places
    if shift < 0:
        divisor = 10**-shift
        if coefficient % divisor:
            raise ValueError("excess effective precision")
        units = coefficient // divisor
    else:
        units = coefficient * 10**shift
    if units > maximum * 10**places:
        raise ValueError("decimal exceeds supported bound")
    return -units if sign else units


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class Entry(Contract):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[\x21-\x7e]+$")
    team: str = Field(min_length=1, max_length=20)
    game: str = Field(min_length=1, max_length=100)
    positions: tuple[Literal["QB", "RB", "WR", "TE", "DEF"], ...]
    salary_cents: int = Field(ge=0, le=100_000_000)
    projection: str | None
    available: bool = True
    quarantined: bool = False
    locked: bool = False


class Assignment(Contract):
    slot: str
    entry: str


class Rules(Contract):
    profile: Literal["yahoo-nfl-v1"] = "yahoo-nfl-v1"
    salary_cap_cents: int = Field(default=20_000, ge=0, le=100_000_000)
    min_teams: int = Field(default=3, ge=1, le=9)
    max_per_team: int = Field(default=6, ge=1, le=9)


class SolveInput(Contract):
    version: Literal[1] = 1
    manifest: str = Field(min_length=1, max_length=200)
    evaluation_time: str = Field(min_length=1, max_length=100)
    lock_evidence: str = Field(min_length=1, max_length=200)
    entries: tuple[Entry, ...] = Field(max_length=5000)
    slate_games: tuple[str, ...]
    rules: Rules = Rules()
    fixed: tuple[Assignment, ...] = ()
    working: tuple[Assignment, ...] = ()
    required: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


class Stage(Contract):
    name: str
    status: Status
    proven: bool
    elapsed_seconds: float = Field(ge=0)
    objective: int | None = None
    best_bound: float | None = None


class SolveResult(Contract):
    version: Literal[1] = 1
    input_hash: str
    status: Status
    termination: Literal["completed", "budget", "interrupted", "unexpected_exit", "invalid"]
    primary_proven: bool = False
    tie_complete: bool = False
    assignments: tuple[Assignment, ...] = ()
    editable_units: int | None = None
    known_total_units: int | None = None
    whole_total_units: int | None = None
    missing_fixed: tuple[str, ...] = ()
    salary_cents: int | None = None
    stages: tuple[Stage, ...] = ()
    solver_version: str = "unstarted"
    solver_parameters: str = "one worker; seed=0; absolute/relative gap=0; linearization_level=2"
    validator_version: Literal[1] = 1
    validator_seconds: float = Field(default=0.0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0)
    peak_rss_bytes: int = Field(default=0, ge=0)
    model_variables: int = Field(default=0, ge=0)
    model_constraints: int = Field(default=0, ge=0)
    detail: str = ""


def input_hash(data: SolveInput) -> str:
    encoded = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def validate_input(data: SolveInput) -> None:
    entries = {entry.key: entry for entry in data.entries}
    if len(entries) != len(data.entries):
        raise ValueError("duplicate canonical entry key")
    if not data.slate_games or len(set(data.slate_games)) != len(data.slate_games):
        raise ValueError("empty or duplicate slate games")
    total_bound = 0
    for entry in data.entries:
        if not entry.positions or len(set(entry.positions)) != len(entry.positions):
            raise ValueError("invalid canonical eligibility")
        if entry.projection is not None:
            total_bound += abs(exact_units(entry.projection))
    if max(total_bound, sum(e.salary_cents for e in data.entries)) >= 2**63:
        raise ValueError("arithmetic aggregate exceeds signed 64-bit bounds")
    for assignments in (data.fixed, data.working):
        if len({a.slot for a in assignments}) != len(assignments):
            raise ValueError("duplicate input slot")
        if len({a.entry for a in assignments}) != len(assignments):
            raise ValueError("duplicate input assignment")
        if any(a.slot not in SLOTS or a.entry not in entries for a in assignments):
            raise ValueError("unresolved assignment")
    fixed = {a.entry for a in data.fixed}
    required = set(data.required + data.keep + data.include)
    excluded = set(data.avoid + data.exclude) - fixed
    for group in (data.required, data.keep, data.include, data.avoid, data.exclude):
        if len(set(group)) != len(group) or not set(group) <= entries.keys():
            raise ValueError("duplicate or unresolved constraint reference")
    if required & excluded:
        raise ValueError("explicit inclusion/exclusion conflict")
    for key in required - fixed:
        if entries[key].locked:
            raise ValueError("required player game started but player is not entered: " + key)
        if entries[key].projection is None:
            raise ValueError("required editable entry lacks projection: " + key)
    for a in data.fixed:
        e = entries[a.entry]
        if e.quarantined or e.game not in data.slate_games:
            raise ValueError("fixed canonical facts disputed or outside slate")
        if not set(e.positions) & set(ELIGIBILITY[a.slot]):
            raise ValueError("fixed actual slot is ineligible")
