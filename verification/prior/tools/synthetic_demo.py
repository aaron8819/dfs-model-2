"""Generate clearly synthetic future evidence; never rewrite historical files."""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from server.ingestion import HEADER


def demo(kickoff: datetime | None = None) -> tuple[dict, bytes]:
    kickoff = kickoff or (datetime.now(timezone.utc) + timedelta(days=30)).replace(
        hour=17, minute=0, second=0, microsecond=0
    )
    games = [
        {"event_key": "synthetic-a", "away": "CHI", "home": "GB", "kickoff": kickoff.isoformat()},
        {"event_key": "synthetic-b", "away": "BUF", "home": "MIA", "kickoff": kickoff.isoformat()},
    ]
    setup = {
        "name": "Synthetic future demo",
        "yahoo_id": "synthetic-demo",
        "season": "Synthetic",
        "round": "Test only",
        "timezone": "America/Chicago",
        "games": games,
        "confirmed": True,
        "provenance": "Synthetic test schedule and owner rule confirmation",
        "membership_change_confirmed": False,
    }
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(HEADER)
    clock = kickoff.astimezone(ZoneInfo("America/New_York")).strftime("%I:%M%p %Z").lstrip("0")
    for i, (name, position, salary) in enumerate(
        [
            ("Alpha", "QB", "35"),
            ("Bravo", "QB", "38"),
            ("Charlie", "RB", "90"),
            ("Delta", "RB", "90"),
            ("Echo", "WR", "20"),
            ("Foxtrot", "WR", "25"),
            ("Golf", "WR", "22"),
            ("Hotel", "TE", "15"),
            ("India", "DEF", "10"),
            ("Juliet", "RB", "30"),
            ("Conflict", "WR", "12"),
            ("Conflict", "WR", "13"),
        ]
    ):
        gid = 10 if i == 11 else i
        writer.writerow(
            [
                f"nfl.{'t' if position=='DEF' else 'p'}.{900000+gid}",
                "Synthetic",
                name,
                position,
                "CHI" if i % 2 == 0 else "BUF",
                "GB" if i % 2 == 0 else "MIA",
                "CHI@GB" if i % 2 == 0 else "BUF@MIA",
                clock,
                salary,
                "0.0",
                "O" if name == "Delta" else " ",
                " ",
            ]
        )
    return setup, stream.getvalue().encode()


if __name__ == "__main__":
    setup, raw = demo()
    folder = Path("artifacts/local")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "synthetic-setup.json").write_text(json.dumps(setup, indent=2))
    (folder / "synthetic-yahoo.csv").write_bytes(raw)
    print("Synthetic future setup and CSV written to artifacts/local; historical files untouched.")
