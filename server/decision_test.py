"""Decision actions through authenticated HTTP, real PostgreSQL and restricted runtime grants."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.exc import DBAPIError

from server import application_test as boundary
from server.application_test import URL, activate, command, save
from server.completion_test import accept, prepare, solve, stage
from server.decision import OddsInput, implied
from server.persistence import engine_for, one, run
from server.recommendation.contracts import SolveInput, SolveResult
from tools.completion_demo import completion_demo

client = boundary.client
settings = boundary.settings


def ready(client: TestClient) -> dict:
    w, files, context = prepare(client)
    return accept(client, w, stage(client, w, files, context))[0]


def read(client: TestClient, w: dict) -> dict:
    return client.get(f"/api/workspaces/{w['id']}").json()


def post(client: TestClient, w: dict, action: str, **values: object) -> Response:
    return command(
        client,
        f"/api/workspaces/{w['id']}/{action}",
        {"expected_revision": w["revision"], **values},
    )


def poll(client: TestClient, w: dict, response: Response) -> dict:
    assert response.status_code == 202, response.text
    rid = response.json()["request_id"]
    for _ in range(450):
        result = client.get(f"/api/workspaces/{w['id']}/completions/{rid}").json()
        if result["status"] != "pending":
            return result
        time.sleep(0.1)
    pytest.fail("Shared request deadline exceeded")


def apply(client: TestClient, w: dict, result: dict, index: int = 0) -> dict:
    r = post(client, w, f"completions/{result['request_id']}/apply", candidate_index=index)
    assert r.status_code == 200, r.text
    return read(client, w)


def quote(w: dict, **updates: object) -> dict:
    return dict(
        expected_revision=w["revision"],
        expected_context_revision=w["context_revision"],
        game_id=w["games"][0]["id"],
        source="Synthetic bookmaker",
        reference="Manual full game pair",
        observed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        total="47.5001",
        home_spread="-3.25",
        **updates,
    )


@pytest.mark.parametrize(
    "spread,home,away",
    [
        ("-3.25", "25.37505", "22.12505"),
        ("3.25", "22.12505", "25.37505"),
        ("0", "23.75005", "23.75005"),
    ],
)
def test_exact_home_sign(spread: str, home: str, away: str) -> None:
    assert implied("47.5001", spread) == {"home_implied": home, "away_implied": away}


@pytest.mark.parametrize(
    "field,value",
    [
        ("total", "NaN"),
        ("total", "-1"),
        ("home_spread", "99"),
        ("total", "47.00001"),
        ("market", "first-half"),
        ("convention", "away-team"),
        ("observed_at", "2026-09-01T12:00:00"),
    ],
)
def test_odds_invalid(field: str, value: str) -> None:
    data = dict(
        expected_revision=0,
        expected_context_revision=0,
        game_id=str(uuid4()),
        source="Test",
        reference="Reference",
        observed_at="2026-09-01T12:00:00Z",
        total="47",
        home_spread="-3",
    )
    with pytest.raises(ValueError):
        OddsInput.model_validate({**data, field: value})


def test_context_isolation_duplicates_and_comparable_history(client: TestClient) -> None:
    w = ready(client)
    assert not w["environments"]
    result = solve(client, w)
    body = quote(w)
    key = str(uuid4())
    path = f"/api/workspaces/{w['id']}/odds"
    response = command(client, path, body, key)
    assert response.status_code == 200, response.text
    assert command(client, path, body, key).json() == response.json()
    newer = read(client, w)
    assert newer["revision"] == w["revision"] and newer["manifest_id"] == w["manifest_id"]
    assert newer["players"] == w["players"] and newer["assignments"] == w["assignments"]
    assert len(newer["environments"]) == 1 < len(w["games"])
    assert newer["environments"][0]["total_change"] is None
    assert command(client, path, quote(newer)).status_code == 409  # cannot silently replace
    duplicate = {**body, "expected_context_revision": 1, "supersedes": response.json()["odds_id"]}
    assert command(client, path, duplicate).status_code == 409
    changed = {**quote(newer), "total": "48", "supersedes": response.json()["odds_id"]}
    assert command(client, path, changed).status_code == 200
    newest = read(client, w)
    assert newest["environments"][0]["total_change"] == "0.4999"
    r = client.get(f"/api/workspaces/{w['id']}/completions/{result['request_id']}").json()
    assert not r["stale"] and r["newer_context"] and r["captured_context"]["environments"] == []
    assert command(client, path, {**quote(newest), "game_id": str(uuid4())}).status_code == 422
    apply(client, newest, result)  # context alone does not stale a valid solver result


def test_alternatives_constraints_distinct_apply_and_undo(client: TestClient) -> None:
    w = ready(client)
    # Complete must preserve lower-tie QB Bravo. Alternatives may replace him.
    qb = [p for p in w["players"] if p["position"] == "QB" and not p["issues"]]
    assert (
        save(client, w, [dict(op="add", slot="QB", entry_id=qb[1]["entry_id"])]).status_code == 200
    )
    w = read(client, w)
    complete = solve(client, w)
    assert complete["preview"][0]["entry_id"] == qb[1]["entry_id"]
    pref = next(p for p in w["players"] if p["position"] == "RB")
    assert (
        post(
            client,
            w,
            "preferences",
            entry_id=pref["entry_id"],
            subject_id=pref["subject_id"],
            value="keep",
        ).status_code
        == 200
    )
    w = read(client, w)
    r = poll(client, w, post(client, w, "alternatives"))
    assert 1 < len(r["candidates"]) <= 3
    members = [frozenset(p["entry_id"] for p in c["preview"]) for c in r["candidates"]]
    assert len(set(members)) == len(members)
    assert all(pref["entry_id"] in m for m in members)
    assert all(c["delta_draft_units"] is None for c in r["candidates"])
    saved = apply(client, w, r, 1)
    assert {s: p["entry_id"] for s, p in saved["assignments"].items()} == {
        p["slot"]: p["entry_id"] for p in r["candidates"][1]["preview"]
    }
    path = f"/api/workspaces/{w['id']}/undo"
    key = str(uuid4())
    body = {"expected_revision": saved["revision"]}
    undone = command(client, path, body, key)
    assert undone.status_code == 200, undone.text
    assert command(client, path, body, key).json() == undone.json()
    restored = read(client, w)
    assert {s: p["entry_id"] for s, p in restored["assignments"].items()} == {
        s: p["entry_id"] for s, p in w["assignments"].items()
    }
    assert restored["preferences"] == w["preferences"]
    assert post(client, restored, "undo").status_code == 422
    temp = poll(
        client,
        restored,
        post(
            client,
            restored,
            "alternatives",
            include=[qb[0]["yahoo_id"]],
            exclude=[qb[1]["yahoo_id"]],
        ),
    )
    assert all(
        qb[0]["entry_id"] in {p["entry_id"] for p in c["preview"]} for c in temp["candidates"]
    )
    assert read(client, w)["preferences"] == w["preferences"]
    assert post(client, restored, "alternatives", exclude=[pref["yahoo_id"]]).status_code == 422


def test_entered_immutable_superseding_and_slot_comparison(client: TestClient) -> None:
    w = ready(client)
    w = apply(client, w, solve(client, w))
    original_draft = w["draft_id"]
    payload = dict(
        expected_revision=w["revision"],
        draft_id=w["draft_id"],
        attestation="Record as entered in Yahoo",
        reason="Manually entered synthetic lineup",
    )
    key = str(uuid4())
    path = f"/api/workspaces/{w['id']}/entered"
    response = command(client, path, payload, key)
    assert response.status_code == 200, response.text
    assert command(client, path, payload, key).json() == response.json()
    entered = read(client, w)
    assert entered["draft_id"] == original_draft and entered["entered_status"] == "matches"
    a, b = w["assignments"]["WR1"], w["assignments"]["WR2"]
    assert (
        save(
            client,
            entered,
            [
                dict(op="remove", slot="WR1"),
                dict(op="remove", slot="WR2"),
                dict(op="add", slot="WR1", entry_id=b["entry_id"]),
                dict(op="add", slot="WR2", entry_id=a["entry_id"]),
            ],
        ).status_code
        == 200
    )
    changed = read(client, w)
    assert changed["entered_status"] == "differs" and changed["entered"] == entered["entered"]
    r = poll(client, changed, post(client, changed, "alternatives"))
    assert all(c["delta_draft_units"] == 0 for c in r["candidates"])
    changed = apply(client, changed, r)
    assert post(client, changed, "undo").status_code == 200
    changed = read(client, w)
    assert changed["entered"] == entered["entered"]
    assert (
        post(
            client,
            changed,
            "entered",
            draft_id=changed["draft_id"],
            attestation="Record as entered in Yahoo",
            reason="Explicit replacement in Yahoo",
        ).status_code
        == 200
    )
    newer = read(client, w)
    assert newer["entered"]["parent_id"] == entered["entered"]["id"]
    assert newer["entered_status"] == "matches"
    assert command(client, path, payload).status_code == 409
    assert command(client, path, {**payload, "reason": "Different payload"}, key).status_code == 409


def test_undo_current_facts_missing_projections_and_avoid(client: TestClient) -> None:
    w = ready(client)
    p = w["players"][0]
    assert save(client, w, [dict(op="add", slot="QB", entry_id=p["entry_id"])]).status_code == 200
    w = read(client, w)
    assert (
        post(
            client,
            w,
            "preferences",
            entry_id=p["entry_id"],
            subject_id=p["subject_id"],
            value="avoid",
            remove_selected=True,
        ).status_code
        == 200
    )
    w = read(client, w)
    assert post(client, w, "undo").status_code == 422
    assert (
        post(
            client,
            w,
            "preferences",
            entry_id=p["entry_id"],
            subject_id=p["subject_id"],
            value="clear",
        ).status_code
        == 200
    )
    w = read(client, w)
    _, raw, _ = completion_demo()
    raw = raw.replace(b",35,", b",199,")
    bid = client.post(
        f"/api/workspaces/{w['id']}/imports", files={"file": ("new.csv", raw)}
    ).json()["batch_id"]
    w = activate(client, w["id"], client.get(f"/api/workspaces/{w['id']}/imports/{bid}").json())
    assert post(client, w, "undo").status_code == 200  # no accepted projections for new pool
    restored = read(client, w)
    assert restored["salary_cents"] == 19900
    assert restored["assignments"]["QB"]["salary_cents"] == 3500  # historical stays evidence
    assert save(client, restored, [dict(op="remove", slot="QB")]).status_code == 200
    w = read(client, w)
    raw = raw.replace(b"Synthetic,Alpha", b"Another,Identity")
    bid = client.post(
        f"/api/workspaces/{w['id']}/imports", files={"file": ("changed.csv", raw)}
    ).json()["batch_id"]
    w = activate(client, w["id"], client.get(f"/api/workspaces/{w['id']}/imports/{bid}").json())
    assert post(client, w, "undo").status_code == 422


@pytest.mark.parametrize("action", ["undo", "entered"])
def test_new_deadline_contention_zero_writes(client: TestClient, action: str) -> None:
    w = ready(client)
    w = apply(client, w, solve(client, w))
    values = (
        dict(
            draft_id=w["draft_id"],
            attestation="Record as entered in Yahoo",
            reason="Deadline test recording",
        )
        if action == "entered"
        else {}
    )
    engine = engine_for(URL)
    response = []
    with engine.begin() as blocker:
        run(blocker, "SELECT id FROM contest WHERE id=:id FOR UPDATE", id=w["contest_id"])
        old = one(
            blocker,
            "SELECT d.* FROM lock_head h JOIN lock_decision d ON d.id=h.decision_id"
            " WHERE h.contest_id=:id LIMIT 1",
            id=w["contest_id"],
        )
        lid = str(uuid4())
        run(
            blocker,
            "INSERT INTO lock_decision(id,contest_id,game_id,schedule_id,previous_i"
            "d,deadline) VALUES (:id,:cid,:gid,:sid,:prior,clock_timestamp()+interval '2 seconds')",
            id=lid,
            cid=w["contest_id"],
            gid=old["game_id"],
            sid=old["schedule_id"],
            prior=old["id"],
        )
        run(
            blocker,
            "UPDATE lock_head SET decision_id=:id WHERE contest_id=:cid AND game_id=:gid",
            id=lid,
            cid=w["contest_id"],
            gid=old["game_id"],
        )
        thread = threading.Thread(target=lambda: response.append(post(client, w, action, **values)))
        thread.start()
        for _ in range(80):
            with engine.connect() as observer:
                waiting = one(
                    observer,
                    "SELECT count(*) AS n FROM pg_stat_activity WHERE wait_event_type='Lock"
                    "' AND query LIKE '%FOR UPDATE OF c%'",
                )["n"]
            if waiting:
                break
            time.sleep(0.025)
        assert waiting
        time.sleep(2.1)
    thread.join(10)
    assert response[0].status_code == 423, response[0].text
    assert read(client, w)["revision"] == w["revision"]
    with engine.connect() as db:
        assert (
            one(db, "SELECT count(*) AS n FROM draft_revision WHERE workspace_id=:id", id=w["id"])[
                "n"
            ]
            == 1
        )
        assert (
            one(
                db, "SELECT count(*) AS n FROM entered_revision WHERE workspace_id=:id", id=w["id"]
            )["n"]
            == 0
        )


@pytest.mark.parametrize("action", ["undo", "entered"])
def test_concurrent_stale_mutations(client: TestClient, action: str) -> None:
    w = ready(client)
    w = apply(client, w, solve(client, w))
    values = (
        dict(
            draft_id=w["draft_id"],
            attestation="Record as entered in Yahoo",
            reason="Concurrent recording test",
        )
        if action == "entered"
        else {}
    )
    with ThreadPoolExecutor(2) as executor:
        futures = [executor.submit(post, client, w, action, **values) for _ in range(2)]
        assert sorted(f.result().status_code for f in futures) == [200, 409]


def test_runtime_immutability_and_owner_endpoints(client: TestClient) -> None:
    engine = engine_for(URL)
    for table in ["odds_revision", "entered_revision"]:
        for sql in [f"DELETE FROM {table} WHERE false", f"UPDATE {table} SET id=id WHERE false"]:
            with engine.begin() as db, pytest.raises(DBAPIError):
                run(db, sql)
    w = ready(client)
    for action, body in [
        ("odds", quote(w)),
        ("alternatives", {"expected_revision": w["revision"]}),
        ("undo", {"expected_revision": w["revision"]}),
        (
            "entered",
            dict(
                expected_revision=w["revision"],
                draft_id=str(uuid4()),
                attestation="Record as entered in Yahoo",
                reason="Authorization test",
            ),
        ),
    ]:
        assert command(client, f"/api/workspaces/{uuid4()}/{action}", body).status_code == 404
        client.cookies.clear()
        assert command(client, f"/api/workspaces/{w['id']}/{action}", body).status_code == 401
        # restore session via full OIDC; no bypass
        boundary.sign_in(client)
        client.headers["x-csrf-token"] = client.get("/api/session").json()["csrf"]


def test_alternatives_shared_budget_and_interruption(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server import completion
    from server.recommendation.solver import solve as direct

    w = ready(client)
    calls = []
    clock = [0.0]

    def runner(
        data: SolveInput,
        budget_seconds: float = 30,
        hard_seconds: float = 35,
        cancel: threading.Event | None = None,
    ) -> SolveResult:
        calls.append((budget_seconds, hard_seconds))
        result = direct(data)
        clock[0] += 28 if len(calls) == 1 else 3
        return result

    monkeypatch.setattr(completion, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(completion, "run_solve", runner)
    r = poll(client, w, post(client, w, "alternatives"))
    assert r["status"] == "ready"
    assert calls == [(30, 35), (2, 7)]  # no third child; no multiplied budget
    assert read(client, w)["draft_id"] is None

    def interrupted(data: SolveInput, **kwargs: object) -> SolveResult:
        result = direct(data)
        client.app.state.completion.cancel.set()
        return result

    monkeypatch.setattr(completion, "run_solve", interrupted)
    r = poll(client, w, post(client, w, "alternatives"))
    assert r["status"] == "interrupted"
    assert post(client, w, f"completions/{r['request_id']}/apply").status_code == 409
    with engine_for(URL).connect() as db:
        assert one(db, "SELECT request_id FROM solve_lease WHERE singleton")["request_id"] is None


def test_avoid_and_unprojected_selected_alternatives(client: TestClient) -> None:
    w, files, context = prepare(client)
    # One selected QB lacks a forecast; a second still has one.
    files["QB"] = ("QB.csv", files["QB"][1].replace(b"10.0", b"-", 1))
    w, _ = accept(client, w, stage(client, w, files, context))
    qb = [p for p in w["players"] if p["position"] == "QB" and not p["issues"]]
    assert (
        save(client, w, [dict(op="add", slot="QB", entry_id=qb[0]["entry_id"])]).status_code == 200
    )
    w = read(client, w)
    assert post(client, w, "complete").status_code == 422
    r = poll(client, w, post(client, w, "alternatives"))
    assert r["status"] == "ready"
    assert all(c["delta_draft_units"] is None for c in r["candidates"])
    assert qb[1]["entry_id"] in {p["entry_id"] for p in r["candidates"][0]["preview"]}
    # Avoid is persisted, not silently relaxed by temporary inclusion.
    assert (
        post(
            client,
            w,
            "preferences",
            entry_id=qb[1]["entry_id"],
            subject_id=qb[1]["subject_id"],
            value="avoid",
        ).status_code
        == 200
    )
    w = read(client, w)
    assert post(client, w, "alternatives", include=[qb[1]["yahoo_id"]]).status_code == 422


def test_entered_survives_source_activation_without_projection_requirement(
    client: TestClient,
) -> None:
    w = ready(client)
    w = apply(client, w, solve(client, w))
    assert (
        post(
            client,
            w,
            "entered",
            draft_id=w["draft_id"],
            attestation="Record as entered in Yahoo",
            reason="Initial recorded entry",
        ).status_code
        == 200
    )
    w = read(client, w)
    _, raw, _ = completion_demo()
    raw = raw.replace(b",35,", b",199,")
    bid = client.post(
        f"/api/workspaces/{w['id']}/imports", files={"file": ("new.csv", raw)}
    ).json()["batch_id"]
    newer = activate(client, w["id"], client.get(f"/api/workspaces/{w['id']}/imports/{bid}").json())
    assert newer["entered"] == w["entered"] and newer["entered_status"] == "matches"
    assert (
        post(
            client,
            newer,
            "entered",
            draft_id=newer["draft_id"],
            attestation="Record as entered in Yahoo",
            reason="Would exceed current cap",
        ).status_code
        == 422
    )


def test_alternatives_names_removed_orphan(client: TestClient) -> None:
    w, files, context = prepare(client)
    w, _ = accept(client, w, stage(client, w, files, context))
    player = w["players"][0]
    assert (
        save(client, w, [dict(op="add", slot="QB", entry_id=player["entry_id"])]).status_code == 200
    )
    _, raw, _ = completion_demo()
    raw = raw.replace(b"Synthetic,Alpha", b"Changed,Identity")
    bid = client.post(
        f"/api/workspaces/{w['id']}/imports", files={"file": ("identity.csv", raw)}
    ).json()["batch_id"]
    w = activate(client, w["id"], client.get(f"/api/workspaces/{w['id']}/imports/{bid}").json())
    w, _ = accept(client, w, stage(client, w, files, context))
    assert post(client, w, "complete").status_code == 422
    result = poll(client, w, post(client, w, "alternatives"))
    assert result["status"] == "ready"
    assert all(player["name"] in c["removed"] for c in result["candidates"])
    assert all(c["delta_draft_units"] is None for c in result["candidates"])
