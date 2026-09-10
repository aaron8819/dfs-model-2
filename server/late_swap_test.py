"""Synthetic dated evidence; real PostgreSQL runtime transactions and OIDC requests."""

import threading
import time
from datetime import timedelta
from uuid import uuid4

import pytest

from server import application_test as boundary
from server import completion_test
from server.application_test import ADMIN, URL, activate, command, save
from server.completion_test import accept, solve, stage
from server.decision_test import apply, poll, post, read, ready
from server.persistence import canonical, engine_for, one, run
from tools.decision_demo import decision_demo

client = boundary.client
settings = boundary.settings


@pytest.fixture
def full(client, monkeypatch):
    fixture = decision_demo()
    files = {p: (p + ".csv", text.encode()) for p, text in fixture["projections"].items()}
    monkeypatch.setattr(
        completion_test,
        "completion_demo",
        lambda: (fixture["setup"], fixture["yahoo"].encode(), files),
    )
    w = ready(client)
    names = ["Alpha", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "Juliet", "India"]
    slots = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DEF"]
    players = {p["name"].split()[-1]: p for p in w["players"]}
    r = save(
        client,
        w,
        [dict(op="add", slot=s, entry_id=players[n]["entry_id"]) for s, n in zip(slots, names)],
    )
    assert r.status_code == 200, r.text
    return read(client, w), fixture, files


def record(client, w):
    r = post(
        client,
        w,
        "entered",
        draft_id=w["draft_id"],
        attestation="Record as entered in Yahoo",
        reason="Verified synthetic Yahoo lineup",
    )
    assert r.status_code == 200, r.text
    return read(client, w)


def deadline(db, w, game, delay=-1):
    old = one(
        db,
        "SELECT d.* FROM lock_head h JOIN lock_decision d ON d.id=h.decision_id "
        "WHERE h.contest_id=:cid AND h.game_id=:gid",
        cid=w["contest_id"],
        gid=game,
    )
    lid = str(uuid4())
    run(
        db,
        "INSERT INTO lock_decision(id,contest_id,game_id,schedule_id,previous_id,deadline) "
        "VALUES (:id,:cid,:gid,:sid,:old,clock_timestamp()+:delay * interval '1 second')",
        id=lid,
        cid=w["contest_id"],
        gid=game,
        sid=old["schedule_id"],
        old=old["id"],
        delay=delay,
    )
    run(
        db,
        "UPDATE lock_head SET decision_id=:id WHERE contest_id=:cid AND game_id=:gid",
        id=lid,
        cid=w["contest_id"],
        gid=game,
    )


def lock_game(w, index=0):
    with engine_for(URL).begin() as db:
        deadline(db, w, w["games"][index]["id"])


def body(w, **updates):
    return dict(
        expected_revision=w["revision"],
        draft_id=w["draft_id"],
        entered_id=w["entered"]["id"] if w["entered"] else None,
        assignments={
            s: p["row_id"]
            for s, p in (w["entered"] or {"assignments": w["assignments"]})["assignments"].items()
        },
        attestation="Correct historical Yahoo facts; this does not authorize a late selection",
        reason="Correct historical synthetic record",
        reference="Yahoo screenshot test reference",
        **updates,
    )


def reconcile(client, w, data=None):
    data = data or body(w)
    preview = command(client, f"/api/workspaces/{w['id']}/reconcile-preview", data)
    assert preview.status_code == 200, preview.text
    data = {**data, "preview_hash": preview.json()["preview_hash"]}
    r = command(client, f"/api/workspaces/{w['id']}/reconcile", data)
    assert r.status_code == 200, r.text
    return read(client, w)


