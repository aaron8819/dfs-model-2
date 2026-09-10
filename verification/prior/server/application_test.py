"""Actual runtime role/PostgreSQL, and HTTP OIDC callback/session boundaries."""

import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from server.app import create_app
from server.config import Settings
from server.persistence import digest, engine_for, many, one, run
from tools.synthetic_demo import demo

URL = "postgresql+psycopg://dfs_runtime@127.0.0.1:55432/dfs_increment2_test"
ADMIN = "postgresql+psycopg://dfs_migration@127.0.0.1:55432/dfs_increment2_test"
ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture(scope="module")
def settings() -> Settings:
    secret = secrets.token_urlsafe(32)
    os.environ["OIDC_CLIENT_SECRET"] = secret
    from tools.test_oidc import app as provider

    server = uvicorn.Server(
        uvicorn.Config(provider, host="127.0.0.1", port=8766, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield Settings(
        URL, ORIGIN, "http://127.0.0.1:8766", "dfs-local-test", secret, "synthetic-owner", True
    )
    server.should_exit = True
    thread.join(5)


def sign_in(client: TestClient) -> httpx.Response:
    login = client.get("/auth/login", follow_redirects=False)
    assert login.status_code == 303, login.text
    query = {k: v[0] for k, v in parse_qs(urlparse(login.headers["location"]).query).items()}
    assert query["code_challenge_method"] == "S256" and query["nonce"] and query["state"]
    approved = httpx.post("http://127.0.0.1:8766/authorize", data=query)
    callback = client.get(approved.headers["location"], follow_redirects=False)
    return callback


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        response = sign_in(client)
        assert response.status_code == 303, response.text
        session = client.get("/api/session").json()
        client.headers.update({"origin": ORIGIN, "x-csrf-token": session["csrf"]})
        yield client


def command(
    client: TestClient, path: str, data: dict, key: str | None = None, method: str = "POST"
) -> httpx.Response:
    return client.request(method, path, json=data, headers={"idempotency-key": key or str(uuid4())})


def prepared(client: TestClient, kickoff: datetime | None = None) -> tuple[str, dict, dict, bytes]:
    setup, raw = demo(kickoff)
    setup["yahoo_id"] = "synthetic-" + str(uuid4())
    result = command(client, "/api/workspaces", setup)
    assert result.status_code == 200, result.text
    wid = result.json()["workspace_id"]
    upload = client.post(f"/api/workspaces/{wid}/imports", files={"file": ("synthetic.csv", raw)})
    assert upload.status_code == 200, upload.text
    bid = upload.json()["batch_id"]
    preview = client.get(f"/api/workspaces/{wid}/imports/{bid}").json()
    return wid, setup, preview, raw


def activate(client: TestClient, wid: str, preview: dict) -> dict:
    w = client.get(f"/api/workspaces/{wid}").json()
    response = command(
        client,
        f"/api/workspaces/{wid}/activate",
        {"expected_revision": w["revision"], "batch_id": preview["id"], "batch_revision": 1},
    )
    assert response.status_code == 200, response.text
    return client.get(f"/api/workspaces/{wid}").json()


def save(
    client: TestClient, w: dict, operations: list[dict], key: str | None = None
) -> httpx.Response:
    return command(
        client,
        f"/api/workspaces/{w['id']}/draft",
        {"expected_revision": w["revision"], "operations": operations},
        key,
    )


def test_staging_idempotence_raw_and_history(client: TestClient, settings: Settings) -> None:
    wid, _, preview, raw = prepared(client)
    assert preview["summary"]["quarantined_rows"] == 2
    w = client.get(f"/api/workspaces/{wid}").json()
    assert w["active_pool_id"] is None and not w["players"]
    again = client.post(f"/api/workspaces/{wid}/imports", files={"file": ("again.csv", raw)}).json()
    assert again["batch_id"] == preview["id"]
    assert (
        client.get(f"/api/workspaces/{wid}/imports/{preview['id']}").json()["imported_at"]
        == preview["imported_at"]
    )
    assert client.get(f"/api/workspaces/{wid}/imports/{preview['id']}/raw").content == raw
    w = activate(client, wid, preview)
    alpha = w["players"][0]
    patch = [{"op": "add", "slot": "QB", "entry_id": alpha["entry_id"]}]
    key = str(uuid4())
    result = save(client, w, patch, key)
    assert result.status_code == 200, result.text
    assert save(client, w, patch, key).json() == result.json()
    assert save(client, w, [{"op": "remove", "slot": "QB"}], key).status_code == 409
    reloaded = client.get(f"/api/workspaces/{wid}").json()
    assert reloaded["assignments"]["QB"]["row_id"] == alpha["row_id"]
    # New app and connection pool, same database and opaque server session.
    with TestClient(create_app(settings), base_url=ORIGIN) as restarted:
        restarted.cookies.update(client.cookies)
        assert (
            restarted.get(f"/api/workspaces/{wid}").json()["assignments"] == reloaded["assignments"]
        )


def test_structure_replacement_remove_and_overbudget(client: TestClient) -> None:
    wid, _, preview, _ = prepared(client)
    w = activate(client, wid, preview)
    p = w["players"]
    operations = [
        {"op": "add", "slot": slot, "entry_id": p[index]["entry_id"]}
        for slot, index in [("QB", 0), ("RB1", 2), ("RB2", 3)]
    ]
    assert save(client, w, operations).status_code == 200
    w = client.get(f"/api/workspaces/{wid}").json()
    assert w["salary_cents"] == 21500
    assert "Over budget" in " ".join(w["issues"])
    assert (
        save(client, w, [{"op": "add", "slot": "QB", "entry_id": p[1]["entry_id"]}]).status_code
        == 409
    )
    assert (
        save(client, w, [{"op": "replace", "slot": "QB", "entry_id": p[1]["entry_id"]}]).status_code
        == 200
    )
    w = client.get(f"/api/workspaces/{wid}").json()
    for op in [
        {"op": "add", "slot": "WR1", "entry_id": p[2]["entry_id"]},
        {"op": "add", "slot": "FLEX", "entry_id": p[2]["entry_id"]},
        {"op": "add", "slot": "WR1", "entry_id": p[-1]["entry_id"]},
        {"op": "add", "slot": "WR1", "entry_id": str(uuid4())},
        {"op": "add", "slot": "INVALID", "entry_id": p[4]["entry_id"]},
    ]:
        assert save(client, w, [op]).status_code == 422
    assert save(client, w, [{"op": "remove", "slot": "QB"}]).status_code == 200
    assert "QB" not in client.get(f"/api/workspaces/{wid}").json()["assignments"]


def test_stale_saves_one_winner(client: TestClient) -> None:
    wid, _, preview, _ = prepared(client)
    w = activate(client, wid, preview)
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda index: save(
                    client,
                    w,
                    [{"op": "add", "slot": "QB", "entry_id": w["players"][index]["entry_id"]}],
                ).status_code,
                [0, 1],
            )
        )
    assert sorted(results) == [200, 409]
    with engine_for(URL).connect() as db:
        assert (
            one(db, "SELECT count(*) AS n FROM draft_revision WHERE workspace_id=:id", id=wid)["n"]
            == 1
        )


