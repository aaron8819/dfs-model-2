import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from server import application_test as boundary
from server.application_test import URL, activate, command
from server.ingestion_test import historical_games
from server.persistence import engine_for, one, run
from server.projections import number
from tools.completion_demo import completion_demo

client = boundary.client
settings = boundary.settings


def prepare(client, historical=False):
    setup, raw, files = completion_demo()
    if historical:
        root = Path("fixtures/private/historical")
        setup.update(
            season="2026",
            round="Week 1",
            games=[
                {"event_key": g["id"], **{k: v for k, v in g.items() if k != "id"}}
                for g in historical_games()
            ],
        )
        raw = (root / "raw/yahoo.csv").read_bytes()
        files = {
            p.stem.split("_")[-2]: (p.name, p.read_bytes())
            for p in (root / "acceptance/raw").glob("*/*.csv")
        }
    setup["yahoo_id"] = "completion-" + str(uuid4())
    response = command(client, "/api/workspaces", setup)
    assert response.status_code == 200, response.text
    wid = response.json()["workspace_id"]
    bid = client.post(f"/api/workspaces/{wid}/imports", files={"file": ("pool.csv", raw)}).json()[
        "batch_id"
    ]
    preview = client.get(f"/api/workspaces/{wid}/imports/{bid}").json()
    w = activate(client, wid, preview)
    context = dict(
        season=setup["season"],
        period=setup["round"],
        scoring="half-ppr-baseline",
        evidence="User confirmed Half PPR; documented FantasyPros main scoring"
        " settings match Yahoo baseline",
        source_context="Original exported projected points; declared contest forecast period",
        material_settings_match=True,
    )
    return w, files, context


def stage(client, w, files, context):
    result = client.post(
        f"/api/workspaces/{w['id']}/projections",
        files=[("files", value) for value in files.values()],
        data={"positions": json.dumps(list(files)), "declaration": json.dumps(context)},
    )
    assert result.status_code == 200, result.text
    return result.json()["batch_id"]


def review(client, w, bid):
    r = client.post(f"/api/workspaces/{w['id']}/projections/{bid}/review")
    assert r.status_code == 200, r.text
    return r.json()


def accept(client, w, bid):
    r = review(client, w, bid)
    response = command(
        client,
        f"/api/workspaces/{w['id']}/analysis/activate",
        {"expected_revision": r["expected_revision"], "candidate_id": r["candidate_id"]},
    )
    assert response.status_code == 200, response.text
    return client.get(f"/api/workspaces/{w['id']}").json(), r


def solve(client, w):
    r = command(client, f"/api/workspaces/{w['id']}/complete", {"expected_revision": w["revision"]})
    assert r.status_code == 202, r.text
    rid = r.json()["request_id"]
    for _ in range(450):
        result = client.get(f"/api/workspaces/{w['id']}/completions/{rid}").json()
        if result["status"] != "pending":
            return result
        time.sleep(0.1)
    pytest.fail("Completion did not finish")


def test_complete_apply_reload_and_stale(client):
    w, files, context = prepare(client)
    bid = stage(client, w, files, context)
    w, r = accept(client, w, bid)
    assert r["coverage"]["summary"]["eligible"] == 10
    p = w["players"][2]
    response = command(
        client,
        f"/api/workspaces/{w['id']}/preferences",
        {
            "expected_revision": w["revision"],
            "entry_id": p["entry_id"],
            "subject_id": p["subject_id"],
            "value": "keep",
        },
    )
    assert response.status_code == 200, response.text
    w = client.get(f"/api/workspaces/{w['id']}").json()
    result = solve(client, w)
    assert result["status"] == "ready", result
    assert result["result"]["whole_total_units"] == 900000
    assert p["entry_id"] in {p["entry_id"] for p in result["preview"]}
    key = str(uuid4())
    path = f"/api/workspaces/{w['id']}/completions/{result['request_id']}/apply"
    applied = command(client, path, {"expected_revision": w["revision"]}, key)
    assert applied.status_code == 200, applied.text
    assert command(client, path, {"expected_revision": w["revision"]}, key).json() == applied.json()
    saved = client.get(f"/api/workspaces/{w['id']}").json()
    assert len(saved["assignments"]) == 9
    assert command(client, path, {"expected_revision": saved["revision"]}).status_code == 409
    assert stage(client, saved, files, context) == bid
    state = client.get(f"/api/workspaces/{w['id']}/analysis").json()
    assert len(state["preferences"]) == 1


