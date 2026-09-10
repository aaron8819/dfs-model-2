"""Capture once, solve outside transactions, validate and apply the exact saved result."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from time import perf_counter

from pydantic import Field
from sqlalchemy.engine import Connection

from server import late_swap
from server.analysis import Expected, items
from server.decision import environments
from server.persistence import canonical, one, run, uid
from server.recommendation.contracts import (
    Assignment,
    Entry,
    SolveInput,
    SolveResult,
    exact_units,
    validate_input,
)
from server.recommendation.runner import BusyError, run_solve
from server.validator.lineup import validate_result
from server.workspace import WorkspaceService, fail


class Alternatives(Expected):
    include: list[str] = Field(default_factory=list, max_length=9)
    exclude: list[str] = Field(default_factory=list, max_length=100)


class ApplyCandidate(Expected):
    candidate_index: int = Field(default=0, ge=0, le=2)


class CompletionService:
    def __init__(self, workspace: WorkspaceService) -> None:
        self.workspace, self.engine = workspace, workspace.engine
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="completion")
        self.cancel = threading.Event()

    def close(self) -> None:
        self.cancel.set()
        self.executor.shutdown(wait=True)

    def snapshot(self, db: Connection, w: dict) -> dict:
        m = one(
            db,
            "SELECT m.*,c.report,b.interpretation FROM analysis_manifest m "
            "JOIN coverage_report c ON c.id=m.coverage_id JOIN "
            "projection_batch b ON b.id=m.batch_id WHERE m.id=:id",
            id=w["manifest_id"],
        )
        if not m or any(
            m[a] != w[b]
            for a, b in [
                ("setup_id", "setup_id"),
                ("pool_id", "active_pool_id"),
                ("mapping_id", "mapping_id"),
                ("availability_id", "availability_id"),
            ]
        ):
            fail(422, "Review and activate projections for the current Yahoo pool and evidence")
        return m

    def assemble(
        self, db: Connection, w: dict, at: datetime, options: dict | None = None, lock_context=None
    ) -> SolveInput:
        options = options or {}
        alternatives = options.get("action") == "alternatives"
        m = self.snapshot(db, w)
        accepted = {p["row_id"]: p for p in m["report"]["players"]}
        players = []
        for p in self.workspace.pool(db, m["pool_id"]):
            if p["issues"]:
                continue
            evidence = accepted.get(p["row_id"])
            if not evidence or evidence["subject_id"] != p["subject_id"]:
                fail(422, "Accepted projection evidence does not bind this canonical Yahoo row")
            players.append(
                {**p, "projection": evidence["projection"], "available": evidence["available"]}
            )
        assignments = self.workspace.assignments(db, w["draft_id"])
        policy = lock_context or late_swap.context(db, w, assignments)
        late_swap.require(policy)
        fixed = policy["fixed"]
        fixed_entries = {p["entry_id"] for p in fixed.values()}
        current_projections = {(p["entry_id"], p["subject_id"]): p["projection"] for p in players}
        players = [p for p in players if p["entry_id"] not in fixed_entries]
        players.extend(
            {
                **p,
                "projection": current_projections.get((p["entry_id"], p["subject_id"])),
                "available": True,
            }
            for p in fixed.values()
        )
        pool = {p["entry_id"]: p for p in players}
        assignments = self.workspace.assignments(db, w["draft_id"])
        prefs = items(db, "preference_revision", w["preference_id"])
        for p in ([] if alternatives else list(assignments.values())) + prefs:
            current = pool.get(p["entry_id"])
            if not current or current["subject_id"] != p["subject_id"]:
                fail(422, "Selected or preferred subject is unresolved; original choice preserved")
        data = SolveInput(
            manifest=str(m["id"]),
            evaluation_time=at.isoformat(),
            lock_evidence="Per-game entered authority v1; " + str(w["entered_id"]),
            fixed=tuple(Assignment(slot=s, entry=p["yahoo_id"]) for s, p in fixed.items()),
            entries=tuple(
                Entry(
                    key=p["yahoo_id"],
                    team=p["team"],
                    game=p["game_id"],
                    positions=(p["position"],),
                    salary_cents=p["salary_cents"],
                    projection=p["projection"],
                    available=p["available"],
                    locked=p["game_id"] in policy["started"],
                )
                for p in players
            ),
            slate_games=tuple(str(g["id"]) for g in self.workspace.games(db, w["setup_id"])),
            working=tuple(
                Assignment(slot=s, entry=pool[p["entry_id"]]["yahoo_id"])
                for s, p in assignments.items()
                if p["entry_id"] in pool and pool[p["entry_id"]]["subject_id"] == p["subject_id"]
            ),
            required=(
                ()
                if alternatives
                else tuple(pool[p["entry_id"]]["yahoo_id"] for p in assignments.values())
            ),
            include=tuple(options.get("include", [])),
            exclude=tuple(options.get("exclude", [])),
            keep=tuple(pool[p["entry_id"]]["yahoo_id"] for p in prefs if p["value"] == "keep"),
            avoid=tuple(pool[p["entry_id"]]["yahoo_id"] for p in prefs if p["value"] == "avoid"),
        )
        try:
            validate_input(data)
        except ValueError as exc:
            fail(422, str(exc))
        return data

    def prelock(self, db: Connection, w: dict) -> datetime:
        policy = late_swap.context(db, w, self.workspace.assignments(db, w["draft_id"]))
        late_swap.require(policy)
        return policy["at"]

    def expire(self, db: Connection) -> dict:
        lease = one(db, "SELECT * FROM solve_lease WHERE singleton FOR UPDATE")
        expired = one(
            db, "SELECT expires_at<=clock_timestamp() AS expired FROM solve_lease WHERE singleton"
        )["expired"]
        if lease["request_id"] and expired:
            run(
                db,
                "INSERT INTO recommendation_result(request_id,status,validation) "
                "VALUES (:id,'interrupted','{\"reason\":\"Worker lease expired; no "
                "automatic retry\"}') ON CONFLICT DO NOTHING",
                id=lease["request_id"],
            )
            run(
                db,
                "UPDATE solve_lease SET request_id=NULL,token=NULL,expires_at=NULL WHERE singleton",
            )
            lease["request_id"] = None
        return lease

    def submit(self, wid: str, owner: str, key: str, data: Expected) -> dict:
        token = uid()
        options = (
            {
                "action": "alternatives",
                "include": data.include,
                "exclude": data.exclude,
                "policy": "exclude-up-to-two-leading-replaceable-members-v1",
                "max_candidates": 3,
                "diversity": "distinct membership; visible single-player exclusions",
            }
            if isinstance(data, Alternatives)
            else {"action": "complete"}
        )

        def action(db: Connection) -> dict:
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            lease = self.expire(db)
            if lease["request_id"]:
                fail(409, "A completion is already running; wait for its result")
            at = self.prelock(db, w)
            capture_locks = late_swap.context(db, w, self.workspace.assignments(db, w["draft_id"]))
            snapshot = self.assemble(db, w, at, options, capture_locks)
            context = {
                "revision": w["context_revision"],
                "environments": environments(db, w),
                "locks": capture_locks,
            }
            rid = uid()
            run(
                db,
                "INSERT INTO "
                "recommendation_request(id,workspace_id,manifest_id,draft_id,"
                "preference_id,bound_revision,input,limits,token,options,context) "
                "VALUES "
                "(:id,:wid,:manifest,:draft,:preference,:revision,CAST(:input AS "
                "jsonb),CAST(:limits AS jsonb),:token,CAST(:options AS jsonb),"
                "CAST(:context AS jsonb))",
                limits=canonical({"budget_seconds": 30, "hard_seconds": 35}),
                id=rid,
                wid=wid,
                manifest=w["manifest_id"],
                draft=w["draft_id"],
                preference=w["preference_id"],
                revision=w["revision"],
                input=snapshot.model_dump_json(),
                token=token,
                options=canonical(options),
                context=canonical(context),
            )
            run(
                db,
                "UPDATE solve_lease SET "
                "request_id=:id,token=:token,expires_at=clock_timestamp()+interval "
                "'45 seconds' WHERE singleton",
                id=rid,
                token=token,
            )
            return {"request_id": rid}

        receipt = self.workspace.command(
            owner, key, {"complete": data.model_dump(), "workspace": wid}, action
        )
        with self.engine.connect() as db:
            request = one(
                db, "SELECT * FROM recommendation_request WHERE id=:id", id=receipt["request_id"]
            )
        # Only the capturing process launches work; a retried receipt never reruns it.
        if str(request["token"]) == token:
            self.executor.submit(self.execute, request)
        return receipt

    def execute(self, request: dict) -> None:
        stop = threading.Event()
        lost = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(5):
                try:
                    with self.engine.begin() as db:
                        ok = one(
                            db,
                            "UPDATE solve_lease SET expires_at=clock_timestamp()+interval '45 "
                            "seconds' WHERE singleton AND request_id=:id AND token=:token AND "
                            "expires_at>clock_timestamp() RETURNING token",
                            id=request["id"],
                            token=request["token"],
                        )
                    if not ok or self.cancel.is_set():
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()

        class Cancel:
            def is_set(inner) -> bool:
                return self.cancel.is_set() or lost.is_set()

        result, validation, status = None, {}, "failed"
        candidates = []
        attempts = []
        try:
            data = SolveInput.model_validate_json(canonical(request["input"]))
            started = perf_counter()
            candidates = []
            solved = run_solve(data, cancel=Cancel())
            seconds = validate_result(data, solved)
            result = solved.model_dump(mode="json")
            if solved.assignments:
                candidates.append(
                    {
                        "input": data.model_dump(mode="json"),
                        "result": result,
                        "extra_exclusion": None,
                    }
                )
            # Same runner, lease and one total 30/35-second budget, including process startup.
            # Only suggest exclusions after the base proof; never mislabel a stronger found result.
            if request["options"].get("action") == "alternatives" and solved.primary_proven:
                protected = set(data.keep + data.include) | {a.entry for a in data.fixed}
                facts = {e.key: e for e in data.entries}
                choices = sorted(
                    (a.entry for a in solved.assignments if a.entry not in protected),
                    key=lambda k: (-exact_units(facts[k].projection), k),
                )[:2]
                memberships = {frozenset(a.entry for a in solved.assignments)}
                for choice in choices:
                    elapsed = perf_counter() - started
                    if elapsed >= 30 or Cancel().is_set():
                        break
                    variant = data.model_copy(update={"exclude": data.exclude + (choice,)})
                    alt = run_solve(
                        variant,
                        budget_seconds=30 - elapsed,
                        hard_seconds=35 - elapsed,
                        cancel=Cancel(),
                    )
                    validate_result(variant, alt)
                    attempts.append(
                        {
                            "excluded": choice,
                            "status": alt.status,
                            "termination": alt.termination,
                            "primary_proven": alt.primary_proven,
                            "tie_complete": alt.tie_complete,
                        }
                    )
                    members = frozenset(a.entry for a in alt.assignments)
                    if members and members not in memberships:
                        memberships.add(members)
                        candidates.append(
                            {
                                "input": variant.model_dump(mode="json"),
                                "result": alt.model_dump(mode="json"),
                                "extra_exclusion": choice,
                            }
                        )
            validation = {
                "valid": True,
                "version": 1,
                "seconds": seconds,
                "alternative_attempts": attempts,
                "shared_budget_exhausted": perf_counter() - started >= 30,
                "request_seconds": perf_counter() - started,
            }
            status = (
                "interrupted"
                if Cancel().is_set()
                else "ready" if solved.assignments else solved.status.lower()
            )
        except BusyError:
            status, validation = "busy", {
                "reason": "Local solver process is busy; submit a new request explicitly"
            }
        except Exception:
            logging.getLogger(__name__).exception("Completion failed for request %s", request["id"])
            validation = {
                "reason": "Completion failed; no draft changes. Inspect server diagnostics."
            }
        finally:
            stop.set()
            thread.join()
        with self.engine.begin() as db:
            lease = one(db, "SELECT * FROM solve_lease WHERE singleton FOR UPDATE")
            ok = one(
                db, "SELECT expires_at>clock_timestamp() AS valid FROM solve_lease WHERE singleton"
            )["valid"]
            if lease["request_id"] == request["id"] and lease["token"] == request["token"] and ok:
                run(
                    db,
                    "INSERT INTO "
                    "recommendation_result(request_id,status,result,validation,candidates) VALUES "
                    "(:id,:status,CAST(:result AS jsonb),CAST(:validation AS jsonb),CAST(:c"
                    "andidates AS jsonb)) "
                    "ON CONFLICT DO NOTHING",
                    id=request["id"],
                    status=status,
                    result=canonical(result),
                    validation=canonical(validation),
                    candidates=canonical(candidates),
                )
                run(
                    db,
                    "UPDATE solve_lease SET request_id=NULL,token=NULL,expires_at=NULL "
                    "WHERE singleton",
                )

    def read(self, wid: str, owner: str, rid: str) -> dict:
        with self.engine.begin() as db:
            w = self.workspace.owned(db, wid, owner)
            self.expire(db)
            request = one(
                db,
                "SELECT * FROM recommendation_request WHERE id=:id AND workspace_id=:wid",
                id=rid,
                wid=wid,
            )
            if not request:
                fail(404, "Completion not found")
            result = one(db, "SELECT * FROM recommendation_result WHERE request_id=:id", id=rid)
            m = one(
                db,
                "SELECT c.report,b.interpretation FROM analysis_manifest m JOIN "
                "coverage_report c ON c.id=m.coverage_id JOIN projection_batch b "
                "ON b.id=m.batch_id WHERE m.id=:id",
                id=request["manifest_id"],
            )
            pool = {p["yahoo_id"]: p for p in m["report"]["players"] if not p["issues"]}
            previous = {a["entry"]: a["slot"] for a in request["input"]["working"]}
            original = self.workspace.assignments(db, request["draft_id"])
            saved_input = SolveInput.model_validate_json(canonical(request["input"]))
            input_facts = {e.key: e for e in saved_input.entries}
            pool.update(
                {
                    p["yahoo_id"]: {
                        **p,
                        "projection": input_facts[p["yahoo_id"]].projection,
                        "concerns": ["Fixed entered assignment; pregame projection only"],
                    }
                    for p in request["context"].get("locks", {}).get("fixed", {}).values()
                }
            )
            preview = []
            if result and result["result"]:
                preview = [
                    {
                        **pool[a["entry"]],
                        "slot": a["slot"],
                        "previous_slot": previous.get(a["entry"]),
                    }
                    for a in result["result"]["assignments"]
                ]
            candidates = []
            saved_input = SolveInput.model_validate_json(canonical(request["input"]))
            facts = {e.key: e for e in saved_input.entries}
            fixed_keys = {a.entry for a in saved_input.fixed}
            editable_previous = set(previous) - fixed_keys
            comparable = len(previous) == 9 and all(
                facts[k].projection is not None for k in editable_previous
            )
            baseline = (
                sum(exact_units(facts[k].projection) for k in editable_previous)
                if comparable
                else None
            )
            for index, candidate in enumerate(result["candidates"] if result else []):
                value = candidate["result"]
                members = {a["entry"] for a in value["assignments"]}
                candidates.append(
                    {
                        "index": index,
                        "result": value,
                        "extra_exclusion": candidate["extra_exclusion"],
                        "constraint_name": (
                            pool[candidate["extra_exclusion"]]["name"]
                            if candidate["extra_exclusion"]
                            else None
                        ),
                        "preview": [
                            {
                                **pool[a["entry"]],
                                "slot": a["slot"],
                                "previous_slot": previous.get(a["entry"]),
                            }
                            for a in value["assignments"]
                        ],
                        "removed": [
                            p["name"]
                            for p in sorted(original.values(), key=lambda p: p["yahoo_id"])
                            if (p["entry_id"], p["subject_id"])
                            not in {(pool[k]["entry_id"], pool[k]["subject_id"]) for k in members}
                        ],
                        "delta_best_units": value["editable_units"]
                        - result["result"]["editable_units"],
                        "delta_draft_units": (
                            value["editable_units"] - baseline if baseline is not None else None
                        ),
                        "salary_delta_best_cents": value["salary_cents"]
                        - result["result"]["salary_cents"],
                        "salary_delta_draft_cents": (
                            value["salary_cents"] - sum(facts[k].salary_cents for k in previous)
                            if comparable
                            else None
                        ),
                    }
                )
            return {
                "candidates": candidates,
                "options": request["options"],
                "captured_context": request["context"],
                "newer_context": request["context"].get("revision", 0) != w["context_revision"],
                "fixed_conflicts": [
                    k for k in saved_input.avoid + saved_input.exclude if k in fixed_keys
                ],
                "request_id": rid,
                "status": result["status"] if result else "pending",
                "stale": request["bound_revision"] != w["revision"]
                or request["context"].get("locks", {}).get("started", [])
                != late_swap.context(db, w)["started"],
                "bound_revision": request["bound_revision"],
                "result": result["result"] if result else None,
                "validation": result["validation"] if result else None,
                "preview": preview,
                "interpretation": m["interpretation"],
            }

    def apply(self, wid: str, owner: str, key: str, rid: str, data: Expected) -> dict:
        def action(db: Connection) -> dict:
            w = self.workspace.lock(db, wid, owner, data.expected_revision)
            request = one(
                db,
                "SELECT q.*,r.result,r.status,r.candidates FROM recommendation_request q JOIN "
                "recommendation_result r ON r.request_id=q.id WHERE q.id=:id AND "
                "q.workspace_id=:wid",
                id=rid,
                wid=wid,
            )
            if (
                not request
                or request["bound_revision"] != w["revision"]
                or request["status"] != "ready"
            ):
                fail(409, "Preview is stale or not applicable; request a new completion")
            policy = late_swap.context(db, w)
            captured_locks = request["context"].get("locks", {})
            if any(
                captured_locks.get(k) != policy[k] for k in ("started", "decisions", "entered_id")
            ):
                fail(
                    409,
                    "Another game locked or lock evidence changed; "
                    "refresh, reconcile and request a new preview",
                )
            at = self.prelock(db, w)
            current = self.assemble(db, w, at, request["options"])
            saved = SolveInput.model_validate_json(canonical(request["input"]))
            if current.model_copy(update={"evaluation_time": saved.evaluation_time}) != saved:
                fail(409, "Canonical facts or preferences changed")
            index = getattr(data, "candidate_index", 0)
            candidates = request["candidates"]
            if candidates:
                if index >= len(candidates):
                    fail(422, "Saved candidate does not exist")
                candidate = candidates[index]
                variant = (
                    saved.model_copy(
                        update={"exclude": saved.exclude + (candidate["extra_exclusion"],)}
                    )
                    if candidate["extra_exclusion"]
                    else saved
                )
                if variant.model_dump(mode="json") != candidate["input"]:
                    fail(409, "Candidate constraints differ from captured request")
                result = SolveResult.model_validate_json(canonical(candidate["result"]))
                validate_result(variant, result)
            else:
                if index:
                    fail(422, "Saved candidate does not exist")
                result = SolveResult.model_validate_json(canonical(request["result"]))
                validate_result(saved, result)
            pool = {
                p["yahoo_id"]: p
                for p in self.workspace.pool(db, w["active_pool_id"])
                if not p["issues"]
            }
            pool.update({p["yahoo_id"]: p for p in policy["fixed"].values()})
            historical = self.workspace.assignments(db, w["draft_id"])
            chosen = {p["entry_id"]: p for p in historical.values()}
            assignments = {
                a.slot: chosen.get(pool[a.entry]["entry_id"], pool[a.entry])
                for a in result.assignments
            }
            return self.workspace.write_draft(
                db,
                w,
                assignments,
                [{"action": "apply-completion", "request_id": rid, "candidate_index": index}],
            )

        return self.workspace.command(
            owner, key, {"apply": rid, "workspace": wid, **data.model_dump()}, action
        )