def test_setup_revalidation_stable_game_and_no_reopen(client: TestClient) -> None:
    wid, setup, preview, _ = prepared(client, datetime.now(timezone.utc) - timedelta(days=1))
    w = activate(client, wid, preview)
    old_game_ids = [g["id"] for g in w["games"]]
    old_membership = w["setup"]["slate_revision_id"]
    setup["expected_revision"] = w["revision"]
    for game in setup["games"]:
        game["kickoff"] = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    response = command(client, f"/api/workspaces/{wid}/setup", setup, method="PUT")
    assert response.status_code == 200, response.text
    w = client.get(f"/api/workspaces/{wid}").json()
    assert [g["id"] for g in w["games"]] == old_game_ids
    assert w["setup"]["slate_revision_id"] == old_membership and w["locked"]
    assert (
        command(
            client,
            f"/api/workspaces/{wid}/activate",
            {"expected_revision": w["revision"], "batch_id": preview["id"], "batch_revision": 1},
        ).status_code
        == 409
    )
    setup["expected_revision"] = w["revision"]
    setup["games"] = setup["games"][:1]
    assert command(client, f"/api/workspaces/{wid}/setup", setup, method="PUT").status_code == 423
    setup["membership_change_confirmed"] = True
    assert command(client, f"/api/workspaces/{wid}/setup", setup, method="PUT").status_code == 423
    w = client.get(f"/api/workspaces/{wid}").json()
    assert w["locked"] and w["setup"]["slate_revision_id"] == old_membership


