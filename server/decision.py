"""Manual game context and explicit, pre-lock draft history actions."""

from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy.engine import Connection

from server import late_swap
from server.analysis import Expected, items
from server.ingestion import SLOTS
from server.persistence import canonical, digest, many, one, run, uid
from server.recommendation.contracts import exact_units
from server.workspace import WorkspaceService, fail


class OddsInput(Expected):
    expected_context_revision: int = Field(ge=0)
    game_id: UUID
    source: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=2000)
    observed_at: datetime
    published_at: datetime | None = None
    total: str
    home_spread: str
    market: Literal["full-game"] = "full-game"
    convention: Literal["home-team"] = "home-team"
    supersedes: UUID | None = None
    reason: str = Field(default="Initial observation", min_length=5, max_length=2000)

    @model_validator(mode="after")
    def valid(self) -> Self:
        total = exact_units(self.total, 4, 200)
        spread = exact_units(self.home_spread, 4, 200)
        if total <= 0 or abs(spread) > total:
            raise ValueError("Total must be positive and at least the absolute home spread")
        if self.observed_at.tzinfo is None or (
            self.published_at is not None and self.published_at.tzinfo is None
        ):
            raise ValueError("Timestamps require an explicit timezone")
        if self.published_at and self.published_at > self.observed_at:
            raise ValueError("Publication cannot follow observation")
        return self


class EnteredInput(Expected):
    draft_id: UUID
    attestation: Literal["Record as entered in Yahoo"]
    reason: str = Field(min_length=5, max_length=2000)


class DisputeInput(Expected):
    reason: str = Field(min_length=5, max_length=2000)
    reference: str = Field(min_length=5, max_length=2000)


class ReconcileInput(Expected):
    preview_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    draft_id: UUID | None
    entered_id: UUID | None
    assignments: dict[str, UUID] = Field(min_length=9, max_length=9)
    draft_assignments: dict[str, UUID] | None = Field(default=None, max_length=9)
    attestation: Literal["Correct historical Yahoo facts; this does not authorize a late selection"]
    reason: str = Field(min_length=5, max_length=2000)
    reference: str = Field(min_length=5, max_length=2000)
    reported_at: AwareDatetime | None = None


def implied(total: str, spread: str) -> dict[str, str]:
    # Validate before Decimal arithmetic; supported bounds fit well within its context.
    t, s = exact_units(total, 4, 200), exact_units(spread, 4, 200)
    return {
        "home_implied": str(Decimal(t - s) / 20000),
        "away_implied": str(Decimal(t + s) / 20000),
    }


def environments(db: Connection, w: dict) -> list[dict]:
    rows = many(
        db,
        "SELECT r.* FROM odds_head h JOIN odds_revision r ON r.id=h.revision_id "
        "WHERE h.workspace_id=:id",
        id=w["id"],
    )
    result = []
    for row in rows:
        old = one(db, "SELECT * FROM odds_revision WHERE id=:id", id=row["parent_id"])
        comparable = bool(
            old
            and old["source"] == row["source"]
            and old["setup_id"] == row["setup_id"]
            and old["observed_at"] < row["observed_at"]
            and (
                old["published_at"] is None
                or row["published_at"] is None
                or old["published_at"] < row["published_at"]
            )
        )
        result.append(
            {
                **row,
                **implied(row["total"], row["home_spread"]),
                "current_setup": row["setup_id"] == w["setup_id"],
                "total_change": (
                    str(Decimal(row["total"]) - Decimal(old["total"])) if comparable else None
                ),
                "spread_change": (
                    str(Decimal(row["home_spread"]) - Decimal(old["home_spread"]))
                    if comparable
                    else None
                ),
            }
        )
    return sorted(result, key=lambda r: (-exact_units(r["total"]), str(r["game_id"])))


