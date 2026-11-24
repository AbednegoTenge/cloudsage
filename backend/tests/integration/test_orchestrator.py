"""End-to-end investigations on mock AWS with a scripted stand-in for Bedrock."""

import time
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ALICE, _sync_dsn, connection_body
from tests.fakes import ScriptedModel, Sleep, ToolCall

SICK = "i-0a1b2c3d4e5f67890"
GATHER = [
    ToolCall("ec2_describe_instance_status", {"instance_ids": [SICK]}),
    ToolCall(
        "cloudwatch_get_metric_data",
        {
            "namespace": "CWAgent",
            "metric_name": "disk_used_percent",
            "dimensions": [{"name": "InstanceId", "value": SICK}],
            "stat": "Maximum",
        },
    ),
    ToolCall(
        "logs_filter_log_events", {"log_group": "/platform/api-worker", "filter_pattern": "ERROR"}
    ),
    "Status checks are impaired, disk is at 100% and logs show write failures.",
]
REPORT = {
    "summary": "api-worker-3's root volume is full, so its health checks fail.",
    "severity": "high",
    "confidence": "high",
    "observations": [
        {"statement": "Instance status check is impaired.", "evidence": ["E1"]},
        {"statement": "disk_used_percent reached 100%.", "evidence": ["E2"]},
        {"statement": "Logs show 'No space left on device'.", "evidence": ["E3"]},
    ],
    "hypotheses": [
        {
            "title": "Disk exhaustion",
            "statement": "Logs filled the root volume.",
            "confidence": "high",
            "likelihood": 0.85,
            "supporting_facts": ["F1", "F2", "F3"],
        }
    ],
    "recommendations": [
        {"title": "Free disk space", "detail": "Rotate and ship logs.", "priority": "now"}
    ],
    "limitations": [],
}


class Factory:
    def __init__(self, model):
        self.model = model

    def __call__(self, settings):
        if self.model is None:
            from app.agent.model import build_model

            return build_model(settings)  # unconfigured in tests: raises
        return self.model


