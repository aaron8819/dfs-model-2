"""Shared entered, schedule and mutation policy. No solver or route exceptions."""

import json

from fastapi import HTTPException

from server.ingestion import SLOTS
from server.persistence import many, one


def reject(message: str) -> None:
    raise HTTPException(423, message)


def identity(row: dict | None):
    return (row.get("entry_id"), row.get("subject_id")) if row else None


def clock(db):
    return one(db, "SELECT clock_timestamp() AS at, observed_at FROM clock_observation")


def observe(engine):
    # Serialize observations and sample after that short lock wait. Ordinary concurrent
    # reads must not look like a backward clock simply because one was evaluated first.
    with engine.begin() as db:
        one(db, "SELECT observed_at FROM clock_observation FOR UPDATE")
        sample = clock(db)
        high = one(
            db,
            "UPDATE clock_observation SET observed_at=greatest(observed_at,:at) "
            "RETURNING observed_at",
            at=sample["at"],
        )["observed_at"]
        return {"at": sample["at"], "observed_at": high}


def context(db, w, assignments=None):
    # Independent of this read/write transaction: observed locks survive its rollback.
    sample = observe(db.engine)
    high = max(sample["observed_at"], w.get("decision_at") or sample["observed_at"])
    effective = max(sample["at"], high)
    rows = many(
        db,
        "SELECT d.* FROM lock_head h JOIN lock_decision d ON d.id=h.decision_id "
        "JOIN setup_revision s ON s.id=:setup JOIN slate_game sg "
        "ON sg.slate_revision_id=s.slate_revision_id AND sg.game_id=h.game_id "
        "WHERE h.contest_id=:cid ORDER BY h.game_id",
        cid=w["contest_id"],
        setup=w["setup_id"],
    )
    started = [str(r["game_id"]) for r in rows if r["deadline"] and r["deadline"] <= effective]
    unknown = (
        any(r["deadline"] is None for r in rows)
        or not rows
        or bool(
            one(
                db,
                "SELECT 1 FROM setup_revision s JOIN schedule_observation o "
                "ON o.schedule_id=s.schedule_id "
                "WHERE s.id=:id AND o.kickoff IS NULL LIMIT 1",
                id=w["setup_id"],
            )
        )
    )
    entered = one(db, "SELECT * FROM entered_revision WHERE id=:id", id=w["entered_id"])
    facts = entered["assignments"] if entered else {}
    fixed = {s: p for s, p in facts.items() if p.get("game_id") in started}
    blockers = []
    if entered and set(facts) != set(SLOTS):
        blockers.append(
            "Entered actual slot evidence is incomplete; reconcile the full Yahoo lineup"
        )
    if entered and json.loads(entered["attestation"]).get("disputed"):
        blockers.append("Entered facts explicitly disputed; reconcile with Yahoo evidence")
    if sample["at"] < high:
        blockers.append("Server clock moved backward; restore verified clock health")
    if unknown:
        blockers.append("Schedule is unknown; review dated Yahoo schedule evidence")
    if started and not entered:
        blockers.append("Missing entered lineup after kickoff; reconcile actual Yahoo assignments")
    # All entered rows need identifiable games, otherwise fixed membership itself is unknown.
    for slot, p in facts.items():
        if (
            slot not in SLOTS
            or p.get("game_id") not in {str(r["game_id"]) for r in rows}
            or not p.get("entry_id")
            or not p.get("subject_id")
        ):
            blockers.append(f"{slot}: fixed identity/slot/game missing; reconcile Yahoo facts")
    for slot, p in fixed.items():
        if (
            not isinstance(p.get("salary_cents"), int)
            or p["salary_cents"] < 0
            or p.get("position") not in SLOTS.get(slot, ())
            or not p.get("team")
            or not p.get("row_id")
            or p.get("issues")
        ):
            blockers.append(
                f"{slot}: fixed salary/eligibility/source disputed; reconcile Yahoo facts"
            )
    if assignments is not None and started:
        for slot, p in fixed.items():
            if identity(assignments.get(slot)) != identity(p):
                blockers.append(f"{slot}: draft differs from fixed entered assignment; reconcile")
        for slot, p in assignments.items():
            if p.get("game_id") in started and identity(fixed.get(slot)) != identity(p):
                blockers.append(f"{slot}: started player is not entered in this slot; reconcile")
    all_locked = bool(rows) and len(started) == len(rows)
    return {
        "at": sample["at"],
        "started": started,
        "fixed": fixed,
        "entered_id": str(w["entered_id"]) if w["entered_id"] else None,
        "decisions": [str(r["id"]) for r in rows],
        "blockers": blockers,
        "all_locked": all_locked,
        "unknown": unknown,
        "clock_uncertain": sample["at"] < high,
        "mode": (
            "Reconciliation required"
            if blockers
            else (
                "All games locked"
                if all_locked
                else "Late swaps available" if started else "Pre-lock window"
            )
        ),
        "deadlines": {str(r["game_id"]): r["deadline"] for r in rows},
    }


def require(ctx, allow_all=False):
    if ctx["blockers"]:
        reject("; ".join(ctx["blockers"]))
    if ctx["all_locked"] and not allow_all:
        reject("All games locked; only historical reconciliation remains available")


def validate_change(ctx, assignments):
    require(ctx)
    for slot, p in ctx["fixed"].items():
        if identity(assignments.get(slot)) != identity(p):
            reject(
                f"{slot} is fixed to {p['name']} in Yahoo; reconcile historical facts if inaccurate"
            )
    for slot, p in assignments.items():
        if p.get("game_id") in ctx["started"] and identity(ctx["fixed"].get(slot)) != identity(p):
            reject(f"{slot}: a started-game player cannot be newly selected or moved")