def test_replacement_preserves_unresolved_salary_and_subject(client: TestClient) -> None:
    wid, _, preview, raw = prepared(client)
    w = activate(client, wid, preview)
    assert (
        save(
            client, w, [{"op": "add", "slot": "QB", "entry_id": w["players"][0]["entry_id"]}]
        ).status_code
        == 200
    )
    original = client.get(f"/api/workspaces/{wid}").json()["assignments"]["QB"]
    for replacement in [
        raw.replace(b",35,", b",99,"),
        b"\r\n".join(line for line in raw.split(b"\r\n") if b",Alpha," not in line),
        raw.replace(b",Alpha,", b",Different Person,"),
    ]:
        b = client.post(
            f"/api/workspaces/{wid}/imports", files={"file": ("replacement.csv", replacement)}
        ).json()
        p = client.get(f"/api/workspaces/{wid}/imports/{b['batch_id']}").json()
        w = activate(client, wid, p)
        assert w["assignments"]["QB"]["row_id"] == original["row_id"]
        assert w["assignments"]["QB"]["salary_cents"] == 3500
        assert w["assignments"]["QB"]["concerns"]
        # Saving an unrelated addition retains an unresolved existing selection.
        wr = next(p for p in w["players"] if p["name"] == "Synthetic Echo")
        operation = "replace" if "WR1" in w["assignments"] else "add"
        assert (
            save(
                client, w, [{"op": operation, "slot": "WR1", "entry_id": wr["entry_id"]}]
            ).status_code
            == 200
        )


def test_deadline_after_lock_wait(client: TestClient) -> None:
    # Use whole-minute clock-compatible fixture, then tighten with precise schedule evidence.
    wid, setup, preview, _ = prepared(client)
    w = activate(client, wid, preview)
    engine = engine_for(URL)
    # A real second connection holds the documented first aggregate lock.
    with engine.begin() as blocker:
        run(blocker, "SELECT id FROM contest WHERE id=:id FOR UPDATE", id=w["contest_id"])
        # Append a synthetic tightening decision without changing any immutable evidence.
        old = one(
            blocker,
            "SELECT d.* FROM lock_head h JOIN lock_decision d "
            "ON d.id=h.decision_id WHERE h.contest_id=:id LIMIT 1",
            id=w["contest_id"],
        )
        decision_id = str(uuid4())
        run(
            blocker,
            "INSERT INTO lock_decision(id,contest_id,game_id,schedule_id,previous_id,deadline) "
            "VALUES (:id,:cid,:gid,:sid,:previous,clock_timestamp()+interval '2 seconds')",
            id=decision_id,
            cid=w["contest_id"],
            gid=old["game_id"],
            sid=old["schedule_id"],
            previous=old["id"],
        )
        run(
            blocker,
            "UPDATE lock_head SET decision_id=:id WHERE contest_id=:cid AND game_id=:gid",
            id=decision_id,
            cid=w["contest_id"],
            gid=old["game_id"],
        )
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(
                save,
                client,
                w,
                [{"op": "add", "slot": "QB", "entry_id": w["players"][0]["entry_id"]}],
            )
            # Prove the save is actually waiting on a database lock before crossing the deadline.
            with engine.connect() as observer:
                for _ in range(50):
                    run(observer, "SELECT pg_stat_clear_snapshot()")
                    waiting = one(
                        observer,
                        "SELECT count(*) AS n FROM pg_stat_activity "
                        "WHERE usename=current_user AND wait_event_type='Lock' "
                        "AND query LIKE '%FOR UPDATE OF c%'",
                    )["n"]
                    if waiting:
                        break
                    time.sleep(0.02)
                assert waiting
            time.sleep(2.4)
            blocker.commit()
            response = future.result(timeout=10)
    assert response.status_code == 423, response.text
    with engine.connect() as db:
        assert (
            one(db, "SELECT count(*) AS n FROM draft_revision WHERE workspace_id=:id", id=wid)["n"]
            == 0
        )