def test_late_swap_complete_alternatives_record_and_retry(client, full):
    w, _, _ = full
    w = record(client, w)
    entered = w["entered"]
    lock_game(w, 1)
    w = read(client, w)
    assert not w["locked"] and w["late_swap"]["fixed"]
    fixed = {s: p["entry_id"] for s, p in w["late_swap"]["fixed"].items()}
    result = poll(client, w, post(client, w, "alternatives", include=[], exclude=[]))
    assert result["status"] == "ready", result
    assert len(result["candidates"]) > 1
    for candidate in result["candidates"]:
        assert all(
            next(p for p in candidate["preview"] if p["slot"] == s)["entry_id"] == e
            for s, e in fixed.items()
        )
    w = apply(client, w, result, len(result["candidates"]) - 1)
    assert w["entered"] == entered
    data = dict(
        expected_revision=w["revision"],
        draft_id=w["draft_id"],
        attestation="Record as entered in Yahoo",
        reason="Manually updated synthetic Yahoo",
    )
    key = str(uuid4())
    first = command(client, f"/api/workspaces/{w['id']}/entered", data, key)
    assert first.status_code == 200, first.text
    lock_game(w, 0)
    assert command(client, f"/api/workspaces/{w['id']}/entered", data, key).json() == first.json()
    w = read(client, w)
    assert w["late_swap"]["all_locked"] and w["entered_status"] == "matches"
    assert post(client, w, "complete").status_code == 423
    assert post(client, w, "undo").status_code == 423


@pytest.mark.parametrize("slots", [("RB1", "FLEX"), ("WR1", "WR3")])
def test_fixed_actual_slots_never_move(client, full, slots):
    w = record(client, full[0])
    lock_game(w)
    w = read(client, w)
    a, b = slots
    ops = [
        dict(op="remove", slot=a),
        dict(op="remove", slot=b),
        dict(op="add", slot=b, entry_id=w["assignments"][a]["entry_id"]),
        dict(op="add", slot=a, entry_id=w["assignments"][b]["entry_id"]),
    ]
    r = save(client, w, ops)
    assert r.status_code == 423, r.text
    assert read(client, w)["draft_id"] == w["draft_id"]


def test_missing_entered_reconcile_and_intervening_heads(client, full):
    w = full[0]
    lock_game(w)
    w = read(client, w)
    assert "Missing entered" in " ".join(w["late_swap"]["blockers"])
    assert post(client, w, "complete").status_code == 423
    assert (
        post(
            client,
            w,
            "entered",
            draft_id=w["draft_id"],
            attestation="Record as entered in Yahoo",
            reason="Cannot infer submission",
        ).status_code
        == 423
    )
    data = body(w)
    w = reconcile(client, w, data)
    assert not w["locked"] and w["entered_status"] == "matches"
    stale = command(client, f"/api/workspaces/{w['id']}/reconcile", data)
    assert stale.status_code == 409
    history = client.get(f"/api/workspaces/{w['id']}/decision-history").json()
    assert len(history["entered"]) == 1


def test_explicit_historical_correction_preserves_evidence_and_draft(client, full):
    w = record(client, full[0])
    lock_game(w)
    w = read(client, w)
    original = w["entered"]
    data = body(w)
    data["assignments"]["WR1"], data["assignments"]["WR3"] = (
        data["assignments"]["WR3"],
        data["assignments"]["WR1"],
    )
    r = command(client, f"/api/workspaces/{w['id']}/reconcile-preview", data)
    assert r.status_code == 200, r.text
    assert r.json()["draft"]["WR1"]["name"] != w["assignments"]["WR1"]["name"]
    w = reconcile(client, w, data)
    assert w["entered"]["parent_id"] == original["id"]
    assert w["entered"]["created_at"] >= original["created_at"]
    for slot, p in full[0]["assignments"].items():
        if slot not in w["late_swap"]["fixed"]:
            assert w["assignments"][slot]["entry_id"] == p["entry_id"]
    history = client.get(f"/api/workspaces/{w['id']}/decision-history").json()
    assert any(
        e["id"] == original["id"] and e["assignments"] == original["assignments"]
        for e in history["entered"]
    )
    assert post(client, w, "undo").status_code == 422


