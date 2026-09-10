"""Isolated future-dated decision fixtures; no historical freshness edits."""

import csv
import io
import json
from pathlib import Path

from server.projections import HEADER
from tools.completion_demo import completion_demo


def decision_demo() -> dict:
    setup, raw, _ = completion_demo()
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    for index, position in enumerate(["RB", "WR", "TE"]):
        original = next(r for r in rows if r["Position"] == position)
        rows.append(
            {
                **original,
                "ID": f"nfl.p.99000{index}",
                "Last Name": f"Alternative{position}",
                "Salary": "12",
            }
        )
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    files = {}
    for position in ["QB", "RB", "WR", "TE", "DST"]:
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        for row in rows:
            if (
                row["Position"] != ("DEF" if position == "DST" else position)
                or row["Last Name"] == "Conflict"
            ):
                continue
            writer.writerow(
                [
                    1,
                    row["First Name"] + " " + row["Last Name"],
                    row["Team"],
                    "vs. " + row["Opponent"],
                    "3 stars",
                    "A",
                    "9.25" if row["Last Name"].startswith("Alternative") else "10.0",
                ]
            )
        files[position] = stream.getvalue()
    return {"setup": setup, "yahoo": out.getvalue(), "projections": files}


if __name__ == "__main__":
    folder = Path("artifacts/local")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "decision-fixture.json").write_text(json.dumps(decision_demo()), encoding="utf-8")