def test_raw_transaction_rollback_and_runtime_grants(client: TestClient) -> None:
    wid, _, preview, _ = prepared(client)
    engine = engine_for(URL)
    with engine.connect() as db:
        assert one(db, "SELECT current_user AS role")["role"] == "dfs_runtime"
        tables = [
            r["tablename"]
            for r in many(db, "SELECT tablename FROM pg_tables WHERE schemaname='public'")
            if r["tablename"]
            not in {
                "alembic_version",
                "auth_flow",
                "session",
                "workspace",
                "lock_head",
                "solve_lease",
                "odds_head",
                "clock_observation",
            }
        ]
    for table in tables:
        for verb in ("UPDATE", "DELETE"):
            with pytest.raises(DBAPIError), engine.begin() as db:
                sql = (
                    f"DELETE FROM {table} WHERE false"
                    if verb == "DELETE"
                    else f"UPDATE {table} SET "
                )
                if verb == "UPDATE":
                    column = one(
                        db,
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name=:table ORDER BY ordinal_position LIMIT 1",
                        table=table,
                    )["column_name"]
                    sql += f"{column}={column} WHERE false"
                run(db, sql)
    raw = secrets.token_bytes(20)
    sha = digest(raw)
    with pytest.raises(DBAPIError), engine.begin() as db:
        run(
            db,
            "INSERT INTO raw_blob VALUES (:hash,:raw,:length,'text/csv')",
            hash=sha,
            raw=raw,
            length=len(raw),
        )
        run(
            db,
            "INSERT INTO source_capture(id,blob_hash,filename) "
            "VALUES (gen_random_uuid(),:hash,NULL)",
            hash=sha,
        )
    with engine.connect() as db:
        assert one(db, "SELECT * FROM raw_blob WHERE sha256=:hash", hash=sha) is None


@pytest.mark.parametrize(
    "fault,status",
    [
        ("sub", 403),
        ("iss", 401),
        ("aud", 401),
        ("nonce", 401),
        ("expired", 401),
        ("signature", 401),
    ],
)
def test_oidc_validation(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, fault: str, status: int
) -> None:
    monkeypatch.setenv("TEST_OIDC_FAULT", fault)
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        assert sign_in(client).status_code == status
        assert client.get("/api/session").status_code == 401


def test_auth_csrf_expiry_logout_and_unauthorized_routes(
    client: TestClient, settings: Settings
) -> None:
    wid, _, preview, _ = prepared(client)
    with TestClient(create_app(settings), base_url=ORIGIN) as anonymous:
        for path in [
            "/api/session",
            "/api/rules",
            "/api/workspaces",
            f"/api/workspaces/{wid}",
            f"/api/workspaces/{wid}/imports/{preview['id']}",
            f"/api/workspaces/{wid}/imports/{preview['id']}/raw",
        ]:
            assert anonymous.get(path).status_code == 401
        assert (
            anonymous.post(
                f"/api/workspaces/{wid}/imports", files={"file": ("x", b"x")}
            ).status_code
            == 401
        )
        assert anonymous.post(f"/api/workspaces/{wid}/draft", json={}).status_code == 401
        assert anonymous.get("/auth/callback?state=bad&code=bad").status_code == 401
    assert client.post("/auth/logout", headers={"x-csrf-token": "wrong"}).status_code == 403
    assert client.post("/auth/logout", headers={"origin": "http://evil.example"}).status_code == 403
    cookie = client.cookies.get("dfs_session")
    assert client.post("/auth/logout").status_code == 204
    client.cookies.set("dfs_session", cookie)
    assert client.get("/api/session").status_code == 401


