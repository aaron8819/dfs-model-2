"""Synthetic future-dated complete pool and original-format projection files."""

import csv
import io
import json
from pathlib import Path

from server.projections import HEADER
from tools.synthetic_demo import demo


def completion_demo():
    setup, raw = demo()
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    for row in rows:
        if row["Last Name"] in {"Charlie", "Delta"}:
            row["Salary"] = "15"
        if row["Last Name"] == "Delta":
            row["Injury Status"] = " "
        if row["Last Name"] == "Echo":
            row["Team"], row["Opponent"], row["Game"] = "GB", "CHI", "CHI@GB"
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    files = {}
    for position in ["QB", "RB", "WR", "TE", "DST"]:
        out = io.StringIO(newline="")
        w = csv.writer(out)
        w.writerow(HEADER)
        for r in rows:
            if (
                r["Position"] != ("DEF" if position == "DST" else position)
                or r["Last Name"] == "Conflict"
            ):
                continue
            w.writerow(
                [
                    1,
                    r["First Name"] + " " + r["Last Name"],
                    r["Team"],
                    "vs. " + r["Opponent"],
                    "3 stars",
                    "A",
                    "10.0",
                ]
            )
        files[position] = (position + ".csv", out.getvalue().encode())
    return setup, stream.getvalue().encode(), files


if __name__ == "__main__":
    setup, raw, files = completion_demo()
    folder = Path("artifacts/local")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "completion-setup.json").write_text(json.dumps(setup))
    (folder / "completion-yahoo.csv").write_bytes(raw)
    for filename, raw in files.values():
        (folder / filename).write_bytes(raw)
