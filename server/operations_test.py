from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from time import perf_counter

import pytest
from sqlalchemy.exc import DBAPIError

from server import late_swap
from server.application_test import URL
from server.config import Settings
from server.operations import check
from server.persistence import engine_for, one, run


def production() -> Settings:
    return Settings(
        URL,
        "https://dfs.example.com",
        "https://accounts.google.com",
        "client",
        "secret",
        "verified-subject",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "https://",
        "https://dfs.example.com/path",
        "https://user@dfs.example.com",
        "https://dfs.example.com?x=1",
        "https://dfs.example.com#x",
        "http://dfs.example.com",
    ],
)
def test_invalid_origin(origin: str) -> None:
    with pytest.raises(ValueError):
        replace(production(), origin=origin)


def test_production_identity_and_credentials(monkeypatch) -> None:
    for update in (
        {"owner_subject": ""},
        {"database_url": URL.replace("dfs_runtime", "dfs_migration")},
        {"session_seconds": 0},
    ):
        with pytest.raises(ValueError):
            replace(production(), **update)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="synthetic"):
        Settings(
            URL,
            "http://127.0.0.1:8765",
            "http://127.0.0.1:8766",
            "client",
            "secret",
            "synthetic",
            True,
        )


def test_migration_credentials_not_in_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "configured-separately")
    with pytest.raises(ValueError, match="Migration credentials"):
        production()


def test_clock_pool_saturation_and_monotonicity() -> None:
    engine = engine_for(URL)
    barrier = Barrier(5)

    def reader(_: int) -> list:
        with engine.begin() as db:
            one(db, "SELECT 1")
            barrier.wait(timeout=5)
            return [late_swap.observe(engine)["observed_at"] for _ in range(10)]

    start = perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(reader, range(5)))
        assert all(values == sorted(values) for values in results)
        with engine.connect() as db:
            high = one(db, "SELECT observed_at FROM clock_observation")["observed_at"]
        assert high == max(max(v) for v in results)
        assert perf_counter() - start < 8
        assert engine.clock_engine.pool.size() == 1
    finally:
        engine.dispose()


def test_older_observation_cannot_overwrite(monkeypatch) -> None:
    engine = engine_for(URL)
    try:
        latest = late_swap.observe(engine)
        from datetime import timedelta

        monkeypatch.setattr(
            late_swap,
            "clock",
            lambda db: {
                "at": latest["at"] - timedelta(days=1),
                "observed_at": latest["observed_at"],
            },
        )
        assert late_swap.observe(engine)["observed_at"] == latest["observed_at"]
    finally:
        engine.dispose()


def test_runtime_grants_and_schema() -> None:
    engine = engine_for(URL)
    try:
        with engine.connect() as db:
            assert check(db, production=True)["schema_version"] == "0005_increment6"
        with pytest.raises(DBAPIError):
            with engine.begin() as db:
                run(db, "UPDATE operational_state SET recovery_required=false")
        with pytest.raises(DBAPIError):
            with engine.begin() as db:
                run(db, "DELETE FROM operational_event")
    finally:
        engine.dispose()


def test_production_cookie_and_readiness() -> None:
    from fastapi.responses import RedirectResponse
    from fastapi.testclient import TestClient

    from server.app import create_app
    from server.auth import Auth

    engine = engine_for(URL)
    try:
        response = RedirectResponse("/")
        Auth(production(), engine).cookie(response, "dfs_session", "test-opaque", 60)
        cookie = response.headers["set-cookie"]
        assert all(flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=lax", "Max-Age=60"))
        with TestClient(create_app(production())) as client:
            assert client.get("/ready").status_code == 200
            assert client.get("/api/session").status_code == 401
    finally:
        engine.dispose()
