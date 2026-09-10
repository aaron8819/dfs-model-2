from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from server.ingestion import SLOTS, TEAMS

RULE_PROFILE = {
    "version": "yahoo-nfl-candidate/1",
    "salary_cap_cents": 20000,
    "slots": SLOTS,
    "min_teams": 3,
    "max_per_team": 6,
    "def_counts_as_team": True,
    "lock_policy": "game kickoff; fixed entered slots and monotonic established deadlines",
    "scoring": {
        "passing_yard": "0.04",
        "passing_td": "4",
        "interception_thrown": "-1",
        "rushing_yard": "0.1",
        "rushing_td": "6",
        "reception": "0.5",
        "receiving_yard": "0.1",
        "receiving_td": "6",
        "return_td": "6",
        "own_fumble_return_td": "6",
        "fumble_lost": "-2",
        "two_point_conversion": "2",
        "def_sack": "1",
        "def_safety": "2",
        "def_interception": "2",
        "def_fumble_recovery": "2",
        "def_blocked_kick": "2",
        "def_td": "6",
        "def_return_td": "6",
        "def_two_point_return": "2",
        "def_points_allowed": "0:10; 1–6:7; 7–13:4; 14–20:1; 21–27:0; 28–34:-1; 35+:-4",
        "points_allowed_basis": "Yahoo official fantasy points-allowed statistic",
    },
    "candidate_source": "Investigated Yahoo NFL profile; owner must confirm applicability",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GameInput(StrictModel):
    event_key: str = Field(min_length=1, max_length=150)
    away: str
    home: str
    kickoff: AwareDatetime | None

    @model_validator(mode="after")
    def teams(self) -> "GameInput":
        if self.away not in TEAMS or self.home not in TEAMS or self.away == self.home:
            raise ValueError("Use distinct supported Yahoo team codes")
        return self


class SetupInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    yahoo_id: str = Field(min_length=1, max_length=300)
    season: str = Field(min_length=1, max_length=100)
    round: str = Field(min_length=1, max_length=100)
    timezone: str = "America/Chicago"
    games: list[GameInput] = Field(min_length=1, max_length=16)
    confirmed: Literal[True]
    provenance: str = Field(min_length=5, max_length=2000)
    expected_revision: int | None = None
    membership_change_confirmed: bool = False

    @field_validator("timezone")
    @classmethod
    def zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError("Use an IANA display timezone") from exc
        return value

    @model_validator(mode="after")
    def unique_games(self) -> "SetupInput":
        if len({g.event_key for g in self.games}) != len(self.games):
            raise ValueError("Duplicate stable game key")
        teams = [t for g in self.games for t in (g.away, g.home)]
        if len(set(teams)) != len(teams):
            raise ValueError("A team may appear in only one game in this supported slate")
        return self


class Operation(StrictModel):
    op: Literal["add", "replace", "remove"]
    slot: str
    entry_id: str | None = None

    @field_validator("slot")
    @classmethod
    def slot_key(cls, value: str) -> str:
        if value not in SLOTS:
            raise ValueError("Invalid slot key")
        return value


class DraftCommand(StrictModel):
    expected_revision: int
    operations: list[Operation] = Field(min_length=1, max_length=100)


class Activation(StrictModel):
    expected_revision: int
    batch_id: str
    batch_revision: int