def test_mismatch_restore_and_unentered_keep_conflict(client, full):
    w = record(client, full[0])
    p = next(p for p in w["players"] if p["name"].endswith("Bravo"))
    assert (
        save(client, w, [dict(op="replace", slot="QB", entry_id=p["entry_id"])]).status_code == 200
    )
    w = read(client, w)
    lock_game(w, 1)
    w = read(client, w)
    assert w["locked"]
    w = reconcile(client, w)
    assert "QB" not in w["assignments"]  # explicit preview removes the unentered started selection
    assert post(client, w, "alternatives", include=[p["yahoo_id"]], exclude=[]).status_code == 422
    assert (
        post(
            client,
            w,
            "preferences",
            entry_id=p["entry_id"],
            subject_id=p["subject_id"],
            value="keep",
        ).status_code
        == 200
    )
    w = read(client, w)
    assert post(client, w, "complete").status_code == 422


@pytest.mark.parametrize("refresh", ["absent", "identity", "salary", "out"])
def test_fixed_refresh_authority_missing_projection_and_avoid(client, full, refresh):
    w, fixture, files = full
    w = record(client, w)
    lock_game(w)
    w = read(client, w)
    p = w["assignments"]["QB"]
    assert (
        post(
            client,
            w,
            "preferences",
            entry_id=p["entry_id"],
            subject_id=p["subject_id"],
            value="avoid",
        ).status_code
        == 200
    )
    w = read(client, w)
    raw = fixture["yahoo"]
    if refresh == "absent":
        raw = "\n".join(line for line in raw.splitlines() if ",Alpha," not in line) + "\n"
    elif refresh == "identity":
        raw = raw.replace(",Alpha,", ",ChangedIdentity,")
    elif refresh == "salary":
        raw = raw.replace(",35,", ",199,")
    else:
        lines = raw.splitlines()
        raw = (
            "\n".join(line.replace(", , ", ",O, ") if ",Alpha," in line else line for line in lines)
            + "\n"
        )
    bid = client.post(
        f"/api/workspaces/{w['id']}/imports", files={"file": ("new.csv", raw.encode())}
    ).json()["batch_id"]
    w = activate(client, w["id"], client.get(f"/api/workspaces/{w['id']}/imports/{bid}").json())
    context = dict(
        season=fixture["setup"]["season"],
        period=fixture["setup"]["round"],
        scoring="half-ppr-baseline",
        evidence="Synthetic matching baseline",
        source_context="Synthetic dated projections",
        material_settings_match=True,
    )
    w = accept(client, w, stage(client, w, files, context))[0]
    result = poll(client, w, post(client, w, "alternatives", include=[], exclude=[p["yahoo_id"]]))
    assert result["status"] == "ready", result
    candidate = result["candidates"][0]
    qb = next(x for x in candidate["preview"] if x["slot"] == "QB")
    assert qb["subject_id"] == p["subject_id"] and qb["salary_cents"] == 3500
    if refresh in {"absent", "identity"}:
        assert candidate["result"]["whole_total_units"] is None
        assert p["yahoo_id"] in candidate["result"]["missing_fixed"]
        assert candidate["result"]["editable_units"] > 0
    w = apply(client, w, result)
    assert w["late_swap"]["fixed"]["QB"]["salary_cents"] == 3500


def test_stale_time_without_revision_and_undo_across_kickoff(client, full):
    w = record(client, full[0])
    result = solve(client, w)
    lock_game(w)
    updated = read(client, w)
    assert updated["revision"] == w["revision"]
    r = post(client, w, f"completions/{result['request_id']}/apply")
    assert r.status_code == 409, r.text
    assert read(client, w)["draft_id"] == w["draft_id"]
    assert post(client, w, "undo").status_code == 423
    # Positive control: a safe unlocked removal and whole-action Undo succeed.
    assert save(client, updated, [dict(op="remove", slot="TE")]).status_code == 200
    updated = read(client, w)
    assert post(client, updated, "undo").status_code == 200


