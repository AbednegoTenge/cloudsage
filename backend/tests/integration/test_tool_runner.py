"""The tool runner records every call as evidence, enforces limits and redacts output."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.tools  # noqa: F401
from app.aws.context import open_context
from app.core.db import get_sessionmaker
from app.models import Investigation, User
from app.repositories.investigations import InvestigationRepository
from app.tools import base
from app.tools.runner import ToolLimitReached, ToolRunner
from tests.conftest import ALICE


def _inv(api: TestClient, connection: dict) -> str:
    return api.post(
        "/api/v1/investigations",
        json={
            "prompt": "Why is api-worker-3 failing health checks?",
            "connectionId": connection["id"],
            "region": "us-east-1",
            "timeRangeHours": 6,
        },
    ).json()["id"]


def _run(db_settings, calls, max_calls=None):
    async def go():
        async with get_sessionmaker(db_settings)() as db:
            user = (await db.execute(select(User).where(User.email == ALICE))).scalar_one()
            inv = (await db.execute(select(Investigation))).scalar_one()
            now = datetime.now(UTC)
            ctx = await open_context(
                db_settings,
                role_arn="arn:aws:iam::123456789012:role/R",
                external_id=None,
                account_id=inv.account_id,
                region=inv.region,
                allowed_regions=["us-east-1"],
                start=now - timedelta(hours=6),
                end=now,
            )
            runner = ToolRunner(
                db, InvestigationRepository(db, user.id), inv, ctx, db_settings, max_calls=max_calls
            )
            results = []
            for name, args in calls:
                try:
                    results.append(await runner.run(name, args))
                except ToolLimitReached as e:
                    results.append(e)
            await db.commit()
            return results

    return asyncio.run(go())


def test_successful_calls_become_evidence(api: TestClient, db_settings, connection):
    inv_id = _inv(api, connection)
    results = _run(
        db_settings,
        [
            ("ec2_describe_instance_status", {"instance_ids": ["i-0a1b2c3d4e5f67890"]}),
            (
                "cloudwatch_get_metric_data",
                {
                    "namespace": "CWAgent",
                    "metric_name": "disk_used_percent",
                    "dimensions": [{"name": "InstanceId", "value": "i-0a1b2c3d4e5f67890"}],
                },
            ),
            (
                "logs_filter_log_events",
                {"log_group": "/platform/api-worker", "filter_pattern": "ERROR"},
            ),
            ("cloudwatch_describe_alarms", {"state": "ALARM"}),
        ],
    )
    assert all(r.ok for r in results)
    status = results[0].output["statuses"][0]
    assert status["instanceStatus"] == "impaired" and status["health"] == "unhealthy"
    assert results[1].output["summary"]["max"] == 100.0
    assert all("ERROR" in e["message"] for e in results[2].output["events"])
    assert {a["name"] for a in results[3].output["alarms"]} == {
        "api-worker-3-status-check",
        "api-worker-3-disk-high",
    }

    detail = api.get(f"/api/v1/investigations/{inv_id}").json()
    tools = detail["toolExecutions"]
    assert [t["toolName"] for t in tools] == [
        "ec2_describe_instance_status",
        "cloudwatch_get_metric_data",
        "logs_filter_log_events",
        "cloudwatch_describe_alarms",
    ]
    assert all(t["status"] == "succeeded" and t["durationMs"] >= 0 for t in tools)
    assert tools[0]["input"] == {"instance_ids": ["i-0a1b2c3d4e5f67890"], "only_impaired": False}
    assert [e["type"] for e in detail["events"]][1:] == ["tool_completed"] * 4
    assert detail["events"][1]["toolExecutionId"] == tools[0]["id"]


def test_failures_are_recorded_not_raised(api: TestClient, db_settings, connection):
    inv_id = _inv(api, connection)
    results = _run(
        db_settings,
        [
            ("ec2_describe_instances", {"instance_ids": ["not-an-id"]}),
            ("ec2_terminate_instances", {"instance_ids": ["i-0a1b2c3d4e5f67890"]}),
            ("logs_filter_log_events", {"log_group": "/does/not/exist"}),
            (
                "cloudwatch_get_metric_data",
                {
                    "namespace": "AWS/EC2",
                    "metric_name": "CPUUtilization",
                    "start": "2020-01-01T00:00:00Z",
                    "end": "2020-01-02T00:00:00Z",
                },
            ),
        ],
    )
    assert not any(r.ok for r in results)
    assert "Invalid input: instance_ids.0" in results[0].error
    assert results[1].error == "Unknown tool: ec2_terminate_instances"
    assert "Log group not found" in results[2].error
    assert "outside the investigation window" in results[3].error
    detail = api.get(f"/api/v1/investigations/{inv_id}").json()
    assert [t["status"] for t in detail["toolExecutions"]] == ["failed"] * 4
    assert [e["type"] for e in detail["events"]][1:] == ["tool_failed"] * 4


def test_tool_call_limit(api: TestClient, db_settings, connection):
    _inv(api, connection)
    results = _run(db_settings, [("cloudwatch_describe_alarms", {})] * 3, max_calls=2)
    assert results[0].ok and results[1].ok
    assert isinstance(results[2], ToolLimitReached)


def test_secrets_in_output_and_errors_are_redacted(
    api: TestClient, db_settings, connection, monkeypatch
):
    inv_id = _inv(api, connection)
    leaky = base.REGISTRY["cloudwatch_describe_alarms"]

    def leak(ctx, inp):
        return {"alarms": [{"reason": "creds AKIAIOSFODNN7EXAMPLE password=hunter2"}]}

    def explode(ctx, inp):
        raise RuntimeError("boom aws_secret_access_key=abc123")

    monkeypatch.setitem(
        base.REGISTRY,
        "cloudwatch_describe_alarms",
        base.ToolSpec(**{**leaky.__dict__, "run": leak}),
    )
    monkeypatch.setitem(
        base.REGISTRY,
        "logs_describe_log_groups",
        base.ToolSpec(**{**base.REGISTRY["logs_describe_log_groups"].__dict__, "run": explode}),
    )
    _run(db_settings, [("cloudwatch_describe_alarms", {}), ("logs_describe_log_groups", {})])
    text = str(api.get(f"/api/v1/investigations/{inv_id}").json())
    for secret in ("AKIAIOSFODNN7EXAMPLE", "hunter2", "abc123"):
        assert secret not in text
