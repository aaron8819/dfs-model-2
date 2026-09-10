"""FantasyPros original-byte adapter and evidence-based association, version 1."""

import csv
import io
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from server.ingestion import TEAMS
from server.recommendation.contracts import exact_units

PARSER = "fantasypros-csv/1"
POLICY = "yahoo-half-ppr-approximation/1"
HEADER = ["RK", "PLAYER NAME", "TEAM", "OPP", "MATCHUP", "START/SIT", "PROJ. FPTS"]
POSITIONS = {"QB", "RB", "WR", "TE", "DST"}
ALIASES = {"LAR": "LA", "JAX": "JAC", "WSH": "WAS"}
EXCLUDED = {
    "O",
    "OUT",
    "INACTIVE",
    "IR",
    "PUP",
    "NFI",
    "SUSP",
    "SUSPENDED",
    "RESERVE",
    "REPORTED ABSENCE",
}


def team(value: str) -> str:
    return ALIASES.get(value, value)


def name(value: str) -> str:
    # Punctuation/case normalization is only corroboration with team, position and opponent.
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def number(raw: str) -> tuple[str, int | None]:
    value = raw.strip()
    if not value or value in {"-", "--", "N/A"}:
        return "missing", None
    try:
        if not Decimal(value).is_finite():
            return "nonfinite", None
    except InvalidOperation:
        return "invalid", None
    try:
        units = exact_units(value)
        return ("explicit_zero" if units == 0 else "numeric"), units
    except ValueError as exc:
        return ("excessive_precision" if "precision" in str(exc) else "invalid"), None


def parse(raw: bytes, position: str) -> dict:
    if position not in POSITIONS or len(raw) > 10 * 1024 * 1024:
        raise ValueError("Unsupported position or file exceeds 10 MiB")
    if b"\x00" in raw:
        raise ValueError("CSV contains NUL bytes")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if [v.strip() for v in next(reader, [])] != HEADER:
        raise ValueError("Unsupported FantasyPros schema")
    rows, separators, errors = [], [], []
    while True:
        start = reader.line_num + 1
        values = next(reader, None)
        if values is None:
            break
        if not any(v.strip() for v in values):
            separators.append({"line": start, "line_end": reader.line_num, "values": values})
            continue
        if len(values) != len(HEADER):
            raise ValueError(f"Line {start}: expected seven fields")
        original = dict(zip(HEADER, values, strict=True))
        v = {k: x.strip() for k, x in original.items()}
        state, units = number(original["PROJ. FPTS"])
        opponent = re.fullmatch(r"(?:at|vs\.?)\s+([A-Z]+)", v["OPP"])
        free_agent = v["TEAM"] == "FA" and v["OPP"] == "-"
        if not v["PLAYER NAME"] or (
            not free_agent and (team(v["TEAM"]) not in TEAMS or not opponent)
        ):
            errors.append(f"Line {start}: missing identity or unsupported team/opponent")
        if state not in {"numeric", "explicit_zero", "missing"}:
            errors.append(f"Line {start}: {state} projection")
        rows.append(
            {
                "line": start,
                "line_end": reader.line_num,
                "raw": original,
                "name": v["PLAYER NAME"],
                "team": team(v["TEAM"]),
                "opponent": team(opponent[1]) if opponent else None,
                "position": "DEF" if position == "DST" else position,
                "numeric_state": state,
                "units": units,
                "projection": v["PROJ. FPTS"] if units is not None else None,
            }
        )
        if len(rows) > 5000:
            raise ValueError("Too many projection records")
    if not rows:
        errors.append("No source subjects")
    return {"rows": rows, "separators": separators, "errors": errors}


