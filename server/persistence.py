import hashlib
import json
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine


def engine_for(url: str) -> Engine:
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=8,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=15000 -c lock_timeout=7000 -c timezone=UTC",
        },
    )
    # Never borrow an observation connection from a pool whose borrowers hold domain locks.
    engine.clock_engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_timeout=8,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=2000 -c lock_timeout=1000 -c timezone=UTC",
        },
    )
    event.listen(engine, "engine_disposed", lambda e: e.clock_engine.dispose())
    return engine


def uid() -> str:
    return str(uuid4())


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def one(db: Connection, sql: str, **params: object) -> dict | None:
    row = db.execute(text(sql), params).mappings().first()
    return dict(row) if row else None


def many(db: Connection, sql: str, **params: object) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def run(db: Connection, sql: str, **params: object) -> None:
    db.execute(text(sql), params)