@pytest.mark.parametrize(
    "value,state",
    [
        ("0", "explicit_zero"),
        ("-1.25", "numeric"),
        ("", "missing"),
        ("NaN", "nonfinite"),
        ("1.23456", "excessive_precision"),
        ("bad", "invalid"),
    ],
)
def test_numeric_states(value, state):
    assert number(value)[0] == state


@pytest.mark.parametrize(
    "bad", ["missing", "period", "inconsistent", "scoring", "numeric", "duplicate", "position"]
)
def test_batch_atomic_rejection(client, bad):
    w, files, context = prepare(client)
    if bad == "missing":
        files.pop("QB")
    if bad == "position":
        files["QB"], files["RB"] = files["RB"], files["QB"]
    if bad == "period":
        context["period"] = "Wrong"
    if bad == "inconsistent":
        context["file_periods"] = {"QB": "Wrong"}
    if bad == "scoring":
        context["material_settings_match"] = False
    if bad == "numeric":
        files["QB"] = ("QB.csv", files["QB"][1].replace(b"10.0", b"NaN"))
    if bad == "duplicate":
        files["QB"] = ("QB.csv", files["QB"][1] + files["QB"][1].splitlines(keepends=True)[1])
    bid = stage(client, w, files, context)
    r = review(client, w, bid)
    assert r["batch"]["validation"]["errors"]
    assert (
        command(
            client,
            f"/api/workspaces/{w['id']}/analysis/activate",
            {"expected_revision": w["revision"], "candidate_id": r["candidate_id"]},
        ).status_code
        == 422
    )
    assert client.get(f"/api/workspaces/{w['id']}/analysis").json()["analysis"] is None


