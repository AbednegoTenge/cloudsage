import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "CLOUDSAGE_TEST_DATABASE_URL",
    "postgresql+psycopg://cloudsage:cloudsage@localhost:5432/cloudsage_test",
)
TABLES = (
    "investigation_events, tool_executions, investigation_reports, investigations, "
    "aws_connections, users"
)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment=Environment.TEST)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


# ---------- Postgres-backed fixtures (integration tests marked ``db``) ----------


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Migrate the test database to head once per run. Skips if Postgres is unreachable."""
    try:
        psycopg.connect(_sync_dsn(TEST_DATABASE_URL), connect_timeout=3).close()
    except psycopg.OperationalError as e:
        pytest.skip(f"Test database unavailable: {e.__class__.__name__}")
    env = os.environ | {"CLOUDSAGE_DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )
    return TEST_DATABASE_URL


@pytest.fixture
def db_settings(migrated_db: str) -> Iterator[Settings]:
    with psycopg.connect(_sync_dsn(migrated_db), autocommit=True) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        conn.execute("ALTER SEQUENCE investigation_number_seq RESTART WITH 1001")
    yield Settings(
        _env_file=None,
        environment=Environment.TEST,
        database_url=migrated_db,
        sse_poll_interval_seconds=0.05,
        investigation_timeout_seconds=10,
    )


@pytest.fixture
def api(db_settings: Settings) -> Iterator[TestClient]:
    """Client acting as alice@example.com against a clean, migrated database."""
    with TestClient(create_app(db_settings), headers={"X-CloudSage-User": ALICE}) as c:
        yield c


ALICE = "alice@example.com"
BOB = "bob@example.com"


def connection_body(**overrides) -> dict:
    body = {
        "name": "prod-us-east-1",
        "accountId": "123456789012",
        "roleArn": "arn:aws:iam::123456789012:role/CloudSageReadOnly",
        "externalId": "cloudsage-ext-1",
        "defaultRegion": "us-east-1",
        "allowedRegions": ["us-east-1", "us-west-2"],
    }
    return body | overrides


@pytest.fixture
def connection(api: TestClient) -> dict:
    r = api.post("/api/v1/connections", json=connection_body())
    assert r.status_code == 201, r.text
    return r.json()