@pytest.mark.parametrize("valid", [False, True])
def test_actual_lock_wait_crosses_kickoff_zero_invalid_writes(client, full, valid):
    w = record(client, full[0])
    engine = engine_for(URL)
    responses = []
    with engine.begin() as blocker:
        run(blocker, "SELECT id FROM contest WHERE id=:id FOR UPDATE", id=w["contest_id"])
        deadline(blocker, w, w["games"][0]["id"], 2)
        thread = threading.Thread(
            target=lambda: responses.append(
                save(client, w, [dict(op="remove", slot="TE" if valid else "QB")])
            )
        )
        thread.start()
        for _ in range(100):
            with engine.connect() as observer:
                waiting = one(
                    observer,
                    "SELECT count(*) AS n FROM pg_stat_activity "
                    "WHERE wait_event_type='Lock' AND query LIKE '%FOR UPDATE OF c%'",
                )["n"]
            if waiting:
                break
            time.sleep(0.025)
        assert waiting, "Must observe an actual PostgreSQL lock wait"
        time.sleep(2.1)
    thread.join(10)
    assert responses[0].status_code == (200 if valid else 423), responses[0].text
    changed = read(client, w)
    assert changed["revision"] == w["revision"] + (1 if valid else 0)
    assert changed["entered"] == w["entered"]


def test_schedule_later_unknown_backward_and_all_locked(client, full, monkeypatch):
    from server import late_swap

    w, fixture, _ = full
    w = record(client, w)
    lock_game(w)
    w = read(client, w)
    setup = dict(fixture["setup"], expected_revision=w["revision"])
    r = command(client, f"/api/workspaces/{w['id']}/setup", setup, method="PUT")
    assert r.status_code == 200, r.text
    w = read(client, w)
    assert w["late_swap"]["started"] == [w["games"][0]["id"]]
    real_clock = late_swap.clock

    def backward(db):
        sample = real_clock(db)
        return {**sample, "at": sample["observed_at"] - timedelta(hours=1)}

    monkeypatch.setattr(late_swap, "clock", backward)
    assert "backward" in " ".join(read(client, w)["late_swap"]["blockers"])
    monkeypatch.setattr(late_swap, "clock", real_clock)
    setup["expected_revision"] = w["revision"]
    setup["games"][1]["kickoff"] = None
    assert (
        command(client, f"/api/workspaces/{w['id']}/setup", setup, method="PUT").status_code == 200
    )
    assert read(client, w)["locked"]


@pytest.mark.parametrize("field", ["salary_cents", "subject_id", "game_id"])
def test_disputed_fixed_facts_block_with_specific_recovery(client, full, field):
    w = record(client, full[0])
    lock_game(w)
    # Isolated migration-role corruption simulates incomplete legacy evidence.
    with engine_for(ADMIN).begin() as db:
        altered = w["entered"]["assignments"]
        altered["QB"][field] = None
        run(
            db,
            "UPDATE entered_revision SET assignments=CAST(:a AS jsonb) WHERE id=:id",
            a=canonical(altered),
            id=w["entered"]["id"],
        )
    w = read(client, w)
    assert "QB:" in " ".join(w["late_swap"]["blockers"])
    assert post(client, w, "complete").status_code == 423


def test_declared_dispute_is_durable_and_reconciliation_resolves(client, full):
    w = record(client, full[0])
    lock_game(w)
    fixed = w["assignments"]["QB"]
    blocked = post(
        client,
        w,
        "preferences",
        entry_id=fixed["entry_id"],
        subject_id=fixed["subject_id"],
        value="avoid",
        remove_selected=True,
    )
    assert blocked.status_code == 423
    assert read(client, w)["revision"] == w["revision"]
    original = w["entered"]
    r = post(
        client,
        w,
        "entered-dispute",
        reason="Actual Yahoo facts need correction",
        reference="Synthetic Yahoo verification reference",
    )
    assert r.status_code == 200, r.text
    w = read(client, w)
    assert "disputed" in " ".join(w["late_swap"]["blockers"])
    assert w["entered"]["assignments"] == original["assignments"]
    assert post(client, w, "complete").status_code == 423
    w = reconcile(client, w)
    assert not w["late_swap"]["blockers"]
    assert len(client.get(f"/api/workspaces/{w['id']}/decision-history").json()["entered"]) == 3


