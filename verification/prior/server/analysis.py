"""Immutable analysis candidates; short conditional activation and preference transactions."""

import csv
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from server.persistence import canonical, digest, many, one, run, uid
from server.projections import PARSER, POLICY, POSITIONS, associate, name, parse
from server.workspace import WorkspaceService, fail


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Declaration(StrictModel):
    season: str = Field(min_length=1, max_length=80)
    period: str = Field(min_length=1, max_length=80)
    units: Literal["projected_points"] = "projected_points"
    scoring: Literal["half-ppr-baseline", "verified-yahoo", "incompatible"]
    evidence: str = Field(min_length=5, max_length=2000)
    source_context: str = Field(min_length=5, max_length=2000)
    # Per-file declarations are optional; their absence means the batch declaration applies.
    file_periods: dict[str, str] = Field(default_factory=dict)
    publication_times: dict[str, datetime | None] = Field(default_factory=dict)
    material_settings_match: bool


class Expected(StrictModel):
    expected_revision: int = Field(ge=0)


class ActivateAnalysis(Expected):
    candidate_id: str


class Preference(Expected):
    entry_id: str
    subject_id: str
    value: Literal["keep", "avoid", "clear"]
    remove_selected: bool = False


class Mapping(Expected):
    batch_id: str
    source_key: str
    entry_id: str
    subject_id: str
    reason: str = Field(min_length=5, max_length=2000)


class Availability(Expected):
    subject_id: str
    game_id: str
    evidence_type: Literal["designation", "participation", "practice", "resolution"]
    designation: Literal[
        "Out",
        "Inactive",
        "IR",
        "PUP",
        "NFI",
        "Suspended",
        "Reported absence",
        "Q",
        "D",
        "DTD",
        "Limited",
        "Active",
        "Unknown",
    ]
    source: str = Field(min_length=5, max_length=2000)
    source_time: datetime | None = None
    reason: str = Field(min_length=5, max_length=2000)
    resolves: list[str] = Field(default_factory=list)


def items(db, table: str, identifier) -> list[dict]:
    assert table in {"mapping_revision", "availability_revision", "preference_revision"}
    row = one(db, f"SELECT items FROM {table} WHERE id=:id", id=identifier)
    return row["items"] if row else []