def associate(
    rows: list[dict], pool: list[dict], resolutions: list[dict], availability: list[dict]
) -> dict:
    """Never repair Yahoo facts; all duplicate associations become explicit exceptions."""
    mappings = {r["source_key"]: r for r in resolutions}
    matches, exceptions = [], []
    for source in rows:
        resolution = mappings.get(source["source_key"])
        candidates = [
            p
            for p in pool
            if p["position"] == source["position"]
            and p["team"] == source["team"]
            and p["opponent"] == source["opponent"]
            and (
                (
                    p["entry_id"] == resolution["entry_id"]
                    and p["subject_id"] == resolution["subject_id"]
                )
                if resolution
                else (source["position"] == "DEF" or name(p["name"]) == name(source["name"]))
            )
        ]
        if len(candidates) != 1 or candidates[0]["issues"]:
            exceptions.append(
                {
                    "source": source,
                    "yahoo": candidates
                    or [
                        p
                        for p in pool
                        if p["team"] == source["team"]
                        and p["position"] == source["position"]
                        and p["opponent"] == source["opponent"]
                    ],
                    "reason": (
                        "Unmatched source identity"
                        if not candidates
                        else "Conflicting or quarantined Yahoo facts"
                    ),
                }
            )
        else:
            matches.append(
                {
                    "source": source,
                    "yahoo": candidates[0],
                    "evidence": resolution
                    or "Unique name/team/position/opponent; DEF team identity",
                }
            )
    counts = Counter(m["yahoo"]["entry_id"] for m in matches)
    admitted = []
    for match in matches:
        if counts[match["yahoo"]["entry_id"]] != 1:
            exceptions.append({**match, "reason": "Multiple source records bind one Yahoo entry"})
        else:
            admitted.append(match)
    matched = {m["yahoo"]["entry_id"]: m for m in admitted}
    evaluated = []
    for p in pool:
        m = matched.get(p["entry_id"])
        evidence = [
            a
            for a in availability
            if a["subject_id"] == p["subject_id"] and a["game_id"] == p["game_id"]
        ]
        designations = [p["injury"] or ""] + [a["designation"] for a in evidence]
        blocked = any(v.upper() in EXCLUDED for v in designations)
        # A resolution covers specific prior evidence; later evidence automatically reopens it.
        resolutions_here = [a for a in evidence if a.get("resolves")]
        if resolutions_here:
            last = resolutions_here[-1]
            covered = set(last["resolves"])
            blockers = {
                a["id"] for a in evidence if a["designation"].upper() in EXCLUDED and a is not last
            }
            if (
                not p["injury"] or p["injury"].upper() not in EXCLUDED or p["row_id"] in covered
            ) and blockers <= covered:
                blocked = last["designation"].upper() in EXCLUDED
        projection = m["source"]["projection"] if m else None
        concerns = [v for v in designations if v] or ["Availability unknown"]
        if blocked and any(v.upper() == "ACTIVE" for v in designations):
            concerns.append("Conflicting participation evidence; excluded pending resolution")
        evaluated.append(
            {
                **p,
                "projection": projection,
                "units": m["source"]["units"] if m else None,
                "available": not blocked,
                "availability": evidence,
                "concerns": concerns,
                "eligible": not p["issues"] and not blocked and projection is not None,
            }
        )

    def counts_for(group: list[dict]) -> dict:
        return {
            "entries": len(group),
            "covered": sum(p["projection"] is not None for p in group),
            "missing": sum(p["projection"] is None for p in group),
            "eligible": sum(p["eligible"] for p in group),
            "zeros": sum(p["eligible"] and p["units"] == 0 for p in group),
            "unavailable": sum(not p["available"] for p in group),
            "quarantined": sum(bool(p["issues"]) for p in group),
        }

    return {
        "matches": admitted,
        "exceptions": exceptions,
        "players": evaluated,
        "summary": {
            **counts_for(evaluated),
            "source_records": len(rows),
            "matched": len(admitted),
            "unmatched_or_conflicting": len(exceptions),
            "unmatched": sum(e["reason"] == "Unmatched source identity" for e in exceptions),
            "conflicting": sum(e["reason"] != "Unmatched source identity" for e in exceptions),
        },
        "by_position": {
            k: counts_for([p for p in evaluated if p["position"] == k])
            for k in {p["position"] for p in pool}
        },
        "by_game": {
            k: counts_for([p for p in evaluated if p["game"] == k])
            for k in {p["game"] for p in pool}
        },
    }
