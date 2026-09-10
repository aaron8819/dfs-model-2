"""Small explicit transactions over immutable evidence and aggregate heads."""

from collections import Counter
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.engine import Connection, Engine

from server import late_swap
from server.contest import RULE_PROFILE, Activation, DraftCommand, SetupInput
from server.ingestion import PARSER_VERSION, SLOTS, parse_yahoo
from server.persistence import canonical, digest, many, one, run, uid


def fail(status: int, message: str) -> None:
    raise HTTPException(status, message)


class WorkspaceService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def command(
        self, owner: str, key: str, payload: dict, action: Callable[[Connection], dict]
    ) -> dict:
        late_swap.observe(self.engine)
        fingerprint = digest(canonical(payload).encode())
        try:
            with self.engine.begin() as db:
                # Command-key lock precedes contest and workspace locks.
                run(db, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key=owner + key)
                receipt = one(
                    db,
                    "SELECT * FROM command_receipt WHERE owner_id=:owner AND key=:key",
                    owner=owner,
                    key=key,
                )
                if receipt:
                    if receipt["payload_hash"] != fingerprint:
                        fail(
                            409, "Idempotency key already belongs to a different attempted command"
                        )
                    return receipt["result"]
                result = action(db)
                run(
                    db,
                    "INSERT INTO command_receipt(owner_id,key,payload_hash,result) "
                    "VALUES (:owner,:key,:hash,CAST(:result AS jsonb))",
                    owner=owner,
                    key=key,
                    hash=fingerprint,
                    result=canonical(result),
                )
                return result
        finally:
            late_swap.observe(self.engine)

    def lock(self, db: Connection, workspace: str, owner: str, expected: int) -> dict:
        contest = one(
            db,
            "SELECT c.* FROM contest c JOIN workspace w ON w.contest_id=c.id "
            "WHERE w.id=:id AND c.owner_id=:owner FOR UPDATE OF c",
            id=workspace,
            owner=owner,
        )
        if not contest:
            fail(404, "Workspace not found")
        w = one(db, "SELECT * FROM workspace WHERE id=:id FOR UPDATE", id=workspace)
        if w["revision"] != expected:
            raise HTTPException(
                409,
                {
                    "message": "Information changed. Attempt retained for review.",
                    "current_revision": w["revision"],
                },
            )
        return w

    def setup(self, owner: str, key: str, data: SetupInput, workspace: str | None = None) -> dict:
        def apply(db: Connection) -> dict:
            if workspace:
                w = self.lock(db, workspace, owner, data.expected_revision)
                contest = one(db, "SELECT * FROM contest WHERE id=:id", id=w["contest_id"])
                if any(
                    contest[k] != getattr(data, k) for k in ("yahoo_id", "name", "season", "round")
                ):
                    fail(
                        422, "This workspace belongs to its original contest. Create a new contest."
                    )
                cid = str(contest["id"])
                slate = one(db, "SELECT * FROM slate WHERE contest_id=:id", id=cid)
                sid = str(slate["id"])
                previous = one(db, "SELECT * FROM setup_revision WHERE id=:id", id=w["setup_id"])
                rid = str(previous["rule_id"])
            else:
                cid, sid, rid = uid(), uid(), uid()
                run(
                    db,
                    "INSERT INTO contest VALUES (:id,:owner,:yahoo,:name,:season,:round)",
                    id=cid,
                    owner=owner,
                    yahoo=data.yahoo_id,
                    name=data.name,
                    season=data.season,
                    round=data.round,
                )
                run(db, "INSERT INTO slate VALUES (:id,:contest)", id=sid, contest=cid)
                run(
                    db,
                    "INSERT INTO rule_revision(id,contest_id,profile,confirmed_by,provenance) "
                    "VALUES (:id,:contest,CAST(:profile AS jsonb),:owner,:source)",
                    id=rid,
                    contest=cid,
                    profile=canonical(RULE_PROFILE),
                    owner=owner,
                    source=data.provenance,
                )
            gids = []
            for g in data.games:
                existing = one(
                    db,
                    "SELECT * FROM game WHERE contest_id=:cid AND event_key=:key",
                    cid=cid,
                    key=g.event_key,
                )
                if existing:
                    if (existing["away"], existing["home"]) != (g.away, g.home):
                        fail(422, "Stable game identity cannot change teams")
                    gids.append(str(existing["id"]))
                else:
                    gid = uid()
                    run(
                        db,
                        "INSERT INTO game VALUES (:id,:cid,:key,:away,:home)",
                        id=gid,
                        cid=cid,
                        key=g.event_key,
                        away=g.away,
                        home=g.home,
                    )
                    gids.append(gid)
            membership = digest(canonical(sorted(gids)).encode())
            sr = one(
                db,
                "SELECT * FROM slate_revision WHERE slate_id=:id AND membership_hash=:hash",
                id=sid,
                hash=membership,
            )
            if workspace and (not sr or sr["id"] != previous["slate_revision_id"]):
                lock_policy = late_swap.context(db, w)
                if lock_policy["started"] or lock_policy["unknown"]:
                    fail(423, "Slate membership cannot change after lock or with unknown schedule")
                if not data.membership_change_confirmed:
                    fail(422, "Explicitly confirm changed game membership and reimport Yahoo")
            if not sr:
                sr = {"id": uid()}
                run(
                    db,
                    "INSERT INTO slate_revision(id,slate_id,membership_hash) "
                    "VALUES (:id,:sid,:hash)",
                    id=sr["id"],
                    sid=sid,
                    hash=membership,
                )
                for gid in gids:
                    run(db, "INSERT INTO slate_game VALUES (:sid,:gid)", sid=sr["id"], gid=gid)
            schedule, setup = uid(), uid()
            run(
                db,
                "INSERT INTO schedule_revision(id,contest_id,provenance) VALUES (:id,:cid,:source)",
                id=schedule,
                cid=cid,
                source=data.provenance,
            )
            for gid, g in zip(gids, data.games, strict=True):
                run(
                    db,
                    "INSERT INTO schedule_observation VALUES (:sid,:gid,:kickoff)",
                    sid=schedule,
                    gid=gid,
                    kickoff=g.kickoff,
                )
                old = one(
                    db,
                    "SELECT d.* FROM lock_head h JOIN lock_decision d ON d.id=h.decision_id "
                    "WHERE h.contest_id=:cid AND h.game_id=:gid",
                    cid=cid,
                    gid=gid,
                )
                deadline = g.kickoff
                if old and old["deadline"] is not None:
                    deadline = min(old["deadline"], deadline) if deadline else old["deadline"]
                lid = uid()
                run(
                    db,
                    "INSERT INTO lock_decision"
                    "(id,contest_id,game_id,schedule_id,previous_id,deadline) "
                    "VALUES (:id,:cid,:gid,:sid,:previous,:deadline)",
                    id=lid,
                    cid=cid,
                    gid=gid,
                    sid=schedule,
                    previous=old["id"] if old else None,
                    deadline=deadline,
                )
                run(
                    db,
                    "INSERT INTO lock_head VALUES (:cid,:gid,:id) ON CONFLICT(contest_id,game_id) "
                    "DO UPDATE SET decision_id=excluded.decision_id",
                    cid=cid,
                    gid=gid,
                    id=lid,
                )
            run(
                db,
                "INSERT INTO setup_revision"
                "(id,contest_id,rule_id,slate_revision_id,schedule_id,timezone) "
                "VALUES (:id,:cid,:rid,:slate,:schedule,:zone)",
                id=setup,
                cid=cid,
                rid=rid,
                slate=sr["id"],
                schedule=schedule,
                zone=data.timezone,
            )
            wid = workspace or uid()
            if workspace:
                changed = one(
                    db,
                    """WITH decision AS MATERIALIZED (SELECT clock_timestamp() AS at)
                    UPDATE workspace w SET setup_id=:setup,revision=revision+1
                    FROM decision WHERE w.id=:id
                    AND decision.at >= (SELECT observed_at FROM clock_observation)
                    AND (:same OR NOT EXISTS (SELECT 1 FROM lock_head h JOIN lock_decision d
                        ON d.id=h.decision_id WHERE h.contest_id=w.contest_id
                        AND (d.deadline IS NULL OR decision.at>=d.deadline))) RETURNING w.id""",
                    id=wid,
                    setup=setup,
                    same=sr["id"] == previous["slate_revision_id"],
                )
                if not changed:
                    fail(
                        423,
                        "Membership or clock context changed at setup write; "
                        "original setup retained",
                    )
            else:
                run(
                    db,
                    "INSERT INTO workspace(id,contest_id,setup_id) VALUES (:id,:cid,:setup)",
                    id=wid,
                    cid=cid,
                    setup=setup,
                )
            return {"workspace_id": wid, "revision": w["revision"] + 1 if workspace else 0}

        return self.command(
            owner, key, {"setup": data.model_dump(mode="json"), "workspace": workspace}, apply
        )

    def owned(self, db: Connection, wid: str, owner: str) -> dict:
        w = one(
            db,
            "SELECT w.*,c.name,c.yahoo_id,c.season,c.round FROM workspace w "
            "JOIN contest c ON c.id=w.contest_id WHERE w.id=:id AND c.owner_id=:owner",
            id=wid,
            owner=owner,
        )
        if not w:
            fail(404, "Workspace not found")
        return w

    def games(self, db: Connection, setup: str) -> list[dict]:
        return many(
            db,
            "SELECT g.*,o.kickoff FROM setup_revision s JOIN slate_game m "
            "ON m.slate_revision_id=s.slate_revision_id JOIN game g ON g.id=m.game_id "
            "JOIN schedule_observation o ON o.game_id=g.id AND o.schedule_id=s.schedule_id "
            "WHERE s.id=:id ORDER BY g.event_key",
            id=setup,
        )

    def stage(self, wid: str, owner: str, raw: bytes, filename: str) -> dict:
        # Parse outside the write transaction against a single immutable setup.
        with self.engine.connect() as db:
            w = self.owned(db, wid, owner)
            games = self.games(db, w["setup_id"])
            slate = one(db, "SELECT * FROM slate WHERE contest_id=:cid", cid=w["contest_id"])
        try:
            parsed = parse_yahoo(raw, games)
            errors = []
        except ValueError as exc:
            parsed, errors = {"rows": [], "summary": {}}, [str(exc)]
        blob_hash = digest(raw)
        fingerprint = digest(canonical([blob_hash, w["setup_id"], PARSER_VERSION]).encode())
        with self.engine.begin() as db:
            run(db, "SELECT pg_advisory_xact_lock(hashtextextended(:hash,0))", hash=fingerprint)
            existing = one(
                db, "SELECT id FROM import_batch WHERE fingerprint=:hash", hash=fingerprint
            )
            if existing:
                return {"batch_id": str(existing["id"])}
            capture, batch = uid(), uid()
            run(
                db,
                "INSERT INTO raw_blob VALUES (:hash,:raw,:length,'text/csv') "
                "ON CONFLICT DO NOTHING",
                hash=blob_hash,
                raw=raw,
                length=len(raw),
            )
            run(
                db,
                "INSERT INTO source_capture(id,blob_hash,filename) VALUES (:id,:hash,:name)",
                id=capture,
                hash=blob_hash,
                name=filename[:200],
            )
            run(
                db,
                "INSERT INTO import_batch(id,setup_id,capture_id,parser_version,fingerprint) "
                "VALUES (:id,:setup,:capture,:parser,:hash)",
                id=batch,
                setup=w["setup_id"],
                capture=capture,
                parser=PARSER_VERSION,
                hash=fingerprint,
            )
            run(
                db,
                "INSERT INTO import_validation(batch_id,summary,errors) "
                "VALUES (:id,CAST(:summary AS jsonb),CAST(:errors AS jsonb))",
                id=batch,
                summary=canonical(parsed["summary"]),
                errors=canonical(errors),
            )
            for row in parsed["rows"]:
                # Identity evidence changes create another subject; old selections remain bound.
                signature = digest(canonical([row["name"].casefold(), row["position"]]).encode())
                run(
                    db,
                    "INSERT INTO subject VALUES (:id,:key,:signature) ON CONFLICT DO NOTHING",
                    id=uid(),
                    key=row["yahoo_id"],
                    signature=signature,
                )
                subject = one(
                    db,
                    "SELECT id FROM subject WHERE provider_key=:key AND identity_signature=:sig",
                    key=row["yahoo_id"],
                    sig=signature,
                )
                run(
                    db,
                    "INSERT INTO slate_entry VALUES (:id,:slate,:key) ON CONFLICT DO NOTHING",
                    id=uid(),
                    slate=slate["id"],
                    key=row["yahoo_id"],
                )
                entry = one(
                    db,
                    "SELECT id FROM slate_entry WHERE slate_id=:slate AND yahoo_id=:key",
                    slate=slate["id"],
                    key=row["yahoo_id"],
                )
                run(
                    db,
                    "INSERT INTO pool_row VALUES (:id,:batch,:entry,:subject,:game,:line,:end,"
                    "CAST(:raw AS jsonb),CAST(:normalized AS jsonb),CAST(:issues AS jsonb))",
                    id=uid(),
                    batch=batch,
                    entry=entry["id"],
                    subject=subject["id"],
                    game=row["game_id"],
                    line=row["line"],
                    end=row["line_end"],
                    raw=canonical(row["raw"]),
                    normalized=canonical(
                        {k: v for k, v in row.items() if k not in {"raw", "issues"}}
                    ),
                    issues=canonical(row["issues"]),
                )
            return {"batch_id": batch}

    def pool(self, db: Connection, batch: str | None) -> list[dict]:
        rows = many(
            db, "SELECT * FROM pool_row WHERE batch_id=:id ORDER BY physical_line", id=batch
        )
        return [
            {
                **r["normalized"],
                "row_id": str(r["id"]),
                "entry_id": str(r["entry_id"]),
                "subject_id": str(r["subject_id"]),
                "issues": r["issues"],
                "raw": r["raw"],
            }
            for r in rows
        ]

    def preview(self, wid: str, owner: str, batch: str) -> dict:
        with self.engine.connect() as db:
            w = self.owned(db, wid, owner)
            b = one(
                db,
                "SELECT b.*,v.summary,v.errors,c.imported_at,c.provider_updated_at "
                "FROM import_batch b JOIN import_validation v ON v.batch_id=b.id "
                "JOIN source_capture c ON c.id=b.capture_id "
                "JOIN setup_revision s ON s.id=b.setup_id WHERE b.id=:id AND s.contest_id=:cid",
                id=batch,
                cid=w["contest_id"],
            )
            if not b:
                fail(404, "Import not found")
            rows = self.pool(db, batch)
            active = {
                r["yahoo_id"]: r for r in self.pool(db, w["active_pool_id"]) if not r["issues"]
            }
            new = {r["yahoo_id"]: r for r in rows if not r["issues"]}
            changes = {
                "added": sorted(new.keys() - active.keys()),
                "removed": sorted(active.keys() - new.keys()),
                "changed": [
                    k
                    for k in new.keys() & active.keys()
                    if any(
                        new[k][f] != active[k][f]
                        for f in ("salary_cents", "subject_id", "position", "team", "game_id")
                    )
                ],
            }
            return {
                **b,
                "rows": rows,
                "changes": changes,
                "setup_matches": b["setup_id"] == w["setup_id"],
            }

    def activate(self, wid: str, owner: str, key: str, data: Activation) -> dict:
        def apply(db: Connection) -> dict:
            w = self.lock(db, wid, owner, data.expected_revision)
            batch = one(
                db,
                "SELECT b.*,v.errors,v.summary FROM import_batch b JOIN import_validation v "
                "ON v.batch_id=b.id WHERE b.id=:id",
                id=data.batch_id,
            )
            if (
                not batch
                or batch["setup_id"] != w["setup_id"]
                or batch["revision"] != data.batch_revision
            ):
                fail(
                    409,
                    "Validated import no longer matches setup or batch revision. "
                    "Reimport to revalidate.",
                )
            if batch["errors"] or not batch["summary"].get("eligible_ids"):
                fail(422, "Import has file errors or no structurally eligible entries")
            run(
                db,
                "UPDATE workspace SET active_pool_id=:batch,revision=revision+1 WHERE id=:id",
                id=wid,
                batch=data.batch_id,
            )
            return {"workspace_id": wid, "revision": w["revision"] + 1}

        return self.command(owner, key, {"activate": data.model_dump(), "workspace": wid}, apply)

    def assignments(self, db: Connection, draft: str | None) -> dict:
        rows = many(
            db,
            "SELECT a.*,r.normalized FROM draft_assignment a JOIN pool_row r "
            "ON r.id=a.source_row_id WHERE a.draft_id=:id",
            id=draft,
        )
        return {
            r["slot"]: {
                **r["normalized"],
                "entry_id": str(r["entry_id"]),
                "subject_id": str(r["subject_id"]),
                "row_id": str(r["source_row_id"]),
            }
            for r in rows
        }

    def save(self, wid: str, owner: str, key: str, data: DraftCommand) -> dict:
        def apply(db: Connection) -> dict:
            w = self.lock(db, wid, owner, data.expected_revision)
            b = one(db, "SELECT setup_id FROM import_batch WHERE id=:id", id=w["active_pool_id"])
            if not b or b["setup_id"] != w["setup_id"]:
                fail(422, "Activate a pool validated against the current setup before editing")
            active = {
                r["entry_id"]: r for r in self.pool(db, w["active_pool_id"]) if not r["issues"]
            }
            assignments = self.assignments(db, w["draft_id"])
            for operation in data.operations:
                slot = operation.slot
                if operation.op == "remove":
                    if slot not in assignments:
                        fail(422, "Cannot remove an empty slot")
                    del assignments[slot]
                    continue
                if operation.op == "add" and slot in assignments:
                    fail(409, "Occupied slot requires explicit replacement")
                if operation.op == "replace" and slot not in assignments:
                    fail(409, "Replacement requires an occupied slot")
                row = active.get(operation.entry_id)
                if not row or row["position"] not in SLOTS[slot]:
                    fail(422, "Entry is unknown, quarantined, or ineligible for that slot")
                if any(
                    r["entry_id"] == operation.entry_id for s, r in assignments.items() if s != slot
                ):
                    fail(422, "An entry cannot occupy two slots")
                assignments[slot] = row
            return self.write_draft(db, w, assignments, [o.model_dump() for o in data.operations])

        return self.command(owner, key, {"save": data.model_dump(), "workspace": wid}, apply)

    def write_draft(self, db, w, assignments, operations, reconciliation_policy=None):
        policy = reconciliation_policy or late_swap.context(
            db, w, self.assignments(db, w["draft_id"])
        )
        current_pool = {
            p["entry_id"]: p for p in self.pool(db, w["active_pool_id"]) if not p["issues"]
        }
        current_pool.update({p["entry_id"]: p for p in policy["fixed"].values()})
        effective = {
            slot: (
                current_pool.get(p["entry_id"], p)
                if late_swap.identity(current_pool.get(p["entry_id"])) == late_swap.identity(p)
                else p
            )
            for slot, p in assignments.items()
        }
        late_swap.validate_change(policy, effective)
        draft = uid()
        run(
            db,
            "INSERT INTO draft_revision(id,workspace_id,parent_id,operations) "
            "VALUES (:id,:wid,:parent,CAST(:ops AS jsonb))",
            id=draft,
            wid=str(w["id"]),
            parent=w["draft_id"],
            ops=canonical(operations),
        )
        for slot, r in assignments.items():
            run(
                db,
                "INSERT INTO draft_assignment VALUES (:draft,:slot,:entry,:subject,:row)",
                draft=draft,
                slot=slot,
                entry=r["entry_id"],
                subject=r["subject_id"],
                row=r["row_id"],
            )
        written = self.advance(db, w, "draft_id", draft, policy)
        return {
            "workspace_id": str(w["id"]),
            "revision": written["revision"],
            "draft_id": draft,
            "decision_at": written["decision_at"].isoformat(),
        }

    def advance(self, db, w, head, identifier, policy=None):
        assert head in {"draft_id", "entered_id"}
        policy = policy or late_swap.context(db, w, self.assignments(db, w["draft_id"]))
        late_swap.require(policy)
        return self.conditional_head(db, w, head, identifier, policy)

    def conditional_head(self, db, w, head, identifier, policy):
        assert head in {"draft_id", "entered_id"}
        written = one(
            db,
            f"""WITH decision AS MATERIALIZED (SELECT clock_timestamp() AS at)
            UPDATE workspace w SET {head}=:identifier,revision=w.revision+1,decision_at=decision.at
            FROM decision WHERE w.id=:id AND w.revision=:expected
            AND decision.at >= (SELECT observed_at FROM clock_observation)
            AND (w.decision_at IS NULL OR decision.at>=w.decision_at)
            AND NOT EXISTS (SELECT 1 FROM lock_head h JOIN lock_decision d ON d.id=h.decision_id
                JOIN setup_revision s ON s.id=w.setup_id JOIN slate_game sg
                ON sg.slate_revision_id=s.slate_revision_id AND sg.game_id=h.game_id
                WHERE h.contest_id=w.contest_id AND (d.deadline IS NULL OR
                ((decision.at>=d.deadline) !=
                 (CAST(d.game_id AS text) = ANY(CAST(:started AS text[]))))))
            AND NOT EXISTS (SELECT 1 FROM setup_revision s JOIN schedule_observation o
                ON o.schedule_id=s.schedule_id WHERE s.id=w.setup_id AND o.kickoff IS NULL)
            RETURNING w.revision,w.decision_at""",
            identifier=identifier,
            id=str(w["id"]),
            expected=w["revision"],
            started=policy["started"],
        )
        if not written:
            fail(
                423,
                "Lock context changed at final write or clock/schedule uncertain; "
                "refresh and reconcile",
            )
        return written

    def read(self, wid: str, owner: str) -> dict:
        late_swap.observe(self.engine)
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as db:
            w = self.owned(db, wid, owner)
            setup = one(
                db,
                "SELECT s.*,r.profile,r.provenance,r.created_at AS confirmed_at "
                "FROM setup_revision s JOIN rule_revision r ON r.id=s.rule_id WHERE s.id=:id",
                id=w["setup_id"],
            )
            players = self.pool(db, w["active_pool_id"])
            accepted = one(
                db,
                "SELECT c.report FROM analysis_manifest m "
                "JOIN coverage_report c ON c.id=m.coverage_id "
                "WHERE m.id=:id AND m.setup_id=:setup AND m.pool_id=:pool "
                "AND m.mapping_id IS NOT DISTINCT FROM CAST(:mapping AS uuid) "
                "AND m.availability_id IS NOT DISTINCT FROM CAST(:availability AS uuid)",
                id=w["manifest_id"],
                setup=w["setup_id"],
                pool=w["active_pool_id"],
                mapping=w["mapping_id"],
                availability=w["availability_id"],
            )
            projections = (
                {p["row_id"]: p for p in accepted["report"]["players"]} if accepted else {}
            )
            for player in players:
                projected = projections.get(player["row_id"])
                player["projection"] = projected["projection"] if projected else None
            assignments = self.assignments(db, w["draft_id"])
            policy = late_swap.context(db, w, assignments)
            active = {r["entry_id"]: r for r in players if not r["issues"]}
            active.update({p["entry_id"]: p for p in policy["fixed"].values() if p.get("entry_id")})
            issues = []
            effective = [active.get(r["entry_id"]) for r in assignments.values()]
            resolved = all(
                c and c["subject_id"] == r["subject_id"] and isinstance(c.get("salary_cents"), int)
                for c, r in zip(effective, assignments.values())
            )
            total = sum(c["salary_cents"] for c in effective) if resolved else None
            if len(assignments) < 9:
                issues.append(f"{9-len(assignments)} empty slots")
            if total is not None and total > 20000:
                issues.append("Over budget; this draft can still be saved")
            teams = Counter(r["team"] for r in effective if r) if resolved else Counter()
            if len(teams) < 3:
                issues.append("At least three teams required for a complete lineup")
            if max(teams.values(), default=0) > 6:
                issues.append("More than six selections from one team")
            for slot, row in assignments.items():
                current = active.get(row["entry_id"])
                row["current"] = current if current and current.get("subject_id") else None
                row["concerns"] = []
                if not current or current["subject_id"] != row["subject_id"]:
                    row["concerns"].append(
                        "Unresolved in active pool; original selection preserved"
                    )
                elif any(
                    current[k] != row[k] for k in ("salary_cents", "position", "team", "game_id")
                ):
                    row["concerns"].append(
                        "Active pool facts changed; selection-time facts preserved"
                    )
                if current and current["injury"]:
                    row["concerns"].append("Current injury designation: " + current["injury"])
                issues.extend(f"{slot}: {issue}" for issue in row["concerns"])
            games = self.games(db, w["setup_id"])
            bound = one(
                db, "SELECT setup_id FROM import_batch WHERE id=:id", id=w["active_pool_id"]
            )
            ready = bool(bound and bound["setup_id"] == w["setup_id"])
            from server.analysis import items
            from server.decision import environments

            entered = one(db, "SELECT * FROM entered_revision WHERE id=:id", id=w["entered_id"])

            def signature(a: dict) -> dict:
                return {s: (p["entry_id"], p["subject_id"]) for s, p in a.items()}

            latest = one(db, "SELECT operations FROM draft_revision WHERE id=:id", id=w["draft_id"])
            return {
                **w,
                "environments": environments(db, w),
                "entered": entered,
                "entered_status": (
                    "none"
                    if not entered
                    else (
                        "matches"
                        if signature(assignments) == signature(entered["assignments"])
                        else "differs"
                    )
                ),
                "undo_available": bool(
                    latest
                    and not any(
                        o.get("action") in {"undo", "reconcile"} for o in latest["operations"]
                    )
                ),
                "preferences": items(db, "preference_revision", w["preference_id"]),
                "setup": setup,
                "games": games,
                "players": players,
                "assignments": assignments,
                "salary_cents": total,
                "remaining_cents": 20000 - total if total is not None else None,
                "issues": issues,
                "deadline": min(
                    (d for g, d in policy["deadlines"].items() if d and g not in policy["started"]),
                    default=None,
                ),
                "locked": bool(policy["blockers"] or policy["all_locked"]),
                "late_swap": policy,
                "pool_matches_setup": ready,
                "imports": many(
                    db,
                    "SELECT b.id,b.created_at FROM import_batch b JOIN setup_revision s "
                    "ON s.id=b.setup_id WHERE s.contest_id=:cid ORDER BY b.created_at DESC",
                    cid=w["contest_id"],
                ),
            }