def test_intervening_reconciliation_invalidates_running_proposal(client, full, monkeypatch):
    from server import completion
    from server.recommendation.solver import solve as direct_solve

    w = record(client, full[0])
    lock_game(w)
    w = read(client, w)
    entered = threading.Event()
    release = threading.Event()

    def held(data, **kwargs):
        entered.set()
        assert release.wait(10)
        return direct_solve(data)

    monkeypatch.setattr(completion, "run_solve", held)
    response = post(client, w, "complete")
    assert response.status_code == 202
    assert entered.wait(5)
    try:
        updated = reconcile(client, w)
    finally:
        release.set()
    result = poll(client, w, response)
    assert result["stale"]
    assert post(client, updated, f"completions/{result['request_id']}/apply").status_code == 409


def test_reconciliation_requires_explicit_displaced_draft_plan(client, full):
    w = record(client, full[0])
    # A pregame rearrangement puts an editable RB in the future fixed RB1 slot.
    a, b = w["assignments"]["RB1"], w["assignments"]["FLEX"]
    assert (
        save(
            client,
            w,
            [
                dict(op="remove", slot="RB1"),
                dict(op="remove", slot="FLEX"),
                dict(op="add", slot="RB1", entry_id=b["entry_id"]),
                dict(op="add", slot="FLEX", entry_id=a["entry_id"]),
            ],
        ).status_code
        == 200
    )
    w = read(client, w)
    lock_game(w)
    w = read(client, w)
    data = body(w)
    assert command(client, f"/api/workspaces/{w['id']}/reconcile-preview", data).status_code == 422
    data["draft_assignments"] = {s: p["row_id"] for s, p in w["assignments"].items()}
    data["draft_assignments"].update(RB1=a["row_id"], FLEX=b["row_id"])
    w = reconcile(client, w, data)
    assert w["assignments"]["FLEX"]["entry_id"] == b["entry_id"]


def test_reconciliation_owner_boundaries(client, full):
    w = full[0]
    routes = {
        "reconcile": body(w),
        "reconcile-preview": body(w),
        "entered-dispute": dict(
            expected_revision=w["revision"],
            reason="Synthetic owner boundary",
            reference="Synthetic Yahoo evidence",
        ),
    }
    for route, data in routes.items():
        assert command(client, f"/api/workspaces/{uuid4()}/{route}", data).status_code == 404
    client.cookies.clear()
    for route, data in routes.items():
        assert command(client, f"/api/workspaces/{w['id']}/{route}", data).status_code == 401


def test_reconciliation_preview_cannot_change_across_kickoff_wait(client, full):
    w = full[0]
    data = body(w)
    preview = command(client, f"/api/workspaces/{w['id']}/reconcile-preview", data)
    assert preview.status_code == 200, preview.text
    data["preview_hash"] = preview.json()["preview_hash"]
    responses = []
    engine = engine_for(URL)
    with engine.begin() as blocker:
        run(blocker, "SELECT id FROM contest WHERE id=:id FOR UPDATE", id=w["contest_id"])
        deadline(blocker, w, w["games"][0]["id"], 2)
        thread = threading.Thread(
            target=lambda: responses.append(
                command(client, f"/api/workspaces/{w['id']}/reconcile", data)
            )
        )
        thread.start()
        for _ in range(100):
            with engine.connect() as observer:
                waiting = one(
                    observer,
                    "SELECT count(*) AS n FROM pg_stat_activity "
                    "WHERE wait_event_type='Lock' AND query LIKE '%FOR UPDATE OF c%'",
                )["n"]
            if waiting:
                break
            time.sleep(0.025)
        assert waiting
        time.sleep(2.1)
    thread.join(10)
    assert responses[0].status_code == 409, responses[0].text
    unchanged = read(client, w)
    assert unchanged["draft_id"] == w["draft_id"] and unchanged["entered"] is None
    with engine.connect() as db:
        assert (
            one(
                db, "SELECT count(*) AS n FROM entered_revision WHERE workspace_id=:id", id=w["id"]
            )["n"]
            == 0
        )
    # Explicitly reviewing the now-fixed scope recovers without guessing.
    assert reconcile(client, unchanged)["entered_status"] == "matches"
