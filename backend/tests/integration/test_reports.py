import asyncio
import json

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models import Investigation, User
from app.repositories.investigations import InvestigationRepository
from app.services.reports import generate_report
from tests.conftest import ALICE, BOB, _sync_dsn
from tests.fakes import ScriptedModel

DISK = {
    "kind": "metric_series",
    "label": "disk_used_percent",
    "unit": "Percent",
    "points": [{"t": "2026-11-23T10:00:00Z", "v": 100}],
}
DRAFT = {
    "summary": "The root volume is full.",
    "severity": "high",
    "confidence": "medium",
    "observations": [{"statement": "Disk usage is 100%.", "evidence": ["E1"]}],
    "hypotheses": [
        {
            "title": "Logs filled the disk",
            "statement": "Logs grew unbounded.",
            "confidence": "medium",
            "supporting_facts": ["F1"],
        }
    ],
    "recommendations": [{"title": "Rotate logs", "detail": "Enable logrotate.", "priority": "now"}],
    "limitations": ["Only one metric was available."],
}


def _setup(api: TestClient, db_settings, connection: dict) -> str:
    inv = api.post(
        "/api/v1/investigations",
        json={
            "prompt": "Why is i-0a1b2c3d4e5f67890 failing health checks?",
            "connectionId": connection["id"],
            "region": "us-east-1",
            "timeRangeHours": 6,
        },
    ).json()
    with psycopg.connect(_sync_dsn(db_settings.database_url), autocommit=True) as c:
        c.execute(
            "INSERT INTO tool_executions (id, investigation_id, tool_name, service, input, output,"
            " status, duration_ms, started_at) SELECT gen_random_uuid(), id,"
            " 'cloudwatch_get_metric_data', 'cloudwatch', %s, %s, 'succeeded', 120, now()"
            " FROM investigations",
            (json.dumps({"metric": "disk_used_percent"}), json.dumps(DISK)),
        )
    return inv["id"]


def _generate(db_settings, model, email=ALICE):
    async def go():
        async with get_sessionmaker(db_settings)() as db:
            user = (await db.execute(select(User).where(User.email == email))).scalar_one()
            repo = InvestigationRepository(db, user.id)
            inv = (await db.execute(select(Investigation))).scalar_one()
            await generate_report(db, repo, db_settings, inv, model=model)
            await db.commit()

    asyncio.run(go())


def test_report_stored_separately_from_evidence(api: TestClient, db_settings, connection):
    inv_id = _setup(api, db_settings, connection)
    before = api.get(f"/api/v1/investigations/{inv_id}").json()["toolExecutions"]
    _generate(db_settings, ScriptedModel(DRAFT))

    detail = api.get(f"/api/v1/investigations/{inv_id}").json()
    assert detail["toolExecutions"] == before  # evidence untouched
    report = detail["report"]
    evidence_id = before[0]["id"]
    assert report["observations"] == [
        {"statement": "Disk usage is 100%.", "evidenceIds": [evidence_id]}
    ]
    assert report["metrics"][0]["evidenceId"] == evidence_id
    assert report["hypotheses"][0]["supportingObservations"] == [0]
    assert report["confidence"] == "medium"
    assert report["modelId"] == "scripted-model"
    assert report["limitations"] == ["Only one metric was available."]
    assert [e["type"] for e in detail["events"]] == ["queued", "analyzing", "report_ready"]
    inv = detail["investigation"]
    assert inv["summary"] == "The root volume is full." and inv["severity"] == "high"
    # Other users still can't see it.
    assert (
        api.get(f"/api/v1/investigations/{inv_id}", headers={"X-CloudSage-User": BOB}).status_code
        == 404
    )


def test_regenerating_replaces_the_report(api: TestClient, db_settings, connection):
    inv_id = _setup(api, db_settings, connection)
    _generate(db_settings, ScriptedModel(DRAFT))
    _generate(db_settings, ScriptedModel(DRAFT | {"summary": "Second pass."}))
    assert api.get(f"/api/v1/investigations/{inv_id}").json()["report"]["summary"] == (
        "Second pass."
    )


def test_unconfigured_bedrock_is_reported(api: TestClient, db_settings, connection):
    import pytest

    from app.services.reports import ModelUnavailable

    _setup(api, db_settings, connection)
    with pytest.raises(ModelUnavailable, match="not configured"):
        _generate(db_settings, None)