@pytest.fixture
def make_client(db_settings) -> Iterator:
    clients = []

    def make(model, **overrides):
        settings = db_settings.model_copy(update={"investigation_autostart": True, **overrides})
        c = TestClient(
            create_app(settings, model_factory=Factory(model)), headers={"X-CloudSage-User": ALICE}
        )
        c.__enter__()
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def start(c: TestClient, prompt=f"Why is {SICK} failing health checks?") -> str:
    conn = c.get("/api/v1/connections").json()
    cid = (
        conn[0]["id"]
        if conn
        else c.post("/api/v1/connections", json=connection_body()).json()["id"]
    )
    r = c.post(
        "/api/v1/investigations",
        json={"prompt": prompt, "connectionId": cid, "region": "us-east-1", "timeRangeHours": 6},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def wait(c: TestClient, inv_id: str, timeout=15.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        d = c.get(f"/api/v1/investigations/{inv_id}").json()
        if d["investigation"]["status"] not in ("queued", "running"):
            return d
        time.sleep(0.05)
    raise AssertionError("investigation did not finish")


def test_full_investigation(make_client):
    model = ScriptedModel(*GATHER, REPORT)
    c = make_client(model)
    inv_id = start(c)
    d = wait(c, inv_id)

    inv = d["investigation"]
    assert inv["status"] == "completed" and inv["completedAt"]
    assert inv["severity"] == "high" and inv["toolCallCount"] == 3
    tools = d["toolExecutions"]
    assert [t["toolName"] for t in tools] == [
        "ec2_describe_instance_status",
        "cloudwatch_get_metric_data",
        "logs_filter_log_events",
    ]
    assert all(t["status"] == "succeeded" for t in tools)

    report = d["report"]
    assert [o["evidenceIds"] for o in report["observations"]] == [[t["id"]] for t in tools]
    assert report["metrics"][0]["evidenceId"] == tools[1]["id"]
    assert report["metrics"][0]["points"][-1]["v"] == 100.0  # copied from the tool, not the model
    assert report["logExcerpts"][0]["evidenceId"] == tools[2]["id"]
    assert report["hypotheses"][0]["supportingObservations"] == [0, 1, 2]

    types = [e["type"] for e in d["events"]]
    assert types == [
        "queued",
        "planning",
        *["tool_started", "tool_completed"] * 3,
        "analyzing",
        "report_ready",
    ]

    # The investigator saw only the read-only tools, and every result as untrusted data.
    names = {s["name"] for s in model.requests[0]["tool_specs"]}
    assert names == {
        "ec2_describe_instances",
        "ec2_describe_instance_status",
        "cloudwatch_get_metric_data",
        "cloudwatch_describe_alarms",
        "logs_filter_log_events",
        "logs_describe_log_groups",
    }
    results = model.tool_results()
    assert len(results) == 3 and all(r.startswith("<untrusted_data nonce=") for r in results)

    # The live stream replays everything and ends.
    with c.stream("GET", f"/api/v1/investigations/{inv_id}/stream") as r:
        body = "".join(r.iter_text())
    assert body.count("event: investigation") == len(types) and "event: end" in body


def test_bedrock_not_configured_fails_clearly(make_client):
    c = make_client(None)
    d = wait(c, start(c))
    assert d["investigation"]["status"] == "failed"
    assert "Amazon Bedrock is not configured" in d["events"][-1]["message"]
    assert d["events"][-1]["type"] == "failed"
    assert d["investigation"]["summary"].startswith("Amazon Bedrock is not configured")


def test_tool_budget_from_user_settings(make_client):
    model = ScriptedModel(*GATHER, REPORT)
    c = make_client(model)
    s = c.get("/api/v1/settings").json()
    c.put("/api/v1/settings", json=s | {"maxToolCalls": 2})
    d = wait(c, start(c))
    assert d["investigation"]["status"] == "completed"
    assert len(d["toolExecutions"]) == 2
    assert "limit of 2 reached" in model.tool_results()[-1]
    # The third observation cited evidence that was never collected, so it was dropped.
    assert len(d["report"]["observations"]) == 2
    assert any("did not cite collected evidence" in x for x in d["report"]["limitations"])


def test_failed_tool_calls_are_evidence_too(make_client):
    model = ScriptedModel(
        ToolCall("logs_filter_log_events", {"log_group": "/no/such/group"}),
        ToolCall("ec2_describe_instances", {"instance_ids": ["bogus"]}),
        "Nothing useful was found.",
        REPORT
        | {
            "observations": [{"statement": "The log group does not exist.", "evidence": ["E1"]}],
            "hypotheses": [],
        },
    )
    c = make_client(model)
    d = wait(c, start(c))
    assert d["investigation"]["status"] == "completed"
    assert [t["status"] for t in d["toolExecutions"]] == ["failed", "failed"]
    assert d["report"]["confidence"] == "low"  # every call failed


def test_gathering_timeout_still_reports(make_client):
    model = ScriptedModel(
        GATHER[0],
        Sleep(30),
        REPORT
        | {
            "observations": [
                {"statement": "Instance status check is impaired.", "evidence": ["E1"]}
            ],
            "hypotheses": [],
        },
    )
    c = make_client(model, investigation_timeout_seconds=5)
    d = wait(c, start(c))
    assert d["investigation"]["status"] == "completed"
    assert "time for gathering evidence ran out" in " ".join(e["message"] for e in d["events"])
    assert [t["status"] for t in d["toolExecutions"]] == ["succeeded"]


def test_total_timeout(make_client):
    c = make_client(ScriptedModel("Done.", Sleep(30)), investigation_timeout_seconds=2)
    d = wait(c, start(c))
    assert d["investigation"]["status"] == "timed_out"
    assert d["events"][-1]["message"] == "Timed out after 2 s."


def test_removed_connection_fails(make_client, db_settings):
    c = make_client(None, investigation_autostart=False)
    inv_id = start(c)
    cid = c.get("/api/v1/connections").json()[0]["id"]
    c.delete(f"/api/v1/connections/{cid}")
    c2 = make_client(ScriptedModel())  # startup recovery picks up the queued investigation
    d = wait(c2, inv_id)
    assert d["investigation"]["status"] == "failed"
    assert "connection for this investigation was removed" in d["events"][-1]["message"]


def test_restart_recovery_marks_running_as_failed(make_client, db_settings):
    c = make_client(None, investigation_autostart=False)
    inv_id = start(c)
    with psycopg.connect(_sync_dsn(db_settings.database_url), autocommit=True) as conn:
        conn.execute("UPDATE investigations SET status = 'running'")
    c2 = make_client(ScriptedModel())
    d = wait(c2, inv_id)
    assert d["investigation"]["status"] == "failed"
    assert "server restart" in d["events"][-1]["message"]
