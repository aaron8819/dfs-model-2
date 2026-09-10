import csv
import io
import json
from pathlib import Path

import pytest

from server.ingestion import parse_yahoo
from tools.synthetic_demo import demo

HISTORICAL = Path("fixtures/private/historical")


def historical_games() -> list[dict]:
    return [
        {
            "id": g["espn_event_id"],
            "away": g["game"].split("@")[0],
            "home": g["game"].split("@")[1],
            "kickoff": g["kickoff_utc"],
        }
        for g in json.loads((HISTORICAL / "derived/games.json").read_text())
    ]


def test_historical_raw_contract() -> None:
    parsed = parse_yahoo((HISTORICAL / "raw/yahoo.csv").read_bytes(), historical_games())
    assert parsed["summary"] == {
        "records": 916,
        "unique_ids": 915,
        "teams": 32,
        "games": 16,
        "quarantined_rows": 11,
        "quarantined_ids": 10,
        "eligible_ids": 905,
    }
    zamir = [r for r in parsed["rows"] if r["name"] == "Zamir White"]
    assert len(zamir) == 2 and all(r["issues"] for r in zamir)
    assert len({r["line"] for r in zamir}) == 2
    assert any(r["injury"] is None and r["starting"] is None for r in parsed["rows"])


@pytest.mark.parametrize(
    "raw,message",
    [
        (b"x,y\n1,2", "schema"),
        (b"\xff", "UTF-8"),
        (b"\x00", "NUL"),
        pytest.param(b"x" * (10 * 1024 * 1024 + 1), "10 MiB", id="oversize"),
    ],
)
def test_malformed_files(raw: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_yahoo(raw, [])


@pytest.mark.parametrize(
    "column,value,reason",
    [
        ("Salary", "10.001", "Salary"),
        ("Salary", "NaN", "Salary"),
        ("ID", "invented", "ID"),
        ("Position", "K", "position"),
        ("Time", "1:00PM PST", "clock"),
        ("Time", "2:00PM EDT", "clock"),
        ("Team", "KC", "conflict"),
        ("FPPG", "Infinity", "FPPG"),
        ("Game", "KC@LA", "slate"),
        ("Last Name", "", "name"),
    ],
)
def test_row_validation(column: str, value: str, reason: str) -> None:
    setup, raw = demo()
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    rows[0][column] = value
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    parsed = parse_yahoo(
        stream.getvalue().encode(), [dict(g, id=g["event_key"]) for g in setup["games"]]
    )
    assert any(reason.lower() in issue.lower() for issue in parsed["rows"][0]["issues"])


def test_physical_multiline_locator_and_exact_salary() -> None:
    setup, raw = demo()
    raw = raw.replace(b"Synthetic,Alpha", b'"Synthetic\nname",Alpha', 1).replace(
        b",35,", b",35.000,", 1
    )
    result = parse_yahoo(raw, [dict(g, id=g["event_key"]) for g in setup["games"]])
    assert result["rows"][0]["line"] == 2 and result["rows"][0]["line_end"] == 3
    assert result["rows"][1]["line"] == 4
    assert result["rows"][0]["salary_cents"] == 3500