def test_historical_import_through_postgres(client: TestClient) -> None:
    from server.ingestion_test import HISTORICAL, historical_games

    setup, _ = demo()
    setup.update(
        name="Historical fixture — not current",
        yahoo_id="historical-" + str(uuid4()),
        season="2026 historical evidence",
        round="Historical week 1",
        provenance="Preserved historical dated schedule evidence; never relabeled current",
    )
    setup["games"] = [
        {"event_key": g["id"], "away": g["away"], "home": g["home"], "kickoff": g["kickoff"]}
        for g in historical_games()
    ]
    result = command(client, "/api/workspaces", setup)
    assert result.status_code == 200, result.text
    wid = result.json()["workspace_id"]
    raw = (HISTORICAL / "raw/yahoo.csv").read_bytes()
    result = client.post(
        f"/api/workspaces/{wid}/imports", files={"file": ("historical-yahoo.csv", raw)}
    )
    assert result.status_code == 200, result.text
    bid = result.json()["batch_id"]
    preview = client.get(f"/api/workspaces/{wid}/imports/{bid}").json()
    assert preview["summary"]["records"] == 916
    assert preview["summary"]["eligible_ids"] == 905
    assert preview["summary"]["quarantined_rows"] == 11
    assert len([r for r in preview["rows"] if r["name"] == "Zamir White"]) == 2
    assert client.get(f"/api/workspaces/{wid}/imports/{bid}/raw").content == raw
    with engine_for(URL).connect() as db:
        assert one(db, "SELECT count(*) AS n FROM pool_row WHERE batch_id=:id", id=bid)["n"] == 916


def test_unknown_lock_and_changed_batch_are_rejected(client: TestClient) -> None:
    wid, setup, preview, raw = prepared(client)
    w = client.get(f"/api/workspaces/{wid}").json()
    assert (
        command(
            client,
            f"/api/workspaces/{wid}/activate",
            {"expected_revision": w["revision"], "batch_id": preview["id"], "batch_revision": 2},
        ).status_code
        == 409
    )
    w = activate(client, wid, preview)
    setup["expected_revision"] = w["revision"]
    setup["games"][0]["kickoff"] = None
    assert command(client, f"/api/workspaces/{wid}/setup", setup, method="PUT").status_code == 200
    result = client.post(
        f"/api/workspaces/{wid}/imports", files={"file": ("unknown.csv", raw)}
    ).json()
    preview = client.get(f"/api/workspaces/{wid}/imports/{result['batch_id']}").json()
    w = activate(client, wid, preview)  # Other game's rows remain inspectable/eligible.
    assert w["locked"]
    row = next(r for r in w["players"] if not r["issues"] and r["position"] == "QB")
    assert (
        save(client, w, [{"op": "add", "slot": "QB", "entry_id": row["entry_id"]}]).status_code
        == 423
    )


def test_invalid_file_keeps_active_pool_and_retains_capture(client: TestClient) -> None:
    wid, _, preview, _ = prepared(client)
    w = activate(client, wid, preview)
    invalid = b"unsupported,schema\n1,2\n"
    result = client.post(
        f"/api/workspaces/{wid}/imports", files={"file": ("invalid.csv", invalid)}
    ).json()
    p = client.get(f"/api/workspaces/{wid}/imports/{result['batch_id']}").json()
    assert p["errors"] and not p["rows"]
    assert (
        command(
            client,
            f"/api/workspaces/{wid}/activate",
            {"expected_revision": w["revision"], "batch_id": p["id"], "batch_revision": 1},
        ).status_code
        == 422
    )
    assert client.get(f"/api/workspaces/{wid}").json()["active_pool_id"] == w["active_pool_id"]
    assert client.get(f"/api/workspaces/{wid}/imports/{p['id']}/raw").content == invalid
    client.cookies.clear()
    assert sign_in(client).status_code == 303
    cookie = client.cookies.get("dfs_session")
    with engine_for(URL).begin() as db:
        run(
            db,
            "UPDATE session SET expires_at=clock_timestamp()-interval '1 second' "
            "WHERE token_hash=:hash",
            hash=digest(cookie.encode()),
        )
    assert client.get("/api/session").status_code == 401