def test_historical_import_and_server_objectives(client, monkeypatch):
    w, files, context = prepare(client, True)
    bid = stage(client, w, files, context)
    r = review(client, w, bid)
    assert r["batch"]["validation"]["records"] == 624
    assert r["batch"]["validation"]["separators"] == 8
    mappings = json.loads(
        Path("fixtures/private/historical/acceptance/name_mappings.json").read_text()
    )
    for mapping in mappings:
        source = next(
            e["source"]
            for e in r["coverage"]["exceptions"]
            if e["source"]["name"] == mapping["source_name"]
        )
        p = next(p for p in w["players"] if p["yahoo_id"] == mapping["yahoo_id"])
        response = command(
            client,
            f"/api/workspaces/{w['id']}/mappings",
            dict(
                expected_revision=w["revision"],
                batch_id=bid,
                source_key=source["source_key"],
                entry_id=p["entry_id"],
                subject_id=p["subject_id"],
                reason=mapping["evidence"],
            ),
        )
        assert response.status_code == 200, response.text
        w = client.get(f"/api/workspaces/{w['id']}").json()
    w, r = accept(client, w, bid)
    assert r["coverage"]["summary"]["matched"] == 565, r["coverage"]["summary"]
    assert r["coverage"]["summary"]["eligible"] == 562
    assert r["coverage"]["summary"]["zeros"] == 108
    # Isolated test-only clock seam; no production endpoint or deadline bypass.
    from datetime import datetime, timezone

    monkeypatch.setattr(
        client.app.state.completion,
        "prelock",
        lambda db, w: datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    prefs = json.loads(
        Path("fixtures/private/historical/acceptance/test_preferences.json").read_text()
    )
    objectives = []
    for kind, expected in [(None, 1190000), ("keep", 1176000), ("avoid", 1160000)]:
        if kind:
            p = next(
                p
                for p in w["players"]
                if p["yahoo_id"] == prefs["lock" if kind == "keep" else "exclude"]
            )
            response = command(
                client,
                f"/api/workspaces/{w['id']}/preferences",
                dict(
                    expected_revision=w["revision"],
                    entry_id=p["entry_id"],
                    subject_id=p["subject_id"],
                    value=kind,
                ),
            )
            assert response.status_code == 200, response.text
            w = client.get(f"/api/workspaces/{w['id']}").json()
        result = solve(client, w)
        assert result["status"] == "ready", result
        assert result["result"]["whole_total_units"] == expected, result
        assert result["result"]["primary_proven"]
        objectives.append(result)
    Path("artifacts/increment3-historical.json").write_text(json.dumps(objectives, indent=2))


def test_admission_snapshot_stale_and_idempotence(client, monkeypatch):
    import threading

    from server.recommendation.runner import run_solve

    w, files, context = prepare(client)
    bid = stage(client, w, files, context)
    w, _ = accept(client, w, bid)
    entered, release = threading.Event(), threading.Event()
    captured = []

    def held(data, **kwargs):
        captured.append(data)
        entered.set()
        assert release.wait(10)
        return run_solve(data, **kwargs)

    monkeypatch.setattr("server.completion.run_solve", held)
    key = str(uuid4())
    payload = {"expected_revision": w["revision"]}
    path = f"/api/workspaces/{w['id']}/complete"
    first = command(client, path, payload, key)
    assert first.status_code == 202, first.text
    try:
        assert entered.wait(5)
        assert command(client, path, payload, key).json() == first.json()
        assert command(client, path, {"expected_revision": 999}, key).status_code == 409
        assert command(client, path, payload).status_code == 409
        # Stage alone does not affect the request; activation advances the aggregate.
        changed = dict(files)
        changed["QB"] = ("QB.csv", files["QB"][1].replace(b"10.0", b"11.0"))
        newer = stage(client, w, changed, context)
        w, _ = accept(client, w, newer)
        assert all(e.projection == "10.0" for e in captured[0].entries)
    finally:
        release.set()
    rid = first.json()["request_id"]
    for _ in range(150):
        r = client.get(f"/api/workspaces/{w['id']}/completions/{rid}").json()
        if r["status"] != "pending":
            break
        time.sleep(0.1)
    assert r["status"] == "ready" and r["stale"]
    assert (
        command(
            client,
            f"/api/workspaces/{w['id']}/completions/{rid}/apply",
            {"expected_revision": w["revision"]},
        ).status_code
        == 409
    )
    assert not client.get(f"/api/workspaces/{w['id']}").json()["assignments"]


def test_apply_rechecks_clock_after_lock_wait(client):
    import threading

    w, files, context = prepare(client)
    w, _ = accept(client, w, stage(client, w, files, context))
    result = solve(client, w)
    engine = engine_for(URL)
    response = []
    with engine.begin() as blocker:
        run(blocker, "SELECT id FROM contest WHERE id=:id FOR UPDATE", id=w["contest_id"])
        old = one(
            blocker,
            "SELECT d.* FROM lock_head h JOIN lock_decision d ON d.id=h.d"
            "ecision_id WHERE h.contest_id=:id LIMIT 1",
            id=w["contest_id"],
        )
        decision = str(uuid4())
        run(
            blocker,
            "INSERT INTO lock_decision(id,contest_id,game_id,schedule_id,"
            "previous_id,deadline) VALUES (:id,:cid,:gid,:sid,:previous,c"
            "lock_timestamp()+interval '2 seconds')",
            id=decision,
            cid=w["contest_id"],
            gid=old["game_id"],
            sid=old["schedule_id"],
            previous=old["id"],
        )
        run(
            blocker,
            "UPDATE lock_head SET decision_id=:id WHERE contest_id=:cid AND game_id=:gid",
            id=decision,
            cid=w["contest_id"],
            gid=old["game_id"],
        )
        thread = threading.Thread(
            target=lambda: response.append(
                command(
                    client,
                    f"/api/workspaces/{w['id']}/completions/{result['request_id']}/apply",
                    {"expected_revision": w["revision"]},
                )
            )
        )
        thread.start()
        for _ in range(80):
            with engine.connect() as observer:
                waiting = one(
                    observer,
                    "SELECT count(*) AS n FROM pg_stat_activity WHERE wait_event_"
                    "type='Lock' AND query LIKE '%FOR UPDATE OF c%'",
                )["n"]
            if waiting:
                break
            time.sleep(0.025)
        assert waiting
        time.sleep(2.1)
    thread.join(10)
    assert response[0].status_code == 409, response[0].text
    with engine.connect() as db:
        assert (
            one(db, "SELECT count(*) AS n FROM draft_revision WHERE workspace_id=:id", id=w["id"])[
                "n"
            ]
            == 0
        )


def test_readiness_and_impossible_preservation(client):
    w, files, context = prepare(client)
    files["QB"] = ("QB.csv", files["QB"][1].replace(b"10.0", b"-"))
    w, _ = accept(client, w, stage(client, w, files, context))
    p = w["players"][0]
    assert (
        command(
            client,
            f"/api/workspaces/{w['id']}/draft",
            {
                "expected_revision": w["revision"],
                "operations": [{"op": "add", "slot": "QB", "entry_id": p["entry_id"]}],
            },
        ).status_code
        == 200
    )
    w = client.get(f"/api/workspaces/{w['id']}").json()
    r = command(client, f"/api/workspaces/{w['id']}/complete", {"expected_revision": w["revision"]})
    assert r.status_code == 422 and "lacks projection" in r.text
    # Avoid does not silently remove an assignment.
    pref = dict(
        expected_revision=w["revision"],
        entry_id=p["entry_id"],
        subject_id=p["subject_id"],
        value="avoid",
    )
    assert command(client, f"/api/workspaces/{w['id']}/preferences", pref).status_code == 409
    pref["remove_selected"] = True
    assert command(client, f"/api/workspaces/{w['id']}/preferences", pref).status_code == 200
    assert not client.get(f"/api/workspaces/{w['id']}").json()["assignments"]
    # Two kept QBs are impossible, with no constraint relaxation.
    w, files, context = prepare(client)
    w, _ = accept(client, w, stage(client, w, files, context))
    for p in w["players"][:2]:
        r = command(
            client,
            f"/api/workspaces/{w['id']}/preferences",
            dict(
                expected_revision=w["revision"],
                entry_id=p["entry_id"],
                subject_id=p["subject_id"],
                value="keep",
            ),
        )
        assert r.status_code == 200, r.text
        w = client.get(f"/api/workspaces/{w['id']}").json()
    assert solve(client, w)["status"] == "infeasible"


def test_expired_lease_cannot_publish_or_apply(client, monkeypatch):
    import threading

    from server.recommendation.runner import run_solve

    entered, release = threading.Event(), threading.Event()

    def held(data, **kwargs):
        entered.set()
        assert release.wait(10)
        return run_solve(data, **kwargs)

    monkeypatch.setattr("server.completion.run_solve", held)
    w, files, context = prepare(client)
    w, _ = accept(client, w, stage(client, w, files, context))
    key = str(uuid4())
    response = command(
        client, f"/api/workspaces/{w['id']}/complete", {"expected_revision": w["revision"]}, key
    )
    rid = response.json()["request_id"]
    try:
        assert entered.wait(5)
        with engine_for(URL).begin() as db:
            run(
                db,
                "UPDATE solve_lease SET expires_at=clock_timestamp()-interval"
                " '1 second' WHERE singleton",
            )
        r = client.get(f"/api/workspaces/{w['id']}/completions/{rid}").json()
        assert r["status"] == "interrupted"
        assert (
            command(
                client,
                f"/api/workspaces/{w['id']}/complete",
                {"expected_revision": w["revision"]},
                key,
            ).json()
            == response.json()
        )
    finally:
        release.set()
    assert (
        command(
            client,
            f"/api/workspaces/{w['id']}/completions/{rid}/apply",
            {"expected_revision": w["revision"]},
        ).status_code
        == 409
    )


def test_new_immutable_tables_runtime_grants(client):
    from sqlalchemy.exc import DBAPIError

    tables = [
        "projection_batch",
        "projection_file",
        "mapping_revision",
        "availability_revision",
        "coverage_report",
        "analysis_manifest",
        "preference_revision",
        "recommendation_request",
        "recommendation_result",
    ]
    for table in tables:
        with engine_for(URL).begin() as db:
            with pytest.raises(DBAPIError):
                run(db, f"DELETE FROM {table} WHERE false")
        with engine_for(URL).begin() as db:
            with pytest.raises(DBAPIError):
                column = (
                    "position"
                    if table == "projection_file"
                    else "status" if table == "recommendation_result" else "id"
                )
                run(db, f"UPDATE {table} SET {column}={column} WHERE false")


def test_availability_scope_resolution_and_new_evidence(client):
    w, files, context = prepare(client)
    bid = stage(client, w, files, context)
    w, reviewed = accept(client, w, bid)
    p = reviewed["coverage"]["players"][0]

    def record(designation, evidence_type="designation", resolves=None):
        nonlocal w
        response = command(
            client,
            f"/api/workspaces/{w['id']}/availability",
            {
                "expected_revision": w["revision"],
                "subject_id": p["subject_id"],
                "game_id": p["game_id"],
                "designation": designation,
                "evidence_type": evidence_type,
                "source": "Synthetic scoped source",
                "reason": "Explicit synthetic evidence for boundary test",
                "resolves": resolves or [],
            },
        )
        assert response.status_code == 200, response.text
        w = client.get(f"/api/workspaces/{w['id']}").json()

    record("Q")
    w, r = accept(client, w, bid)
    assert r["coverage"]["players"][0]["available"]
    record("Out")
    assert (
        command(
            client, f"/api/workspaces/{w['id']}/complete", {"expected_revision": w["revision"]}
        ).status_code
        == 422
    )
    w, r = accept(client, w, bid)
    assert not r["coverage"]["players"][0]["available"]
    state = client.get(f"/api/workspaces/{w['id']}/analysis").json()
    blocked = state["availability"][-1]
    record("Active", "resolution", [blocked["id"]])
    w, r = accept(client, w, bid)
    assert r["coverage"]["players"][0]["available"]
    record("Out")
    w, r = accept(client, w, bid)
    assert not r["coverage"]["players"][0]["available"]


def test_current_salary_and_orphaned_preference(client):
    from tools.completion_demo import completion_demo

    w, files, context = prepare(client)
    bid = stage(client, w, files, context)
    w, _ = accept(client, w, bid)
    p = w["players"][0]
    assert (
        command(
            client,
            f"/api/workspaces/{w['id']}/draft",
            {
                "expected_revision": w["revision"],
                "operations": [{"op": "add", "slot": "QB", "entry_id": p["entry_id"]}],
            },
        ).status_code
        == 200
    )
    w = client.get(f"/api/workspaces/{w['id']}").json()
    assert (
        command(
            client,
            f"/api/workspaces/{w['id']}/preferences",
            {
                "expected_revision": w["revision"],
                "entry_id": p["entry_id"],
                "subject_id": p["subject_id"],
                "value": "keep",
            },
        ).status_code
        == 200
    )
    _, raw, _ = completion_demo()
    for changed in [raw.replace(b",35,", b",40,"), raw.replace(b",Alpha,", b",Different,")]:
        upload = client.post(
            f"/api/workspaces/{w['id']}/imports", files={"file": ("changed.csv", changed)}
        )
        preview = client.get(
            f"/api/workspaces/{w['id']}/imports/{upload.json()['batch_id']}"
        ).json()
        w = activate(client, w["id"], preview)
        assert w["assignments"]["QB"]["salary_cents"] == 3500
        if b",Different," not in changed:
            assert w["salary_cents"] == 4000
        else:
            assert w["salary_cents"] is None
            current = w["players"][0]
            response = command(
                client,
                f"/api/workspaces/{w['id']}/preferences",
                {
                    "expected_revision": w["revision"],
                    "entry_id": current["entry_id"],
                    "subject_id": current["subject_id"],
                    "value": "keep",
                },
            )
            assert response.status_code == 409
            state = client.get(f"/api/workspaces/{w['id']}/analysis").json()
            assert state["preferences"][0]["subject_id"] == p["subject_id"]


def test_feasible_unproven_server_result(client, monkeypatch):
    from server.recommendation.runner import run_solve

    def unproven(data, **kwargs):
        result = run_solve(data, **kwargs)
        primary = result.stages[0].model_copy(update={"status": "FEASIBLE", "proven": False})
        return result.model_copy(
            update={
                "status": "FEASIBLE",
                "primary_proven": False,
                "tie_complete": False,
                "stages": (primary,),
            }
        )

    monkeypatch.setattr("server.completion.run_solve", unproven)
    w, files, context = prepare(client)
    w, _ = accept(client, w, stage(client, w, files, context))
    result = solve(client, w)
    assert result["status"] == "ready" and result["result"]["status"] == "FEASIBLE"
    assert not result["result"]["primary_proven"] and not result["result"]["tie_complete"]


def test_selected_avoid_conflict_and_shutdown(client, settings):
    from fastapi.testclient import TestClient

    from server.app import create_app

    w, files, context = prepare(client)
    w, _ = accept(client, w, stage(client, w, files, context))
    p = w["players"][0]
    path = f"/api/workspaces/{w['id']}"
    preference = {
        "expected_revision": w["revision"],
        "entry_id": p["entry_id"],
        "subject_id": p["subject_id"],
        "value": "avoid",
    }
    assert command(client, path + "/preferences", preference).status_code == 200
    w = client.get(path).json()
    assert (
        command(
            client,
            path + "/draft",
            {
                "expected_revision": w["revision"],
                "operations": [{"op": "add", "slot": "QB", "entry_id": p["entry_id"]}],
            },
        ).status_code
        == 200
    )
    w = client.get(path).json()
    response = command(client, path + "/complete", {"expected_revision": w["revision"]})
    assert response.status_code == 422 and "conflict" in response.text
    preference.update(value="clear", expected_revision=w["revision"])
    assert command(client, path + "/preferences", preference).status_code == 200
    w = client.get(path).json()
    response = command(client, path + "/complete", {"expected_revision": w["revision"]})
    assert response.status_code == 202
    client.app.state.completion.close()
    with TestClient(create_app(settings), base_url=settings.origin) as restarted:
        restarted.cookies.update(client.cookies)
        result = restarted.get(path + "/completions/" + response.json()["request_id"]).json()
        assert result["status"] == "interrupted"
        assert restarted.get(path).json()["draft_id"] == w["draft_id"]


def test_historical_reported_absence_remains_historical(client):
    w, files, context = prepare(client, True)
    bid = stage(client, w, files, context)
    p = next(p for p in w["players"] if p["name"] == "Brock Bowers")
    response = command(
        client,
        f"/api/workspaces/{w['id']}/availability",
        {
            "expected_revision": w["revision"],
            "subject_id": p["subject_id"],
            "game_id": p["game_id"],
            "evidence_type": "participation",
            "designation": "Reported absence",
            "source": "Retained historical Bowers article; PROJECTION_ACCEPTANCE_REPORT section 4",
            "source_time": "2026-09-09T20:40:45.194Z",
            "reason": "Historical Week 1 absence; not a final inactive designation or fresh check",
        },
    )
    assert response.status_code == 200, response.text
    r = review(client, w, bid)
    b = next(p for p in r["coverage"]["players"] if p["name"] == "Brock Bowers")
    assert not b["available"]
    assert b["availability"][0]["source_time"] == "2026-09-09T20:40:45.194000Z"
    assert b["availability"][0]["acquired_at"] != b["availability"][0]["source_time"]