class DecisionService:
    def __init__(self, workspace: WorkspaceService) -> None:
        self.workspace, self.engine = workspace, workspace.engine

    def dispute(self, wid, owner, key, data):
        def action(db):
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            if not w["entered_id"]:
                fail(422, "No entered record; use missing-entered reconciliation")
            rid = uid()
            run(
                db,
                "INSERT INTO entered_revision(id,workspace_id,parent_id,draft_id,setup_id,"
                "pool_id,actor,assignments,attestation) SELECT :id,workspace_id,id,draft_id,"
                "setup_id,pool_id,:owner,assignments,:attestation "
                "FROM entered_revision WHERE id=:old",
                id=rid,
                old=w["entered_id"],
                owner=owner,
                attestation=canonical({**data.model_dump(), "disputed": True}),
            )
            # Declaring uncertainty only removes permission; never changes selections or locks.
            run(
                db,
                "UPDATE workspace SET entered_id=:id,revision=revision+1 WHERE id=:wid",
                id=rid,
                wid=wid,
            )
            return {"entered_id": rid, "revision": w["revision"] + 1}

        return self.workspace.command(
            owner, key, {"dispute": data.model_dump(), "workspace": wid}, action
        )

    def odds(self, wid: str, owner: str, key: str, data: OddsInput) -> dict:
        def action(db: Connection) -> dict:
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            if w["context_revision"] != data.expected_context_revision:
                fail(409, "Game context changed; observation retained locally for review")
            if not any(
                str(g["id"]) == str(data.game_id) for g in self.workspace.games(db, w["setup_id"])
            ):
                fail(422, "Game is not a member of this exact slate")
            if data.observed_at > one(db, "SELECT clock_timestamp() AS at")["at"]:
                fail(422, "Observed time cannot be in the future")
            old = one(
                db,
                "SELECT r.* FROM odds_head h JOIN odds_revision r ON r.id=h.revision_id "
                "WHERE h.workspace_id=:wid AND h.game_id=:game",
                wid=wid,
                game=data.game_id,
            )
            if (old["id"] if old else None) != data.supersedes:
                fail(
                    409,
                    "Explicitly supersede the displayed observation; sources are never averaged",
                )
            duplicate = one(
                db,
                "SELECT * FROM odds_revision WHERE workspace_id=:wid "
                "AND game_id=:game AND source=:source AND observed_at=:at",
                wid=wid,
                game=data.game_id,
                source=data.source,
                at=data.observed_at,
            )
            if duplicate:
                fail(
                    409,
                    "Duplicate or conflicting observation at this source/time; original retained",
                )
            rid = uid()
            run(
                db,
                "INSERT INTO odds_revision(id,workspace_id,setup_id,game_id,parent_id,source,"
                "reference,observed_at,published_at,total,home_spread,reason,actor) VALUES "
                "(:id,:wid,:setup,:game,:parent,:source,:ref,:observed,:published,:tota"
                "l,:spread,:reason,:actor)",
                id=rid,
                wid=wid,
                setup=w["setup_id"],
                game=data.game_id,
                parent=data.supersedes,
                source=data.source,
                ref=data.reference,
                observed=data.observed_at,
                published=data.published_at,
                total=data.total,
                spread=data.home_spread,
                reason=data.reason,
                actor=owner,
            )
            run(
                db,
                "INSERT INTO odds_head VALUES (:wid,:game,:id) ON CONFLICT(workspace_id,game_id) "
                "DO UPDATE SET revision_id=excluded.revision_id",
                wid=wid,
                game=data.game_id,
                id=rid,
            )
            # Context has its own concurrency token. It cannot invalidate or rewrite solver inputs.
            run(db, "UPDATE workspace SET context_revision=context_revision+1 WHERE id=:id", id=wid)
            return {"odds_id": rid, "context_revision": w["context_revision"] + 1}

        return self.workspace.command(
            owner, key, {"odds": data.model_dump(mode="json"), "workspace": wid}, action
        )

    def current_assignments(self, db: Connection, w: dict, historical: dict) -> dict:
        pool = {
            p["entry_id"]: p
            for p in self.workspace.pool(db, w["active_pool_id"])
            if not p["issues"]
        }
        batch = one(db, "SELECT setup_id FROM import_batch WHERE id=:id", id=w["active_pool_id"])
        if not batch or batch["setup_id"] != w["setup_id"]:
            fail(422, "Activate Yahoo facts for the current setup first")
        policy = late_swap.context(db, w)
        pool.update({p["entry_id"]: p for p in policy["fixed"].values()})
        current = {}
        for slot, row in historical.items():
            p = pool.get(row["entry_id"])
            if not p or p["subject_id"] != row["subject_id"] or p["position"] not in SLOTS[slot]:
                fail(
                    422,
                    "Restored/recorded assignments need resolved current Yahoo identities a"
                    "nd slots",
                )
            current[slot] = p
        if len({p["entry_id"] for p in current.values()}) != len(current):
            fail(422, "Duplicate assignment")
        return current

    def undo(self, wid: str, owner: str, key: str, data: Expected) -> dict:
        def action(db: Connection) -> dict:
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            latest = one(db, "SELECT * FROM draft_revision WHERE id=:id", id=w["draft_id"])
            if not latest or any(
                o.get("action") in {"undo", "reconcile"} for o in latest["operations"]
            ):
                fail(422, "No eligible latest action to undo")
            historical = self.workspace.assignments(db, latest["parent_id"])
            restored = self.current_assignments(db, w, historical)
            avoided = {
                p["entry_id"]
                for p in items(db, "preference_revision", w["preference_id"])
                if p["value"] == "avoid"
            }
            fixed = late_swap.context(db, w)["fixed"]
            if (avoided - {p["entry_id"] for p in fixed.values()}) & {
                p["entry_id"] for p in restored.values()
            }:
                fail(
                    422,
                    "Undo would restore an Avoid player. Clear that preference explicitly first",
                )
            # Keep stays a generation preference; no preferences roll back.
            return self.workspace.write_draft(
                db, w, historical, [{"action": "undo", "reversed_id": str(latest["id"])}]
            )

        return self.workspace.command(
            owner, key, {"undo": data.model_dump(), "workspace": wid}, action
        )

    def entered(self, wid: str, owner: str, key: str, data: EnteredInput) -> dict:
        def action(db: Connection) -> dict:
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            if w["draft_id"] != data.draft_id:
                fail(409, "The reviewed draft changed")
            current = self.current_assignments(db, w, self.workspace.assignments(db, w["draft_id"]))
            teams = Counter(p["team"] for p in current.values())
            if (
                set(current) != set(SLOTS)
                or sum(p["salary_cents"] for p in current.values()) > 20000
                or len(teams) < 3
                or max(teams.values(), default=0) > 6
            ):
                fail(422, "Recording requires a complete lineup legal under current Yahoo facts")
            policy = late_swap.context(db, w, self.workspace.assignments(db, w["draft_id"]))
            late_swap.validate_change(policy, current)
            rid = uid()
            run(
                db,
                "INSERT INTO entered_revision(id,workspace_id,parent_id,draft_id,setup_id,pool_id,"
                "actor,assignments,attestation) VALUES (:id,:wid,:parent,:draft,:setup,"
                ":pool,:actor,"
                "CAST(:assignments AS jsonb),:attestation)",
                id=rid,
                wid=wid,
                parent=w["entered_id"],
                draft=w["draft_id"],
                setup=w["setup_id"],
                pool=w["active_pool_id"],
                actor=owner,
                assignments=canonical(current),
                attestation=canonical({"action": data.attestation, "reason": data.reason}),
            )
            written = self.workspace.advance(db, w, "entered_id", rid, policy)
            return {"entered_id": rid, "revision": written["revision"]}

        return self.workspace.command(
            owner, key, {"entered": data.model_dump(mode="json"), "workspace": wid}, action
        )

    def reconciliation_plan(self, db, w, data):
        if w["draft_id"] != data.draft_id or w["entered_id"] != data.entered_id:
            fail(409, "Reviewed draft or entered head changed; preserve edits and preview again")
        policy = late_swap.context(db, w)
        if policy["unknown"] or policy["clock_uncertain"]:
            fail(423, "Resolve schedule/clock uncertainty before historical reconciliation")
        if data.reported_at and data.reported_at > policy["at"]:
            fail(422, "Reported event time cannot be in the future; receipt time is server-owned")

        def resolve(rows):
            resolved = {}
            for slot, row_id in rows.items():
                row = one(
                    db,
                    "SELECT p.*,e.yahoo_id FROM pool_row p JOIN slate_entry e ON e.id=p.entry_id "
                    "JOIN import_batch b ON b.id=p.batch_id "
                    "JOIN setup_revision s ON s.id=b.setup_id "
                    "WHERE p.id=:id AND s.contest_id=:cid",
                    id=row_id,
                    cid=w["contest_id"],
                )
                if not row or row["issues"] or slot not in SLOTS:
                    fail(422, f"{slot}: select unquarantined Yahoo evidence from this contest")
                p = {
                    **row["normalized"],
                    "row_id": str(row["id"]),
                    "entry_id": str(row["entry_id"]),
                    "subject_id": str(row["subject_id"]),
                }
                if p["position"] not in SLOTS[slot] or p.get("salary_cents") is None:
                    fail(422, f"{slot}: unresolved salary or actual slot eligibility")
                resolved[slot] = p
            if len({p["entry_id"] for p in resolved.values()}) != len(resolved):
                fail(422, "Duplicate actual Yahoo entry")
            return resolved

        actual = resolve(data.assignments)
        teams = Counter(p["team"] for p in actual.values())
        members = {str(g["id"]) for g in self.workspace.games(db, w["setup_id"])}
        if (
            set(actual) != set(SLOTS)
            or sum(p["salary_cents"] for p in actual.values()) > 20000
            or len(teams) < 3
            or max(teams.values(), default=0) > 6
            or any(p["game_id"] not in members for p in actual.values())
        ):
            fail(422, "Reconciliation requires a complete legal, evidenced actual Yahoo lineup")
        before = self.workspace.assignments(db, w["draft_id"])
        fixed = {s: p for s, p in actual.items() if p["game_id"] in policy["started"]}
        draft = (
            resolve(data.draft_assignments) if data.draft_assignments is not None else dict(before)
        )
        if data.draft_assignments is None:
            for slot, p in fixed.items():
                occupant = draft.get(slot)
                if (
                    occupant
                    and occupant["game_id"] not in policy["started"]
                    and late_swap.identity(occupant) != late_swap.identity(p)
                ):
                    fail(
                        422,
                        f"{slot}: restoration displaces editable work; "
                        "explicitly provide reviewed draft assignments",
                    )
            fixed_entries = {p["entry_id"] for p in fixed.values()}
            draft = {
                s: p
                for s, p in draft.items()
                if p["entry_id"] not in fixed_entries and p["game_id"] not in policy["started"]
            }
            draft.update(fixed)
        resolved_policy = {**policy, "fixed": fixed, "blockers": [], "all_locked": False}
        late_swap.validate_change(resolved_policy, draft)
        if len({p["entry_id"] for p in draft.values()}) != len(draft):
            fail(422, "Resulting draft has duplicate entry")
        prior = one(db, "SELECT assignments FROM entered_revision WHERE id=:id", id=w["entered_id"])
        plan = {
            "before_entered": prior["assignments"] if prior else {},
            "entered": actual,
            "before_draft": before,
            "draft": draft,
            "policy": resolved_policy,
        }
        binding = {**plan, "policy": {k: policy[k] for k in ("started", "decisions", "entered_id")}}
        return {**plan, "preview_hash": digest(canonical(binding).encode())}

    def reconcile(self, wid, owner, key, data, preview=False):
        def action(db):
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            plan = self.reconciliation_plan(db, w, data)
            if preview:
                return plan
            if data.preview_hash != plan["preview_hash"]:
                fail(409, "Reconciliation preview changed or missing; review exact changes again")
            rid = uid()
            run(
                db,
                "INSERT INTO entered_revision(id,workspace_id,parent_id,draft_id,setup_id,pool_id,"
                "actor,assignments,attestation) VALUES "
                "(:id,:wid,:parent,:draft,:setup,:pool,:actor,"
                "CAST(:assignments AS jsonb),:attestation)",
                id=rid,
                wid=wid,
                parent=w["entered_id"],
                draft=w["draft_id"],
                setup=w["setup_id"],
                pool=w["active_pool_id"],
                actor=owner,
                assignments=canonical(plan["entered"]),
                attestation=canonical(data.model_dump(mode="json")),
            )
            written = self.workspace.conditional_head(db, w, "entered_id", rid, plan["policy"])
            w = {**w, "entered_id": rid, "revision": written["revision"]}
            result = self.workspace.write_draft(
                db,
                w,
                plan["draft"],
                [{"action": "reconcile", "entered_id": rid}],
                reconciliation_policy=plan["policy"],
            )
            return {**result, "entered_id": rid}

        if preview:
            with self.engine.begin() as db:
                return action(db)
        return self.workspace.command(
            owner, key, {"reconcile": data.model_dump(mode="json"), "workspace": wid}, action
        )
