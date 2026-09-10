"""Yahoo byte adapter. No discovery imports or inferred calendar dates."""

import csv
import io
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

PARSER_VERSION = "yahoo-csv/1"
HEADER = (
    "ID,First Name,Last Name,Position,Team,Opponent,Game,Time,Salary,FPPG," "Injury Status,Starting"
).split(",")
TEAMS = set(
    (
        "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAC KC LA LAC LV "
        "MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS"
    ).split()
)
SLOTS = {
    "QB": ["QB"],
    "RB1": ["RB"],
    "RB2": ["RB"],
    "WR1": ["WR"],
    "WR2": ["WR"],
    "WR3": ["WR"],
    "TE": ["TE"],
    "FLEX": ["RB", "WR", "TE"],
    "DEF": ["DEF"],
}


def parse_yahoo(raw: bytes, games: list[dict]) -> dict:
    """Keep every physical record, quarantining every row of a conflicted ID."""
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("CSV exceeds 10 MiB")
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Expected a UTF-8 Yahoo CSV") from exc
    if "\x00" in source:
        raise ValueError("CSV contains NUL bytes")
    reader = csv.reader(io.StringIO(source, newline=""), strict=True)
    rows: list[dict] = []
    schedule = {g["away"] + "@" + g["home"]: g for g in games}
    if len(schedule) != len(games):
        raise ValueError("Ambiguous rematch: this adapter needs one dated game per pairing")
    try:
        if next(reader, None) != HEADER:
            raise ValueError("Unsupported schema. Expected: " + ", ".join(HEADER))
        while True:
            start = reader.line_num + 1
            values = next(reader, None)
            if values is None:
                break
            if len(rows) >= 5000:
                raise ValueError("CSV exceeds 5,000 records")
            if len(values) != len(HEADER):
                raise ValueError(f"Physical line {start}: expected 12 fields, got {len(values)}")
            original = dict(zip(HEADER, values, strict=True))
            v = {k: value.strip() for k, value in original.items()}
            issues: list[str] = []
            if not re.fullmatch(r"nfl\.[pt]\.\d+", v["ID"]):
                issues.append("Invalid Yahoo ID")
            if v["Position"] not in {"QB", "RB", "WR", "TE", "DEF"}:
                issues.append("Unsupported position")
            if v["Position"] == "DEF" and not v["ID"].startswith("nfl.t."):
                issues.append("Defense requires a team identifier")
            if v["Position"] != "DEF" and not v["ID"].startswith("nfl.p."):
                issues.append("Athlete requires a player identifier")
            if not v["Last Name"]:
                issues.append("Missing name")
            salary = None
            try:
                d = Decimal(v["Salary"])
                if not d.is_finite() or d != d.to_integral_value() or not 0 <= d <= 1_000_000:
                    raise InvalidOperation
                salary = int(d * 100)
            except InvalidOperation:
                issues.append("Salary must be an exact whole dollar amount")
            if v["FPPG"]:
                try:
                    if not Decimal(v["FPPG"]).is_finite():
                        raise InvalidOperation
                except InvalidOperation:
                    issues.append("Invalid historical FPPG")
            pair = v["Game"].split("@")
            if (
                len(pair) != 2
                or set(pair) != {v["Team"], v["Opponent"]}
                or v["Team"] == v["Opponent"]
                or not set(pair) <= TEAMS
            ):
                issues.append("Team/opponent/game conflict")
            game = schedule.get(v["Game"])
            if not game:
                issues.append("Game is outside the confirmed dated slate")
            elif not game.get("kickoff"):
                issues.append("Unknown required kickoff")
            else:
                clock = re.fullmatch(r"(\d{1,2}):(\d{2})(AM|PM) (EDT|EST|CDT|CST|UTC)", v["Time"])
                if not clock:
                    issues.append("Unsupported clock/timezone")
                else:
                    hour, minute, meridiem, zone = clock.groups()
                    iana = {
                        "EDT": "America/New_York",
                        "EST": "America/New_York",
                        "CDT": "America/Chicago",
                        "CST": "America/Chicago",
                        "UTC": "UTC",
                    }[zone]
                    kickoff = datetime.fromisoformat(str(game["kickoff"]).replace("Z", "+00:00"))
                    local = kickoff.astimezone(ZoneInfo(iana))
                    expected_hour = int(hour) % 12 + (12 if meridiem == "PM" else 0)
                    if (
                        not 1 <= int(hour) <= 12
                        or local.tzname() != zone
                        or not 0 <= int(minute) <= 59
                        or (local.hour, local.minute) != (expected_hour, int(minute))
                    ):
                        issues.append("CSV clock conflicts with dated schedule")
            rows.append(
                {
                    "line": start,
                    "line_end": reader.line_num,
                    "raw": original,
                    "yahoo_id": v["ID"],
                    "name": (v["First Name"] + " " + v["Last Name"]).strip(),
                    "position": v["Position"],
                    "team": v["Team"],
                    "opponent": v["Opponent"],
                    "game_id": game["id"] if game else None,
                    "game": v["Game"],
                    "salary_cents": salary,
                    "historical_fppg": v["FPPG"] or None,
                    "injury": v["Injury Status"] or None,
                    "starting": v["Starting"] or None,
                    "issues": issues,
                }
            )
    except csv.Error as exc:
        raise ValueError(f"Malformed CSV near physical line {reader.line_num}: {exc}") from exc
    if not rows:
        raise ValueError("CSV has no player records")
    counts = Counter(r["yahoo_id"] for r in rows)
    bad_ids = {r["yahoo_id"] for r in rows if r["issues"]}
    for row in rows:
        if counts[row["yahoo_id"]] > 1:
            row["issues"].append("Duplicate Yahoo ID: all records quarantined")
        elif row["yahoo_id"] in bad_ids and not row["issues"]:
            row["issues"].append("Another record for this ID conflicts")
    quarantined = [r for r in rows if r["issues"]]
    return {
        "rows": rows,
        "summary": {
            "records": len(rows),
            "unique_ids": len(counts),
            "teams": len({r["team"] for r in rows}),
            "games": len({r["game"] for r in rows}),
            "quarantined_rows": len(quarantined),
            "quarantined_ids": len({r["yahoo_id"] for r in quarantined}),
            "eligible_ids": len({r["yahoo_id"] for r in rows if not r["issues"]}),
        },
    }