class AnalysisService:
    def __init__(self, workspace: WorkspaceService):
        self.workspace = workspace
        self.engine = workspace.engine

    def state(self, wid, owner):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as db:
            w = self.workspace.owned(db, wid, owner)
            m = one(
                db,
                "SELECT m.*,c.report,b.interpretation,b.created_at AS imported_at,b.declaration "
                "FROM analysis_manifest m JOIN coverage_report c ON "
                "c.id=m.coverage_id JOIN projection_batch b ON b.id=m.batch_id "
                "WHERE m.id=:id",
                id=w["manifest_id"],
            )
            current = bool(
                m
                and all(
                    m[a] == w[b]
                    for a, b in [
                        ("setup_id", "setup_id"),
                        ("pool_id", "active_pool_id"),
                        ("mapping_id", "mapping_id"),
                        ("availability_id", "availability_id"),
                    ]
                )
            )
            assignments = self.workspace.assignments(db, w["draft_id"])
            prefs = items(db, "preference_revision", w["preference_id"])
            pool = (
                {p["entry_id"]: p for p in m["report"]["players"] if not p["issues"]}
                if current
                else {}
            )
            from server import late_swap

            fixed = {late_swap.identity(p) for p in late_swap.context(db, w)["fixed"].values()}
            issues = []
            for p in list(assignments.values()) + [p for p in prefs if p["value"] == "keep"]:
                if late_swap.identity(p) in fixed:
                    continue
                now = pool.get(p["entry_id"])
                if not now or now["subject_id"] != p["subject_id"]:
                    issues.append(p["name"] + ": unresolved current facts")
                elif now["projection"] is None or not now["available"]:
                    issues.append(p["name"] + ": missing projection or unavailable")
            return {
                "sources": many(
                    db,
                    "SELECT f.position,c.imported_at,c.provider_updated_at,c.filename "
                    "FROM projection_file f JOIN source_capture c ON c.id=f.capture_id "
                    "WHERE f.batch_id=:id ORDER BY f.position",
                    id=m["batch_id"] if m else None,
                ),
                "current": current,
                "analysis": m,
                "preferences": prefs,
                "issues": issues,
                "batches": many(
                    db,
                    "SELECT id,created_at FROM projection_batch WHERE "
                    "workspace_id=:wid ORDER BY created_at DESC",
                    wid=wid,
                ),
                "availability": items(db, "availability_revision", w["availability_id"]),
                "mappings": items(db, "mapping_revision", w["mapping_id"]),
            }

    def stage(self, wid, owner, files: dict[str, tuple[str, bytes]], context: Declaration):
        with self.engine.connect() as db:
            w = self.workspace.owned(db, wid, owner)
            pool_setup = one(
                db, "SELECT setup_id FROM import_batch WHERE id=:id", id=w["active_pool_id"]
            )
        if not pool_setup or pool_setup["setup_id"] != w["setup_id"]:
            fail(422, "Activate Yahoo for this setup first")
        errors, parsed = [], {}
        if set(files) != POSITIONS:
            errors.append("One QB, RB, WR, TE and DST file required together")
        if context.season != w["season"] or context.period != w["round"]:
            errors.append("Declared forecast period differs from confirmed contest")
        if any(v != context.period for v in context.file_periods.values()):
            errors.append("Inconsistent per-file forecast periods")
        compatible = context.scoring != "incompatible" and context.material_settings_match
        state = (
            (
                "Verified compatible"
                if context.scoring == "verified-yahoo"
                else "Accepted approximation"
            )
            if compatible
            else "Blocked"
        )
        if not compatible:
            errors.append("Material scoring incompatibility or unconfirmed settings")
        for position, (_, raw) in files.items():
            try:
                result = parse(raw, position)
            except (ValueError, UnicodeError, csv.Error) as exc:
                result = {"rows": [], "separators": [], "errors": [str(exc)]}
            for row in result["rows"]:
                row["source_key"] = f"{position}:{row['line']}"
            parsed[position] = result
            errors.extend(f"{position}: {e}" for e in result["errors"])
        rows = [r for f in parsed.values() for r in f["rows"]]
        subjects = [(name(r["name"]), r["team"]) for r in rows]
        if len(set(subjects)) != len(subjects):
            errors.append("Duplicate source subject; batch blocked")
        with self.engine.connect() as db:
            games = self.workspace.games(db, w["setup_id"])
            pool = self.workspace.pool(db, w["active_pool_id"])
        for position, content in parsed.items():
            agreements, contradictions = 0, 0
            for source in content["rows"]:
                corroborated = [
                    p
                    for p in pool
                    if not p["issues"]
                    and name(p["name"]) == name(source["name"])
                    and p["team"] == source["team"]
                    and p["opponent"] == source["opponent"]
                ]
                if len(corroborated) == 1:
                    if corroborated[0]["position"] == source["position"]:
                        agreements += 1
                    else:
                        contradictions += 1
            if contradictions and not agreements:
                errors.append(f"{position}: subjects disagree with the declared file position")
        opponents = {
            g[side]: g[other] for g in games for side, other in [("away", "home"), ("home", "away")]
        }
        if any(r["team"] in opponents and opponents[r["team"]] != r["opponent"] for r in rows):
            errors.append("Provider opponents disagree with dated slate; check forecast period")
        interpretation = {
            "state": state,
            "policy": POLICY,
            "evidence": context.evidence,
            "limitations": "Direct totals unchanged. Rare scoring components and provider "
            "methodology remain approximate; filenames do not prove period. "
            "Undetectable mislabeled periods remain possible.",
        }
        fingerprint = digest(
            canonical(
                [
                    wid,
                    w["setup_id"],
                    w["active_pool_id"],
                    PARSER,
                    context.model_dump(mode="json"),
                    {p: digest(f[1]) for p, f in files.items()},
                ]
            ).encode()
        )
        with self.engine.begin() as db:
            run(db, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key=fingerprint)
            old = one(db, "SELECT id FROM projection_batch WHERE fingerprint=:key", key=fingerprint)
            if old:
                return {"batch_id": str(old["id"])}
            bid = uid()
            run(
                db,
                "INSERT INTO "
                "projection_batch(id,workspace_id,setup_id,pool_id,fingerprin"
                "t,parser_version,declaration,interpretation,validation) "
                "VALUES (:id,:wid,:setup,:pool,:hash,:parser,CAST(:declaration AS "
                "jsonb),CAST(:interpretation AS jsonb),CAST(:validation AS jsonb))",
                id=bid,
                wid=wid,
                setup=w["setup_id"],
                pool=w["active_pool_id"],
                hash=fingerprint,
                parser=PARSER,
                declaration=canonical(context.model_dump(mode="json")),
                interpretation=canonical(interpretation),
                validation=canonical(
                    {
                        "errors": errors,
                        "records": len(rows),
                        "separators": sum(len(f["separators"]) for f in parsed.values()),
                        "observed_metadata": {
                            "period": None,
                            "scoring": None,
                            "units": "PROJ. FPTS column",
                            "opponents_reconciled": not any("opponents" in e for e in errors),
                        },
                    }
                ),
            )
            for position, (filename, raw) in files.items():
                capture, hash_ = uid(), digest(raw)
                run(
                    db,
                    "INSERT INTO raw_blob VALUES (:hash,:raw,:length,'text/csv') ON "
                    "CONFLICT DO NOTHING",
                    hash=hash_,
                    raw=raw,
                    length=len(raw),
                )
                run(
                    db,
                    "INSERT INTO source_capture(id,blob_hash,filename) VALUES "
                    "(:id,:hash,:filename)",
                    id=capture,
                    hash=hash_,
                    filename=filename[:200],
                )
                run(
                    db,
                    "INSERT INTO projection_file VALUES "
                    "(:bid,:position,:capture,CAST(:parsed AS jsonb))",
                    bid=bid,
                    position=position,
                    capture=capture,
                    parsed=canonical(parsed[position]),
                )
            return {"batch_id": bid}

    def batch(self, db, wid, bid):
        b = one(
            db, "SELECT * FROM projection_batch WHERE id=:id AND workspace_id=:wid", id=bid, wid=wid
        )
        if not b:
            fail(404, "Projection batch not found")
        b["files"] = many(
            db,
            "SELECT "
            "f.*,c.imported_at,c.provider_updated_at,c.filename,c.blob_hash "
            "FROM projection_file f JOIN source_capture c ON c.id=f.capture_id "
            "WHERE batch_id=:id ORDER BY position",
            id=bid,
        )
        return b

    def review(self, wid, owner, bid):
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as db:
            w = self.workspace.owned(db, wid, owner)
            b = self.batch(db, wid, bid)
            pool = self.workspace.pool(db, b["pool_id"])
            mappings = items(db, "mapping_revision", w["mapping_id"])
            availability = items(db, "availability_revision", w["availability_id"])
        rows = [r for f in b["files"] for r in f["parsed"]["rows"]]
        report = associate(rows, pool, [m for m in mappings if m["batch_id"] == bid], availability)
        candidate, coverage = uid(), uid()
        with self.engine.begin() as db:
            run(
                db,
                "INSERT INTO "
                "coverage_report(id,batch_id,mapping_id,availability_id,report) "
                "VALUES (:id,:batch,:mapping,:availability,CAST(:report AS jsonb))",
                id=coverage,
                batch=bid,
                mapping=w["mapping_id"],
                availability=w["availability_id"],
                report=canonical(report),
            )
            run(
                db,
                "INSERT INTO "
                "analysis_manifest(id,workspace_id,setup_id,pool_id,batch_id,"
                "mapping_id,availability_id,coverage_id,bound_revision,policy"
                "_version) "
                "VALUES "
                "(:id,:wid,:setup,:pool,:batch,:mapping,:availability,:coverage,:revision,:policy)",
                id=candidate,
                wid=wid,
                setup=b["setup_id"],
                pool=b["pool_id"],
                batch=bid,
                mapping=w["mapping_id"],
                availability=w["availability_id"],
                coverage=coverage,
                revision=w["revision"],
                policy=POLICY,
            )
        return {
            "candidate_id": candidate,
            "batch": b,
            "coverage": report,
            "expected_revision": w["revision"],
        }

    def activate(self, wid, owner, key, data: ActivateAnalysis):
        def action(db):
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            m = one(
                db,
                "SELECT m.*,b.validation FROM analysis_manifest m JOIN "
                "projection_batch b ON b.id=m.batch_id WHERE m.id=:id AND "
                "m.workspace_id=:wid",
                id=data.candidate_id,
                wid=wid,
            )
            if not m or any(
                m[a] != w[b]
                for a, b in [
                    ("setup_id", "setup_id"),
                    ("pool_id", "active_pool_id"),
                    ("mapping_id", "mapping_id"),
                    ("availability_id", "availability_id"),
                    ("bound_revision", "revision"),
                ]
            ):
                fail(409, "Review changed inputs before activation")
            if m["validation"]["errors"]:
                fail(422, "Projection batch is blocked: " + "; ".join(m["validation"]["errors"]))
            run(
                db,
                "UPDATE workspace SET manifest_id=:id,revision=revision+1 WHERE id=:wid",
                id=data.candidate_id,
                wid=wid,
            )
            return {"revision": w["revision"] + 1}

        return self.workspace.command(
            owner, key, {"analysis": data.model_dump(), "workspace": wid}, action
        )

    def resolve(self, wid, owner, key, data: Mapping | Availability):
        mapping = isinstance(data, Mapping)
        table, head = (
            ("mapping_revision", "mapping_id")
            if mapping
            else ("availability_revision", "availability_id")
        )

        def action(db):
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            pool = self.workspace.pool(db, w["active_pool_id"])
            current = items(db, table, w[head])
            value = data.model_dump(mode="json", exclude={"expected_revision"})
            if mapping:
                b = self.batch(db, wid, data.batch_id)
                source = next(
                    (
                        r
                        for f in b["files"]
                        for r in f["parsed"]["rows"]
                        if r["source_key"] == data.source_key
                    ),
                    None,
                )
                target = next(
                    (
                        p
                        for p in pool
                        if p["entry_id"] == data.entry_id
                        and p["subject_id"] == data.subject_id
                        and not p["issues"]
                    ),
                    None,
                )
                if (
                    not source
                    or not target
                    or any(source[k] != target[k] for k in ("team", "position", "opponent"))
                ):
                    fail(
                        422,
                        "Mapping needs a source and unambiguous Yahoo subject with "
                        "matching team, position and opponent",
                    )
                value["source_facts"], value["yahoo_facts"] = source, target
                current = [
                    m
                    for m in current
                    if (m["batch_id"], m["source_key"]) != (data.batch_id, data.source_key)
                ]
            else:
                if data.evidence_type == "practice" and data.designation not in {
                    "Limited",
                    "Unknown",
                }:
                    fail(422, "Practice evidence cannot establish a game participation designation")
                if data.source_time is not None and data.source_time.tzinfo is None:
                    fail(422, "Underlying source time must include a timezone")
                if not any(
                    p["subject_id"] == data.subject_id and p["game_id"] == data.game_id
                    for p in pool
                ):
                    fail(422, "Availability scope must identify a current subject and game")
                valid_refs = {
                    a["id"]
                    for a in current
                    if a["subject_id"] == data.subject_id and a["game_id"] == data.game_id
                } | {
                    p["row_id"]
                    for p in pool
                    if p["subject_id"] == data.subject_id and p["game_id"] == data.game_id
                }
                if not set(data.resolves) <= valid_refs or (
                    data.evidence_type == "resolution" and not data.resolves
                ):
                    fail(422, "Resolution requires applicable evidence references")
                value["id"] = uid()
                value["acquired_at"] = one(db, "SELECT clock_timestamp() AS at")["at"].isoformat()
            rid = uid()
            run(
                db,
                f"INSERT INTO {table}(id,workspace_id,parent_id,items) "
                "VALUES (:id,:wid,:parent,CAST(:items AS jsonb))",
                id=rid,
                wid=wid,
                parent=w[head],
                items=canonical(current + [value]),
            )
            run(
                db,
                f"UPDATE workspace SET {head}=:id,revision=revision+1 WHERE id=:wid",
                id=rid,
                wid=wid,
            )
            return {"revision": w["revision"] + 1}

        return self.workspace.command(
            owner,
            key,
            {"resolve": data.model_dump(mode="json"), "kind": table, "workspace": wid},
            action,
        )

    def preference(self, wid, owner, key, data: Preference):
        def action(db):
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            current = items(db, "preference_revision", w["preference_id"])
            row = next(
                (
                    p
                    for p in self.workspace.pool(db, w["active_pool_id"])
                    if p["entry_id"] == data.entry_id
                    and p["subject_id"] == data.subject_id
                    and not p["issues"]
                ),
                None,
            )
            if not row and data.value != "clear":
                fail(422, "Preference subject is unresolved; choose the current subject explicitly")
            old = next((p for p in current if p["entry_id"] == data.entry_id), None)
            if old and old["subject_id"] != data.subject_id:
                fail(
                    409,
                    "Clear the orphaned preference explicitly before choosing a different subject",
                )
            assignments = self.workspace.assignments(db, w["draft_id"])
            selected = [s for s, p in assignments.items() if p["entry_id"] == data.entry_id]
            from server import late_swap

            fixed_ids = {p["entry_id"] for p in late_swap.context(db, w)["fixed"].values()}
            if (
                data.value == "avoid"
                and selected
                and data.entry_id in fixed_ids
                and data.remove_selected
            ):
                fail(
                    423,
                    "Fixed entered player cannot be removed; uncheck removal to record Avoid only",
                )
            if data.value == "avoid" and selected and data.entry_id not in fixed_ids:
                if not data.remove_selected:
                    fail(409, "Selected entry: explicitly remove and Avoid, or cancel")
                assignments = {s: p for s, p in assignments.items() if s not in selected}
                self.workspace.write_draft(
                    db, w, assignments, [{"action": "remove-and-avoid", "entry_id": data.entry_id}]
                )
            updated = [p for p in current if p["entry_id"] != data.entry_id]
            if data.value != "clear":
                updated.append(
                    {
                        "entry_id": data.entry_id,
                        "subject_id": data.subject_id,
                        "value": data.value,
                        "source_row_id": row["row_id"],
                        "name": row["name"],
                    }
                )
            rid = uid()
            run(
                db,
                "INSERT INTO preference_revision(id,workspace_id,parent_id,items) "
                "VALUES (:id,:wid,:parent,CAST(:items AS jsonb))",
                id=rid,
                wid=wid,
                parent=w["preference_id"],
                items=canonical(updated),
            )
            run(
                db,
                "UPDATE workspace SET preference_id=:id,revision=revision+1 WHERE id=:wid",
                id=rid,
                wid=wid,
            )
            return {"preference_id": rid}

        return self.workspace.command(
            owner, key, {"preference": data.model_dump(), "workspace": wid}, action
        )
