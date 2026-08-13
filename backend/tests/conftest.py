"""Shared fixtures.

These tests use a real Postgres and a real Redis rather than mocks, because
the behaviour worth testing here — an ON CONFLICT insert, an atomic SADD —
is behaviour of those systems, and a mock would only assert that the mock
works.

They run against a SEPARATE database (`logipulse_test`) and a separate Redis
db, created here if absent. That matters: the workers and simulator write to
the live database continuously, so sharing it would both corrupt the tests
and let the tests wipe a running fleet.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import dotenv_values
from urllib.parse import urlsplit, urlunsplit

# Redirect to the test stores BEFORE anything imports app.core.config.
# Environment variables take precedence over .env in pydantic-settings.
_env = {**dotenv_values(".env"), **os.environ}

_db_url = _env.get(
    "DATABASE_URL",
    "postgresql+psycopg://logipulse:logipulse@localhost:5432/logipulse",
)
_redis_url = _env.get("REDIS_URL", "redis://localhost:6379/0")

def _swap_path(url: str, new_path: str) -> str:
    """Replace the database name while preserving query parameters —
    a DSN may legitimately carry ?host=... or ?sslmode=..."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path="/" + new_path))


TEST_DB_URL = _swap_path(_db_url, "logipulse_test")
TEST_REDIS_URL = _swap_path(_redis_url, "15")

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL
os.environ.setdefault("KAFKA_BOOTSTRAP", "localhost:19092")


def _create_test_database() -> None:
    """CREATE DATABASE cannot run inside a transaction, so this uses a raw
    autocommit connection to the default database."""
    import psycopg

    admin = _swap_path(_db_url, "postgres").replace(
        "postgresql+psycopg://", "postgresql://"
    )

    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'logipulse_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE logipulse_test")


_create_test_database()

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models import Alert, Route, Shipment, ShipmentEvent  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def clean(db):
    """Empty the test tables before and after each test."""
    def wipe():
        db.query(ShipmentEvent).delete()
        db.query(Alert).delete()
        db.query(Shipment).delete()
        db.query(Route).delete()
        db.commit()

    wipe()
    yield db
    wipe()


@pytest.fixture
def route(clean):
    r = Route(
        origin="Mumbai", destination="Singapore",
        origin_lat=18.9388, origin_lon=72.8354,
        dest_lat=1.2644, dest_lon=103.8223,
        distance_km=3900, expected_duration_hours=168,
    )
    clean.add(r)
    clean.commit()
    clean.refresh(r)
    return r


@pytest.fixture
def shipment(clean, route):
    s = Shipment(
        shipment_number="SHP-TEST-1",
        route_id=route.id,
        status="IN_TRANSIT",
        mode="SEA",
        progress=0.25,
        current_lat=14.0, current_lon=81.0,
        expected_delivery=datetime.now(timezone.utc) + timedelta(hours=100),
    )
    clean.add(s)
    clean.commit()
    clean.refresh(s)
    return s


@pytest.fixture
async def redis():
    from app.cache.client import make_client
    r = make_client()
    await r.flushdb()          # safe: db 15, not the live one
    yield r
    await r.flushdb()
    await r.aclose()
