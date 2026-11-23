import json

from fastapi.testclient import TestClient

from tests.conftest import BOB, connection_body

BASE = "/api/v1/investigations"


def _create(api: TestClient, connection: dict, **overrides):
    body = {
        "prompt": "Why is i-0a1b2c3d4e5f67890 failing health checks?",
        "connectionId": connection["id"],
        "region": "us-east-1",
        "timeRangeHours": 6,
    } | overrides
    return api.post(BASE, json=body)


def test_create_explicit_investigation(api: TestClient, connection: dict):
    r = _create(api, connection)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["id"] == "inv-1001"
    assert inv["status"] == "queued"
    assert inv["identificationMode"] == "explicit"
    assert inv["services"] == ["ec2"]
    assert inv["resources"][0]["identifier"] == "i-0a1b2c3d4e5f67890"
    assert inv["accountId"] == "123456789012"
    assert inv["toolCallCount"] == 0


def test_discovery_mode_when_no_identifiers(api: TestClient, connection: dict):
    inv = _create(api, connection, prompt="Why is checkout slow today?").json()
    assert inv["identificationMode"] == "discovered"
    assert inv["resources"] == []


def test_region_boundary_enforced(api: TestClient, connection: dict):
    r = _create(api, connection, region="eu-west-1")
    assert r.status_code == 403
    assert "not allowed" in r.json()["detail"]


def test_account_and_region_boundary_for_arns(api: TestClient, connection: dict):
    other_account = "arn:aws:lambda:us-east-1:999999999999:function:payments"
    assert _create(api, connection, prompt=f"Check {other_account}").status_code == 403
    other_region = "arn:aws:lambda:us-west-2:123456789012:function:payments"
    r = _create(api, connection, prompt=f"Check {other_region}")
    assert r.status_code == 403
    assert "us-west-2" in r.json()["detail"]


def test_time_range_limit(api: TestClient, connection: dict):
    assert _create(api, connection, timeRangeHours=24 * 30).status_code == 422


def test_errored_connection_blocks_investigations(api: TestClient, db_settings, connection):
    import psycopg

    from tests.conftest import _sync_dsn

    with psycopg.connect(_sync_dsn(db_settings.database_url), autocommit=True) as c:
        c.execute("UPDATE aws_connections SET status = 'error'")
    assert _create(api, connection).status_code == 422


def test_detail_keeps_report_separate_from_evidence(api: TestClient, connection: dict):
    inv_id = _create(api, connection).json()["id"]
    detail = api.get(f"{BASE}/{inv_id}").json()
    assert set(detail) == {"investigation", "events", "toolExecutions", "report"}
    assert detail["report"] is None
    assert detail["toolExecutions"] == []
    assert [e["type"] for e in detail["events"]] == ["queued"]
    assert detail["events"][0]["investigationId"] == inv_id


def test_list_search_filter_and_paginate(api: TestClient, connection: dict):
    for p in ("checkout latency spike", "orders-db CPU high", "lambda invoice-renderer errors"):
        assert _create(api, connection, prompt=p).status_code == 201
    page = api.get(BASE, params={"limit": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["limit"] == 2
    assert page["items"][0]["id"] == "inv-1003"  # newest first
    assert api.get(BASE, params={"limit": 2, "offset": 2}).json()["items"][0]["id"] == "inv-1001"

    found = api.get(BASE, params={"search": "orders-db"}).json()
    assert [i["title"] for i in found["items"]] == ["orders-db CPU high"]
    assert api.get(BASE, params={"search": "100%_"}).json()["total"] == 0
    assert api.get(BASE, params={"status": "queued"}).json()["total"] == 3
    assert api.get(BASE, params={"status": "completed"}).json()["total"] == 0
    assert api.get(BASE, params={"connectionId": connection["id"]}).json()["total"] == 3


def test_events_after(api: TestClient, connection: dict):
    inv_id = _create(api, connection).json()["id"]
    assert len(api.get(f"{BASE}/{inv_id}/events").json()) == 1
    assert api.get(f"{BASE}/{inv_id}/events", params={"after": 1}).json() == []


def test_sse_stream_replays_then_ends_when_finished(api: TestClient, db_settings, connection):
    import psycopg

    from tests.conftest import _sync_dsn

    inv_id = _create(api, connection).json()["id"]
    with psycopg.connect(_sync_dsn(db_settings.database_url), autocommit=True) as c:
        c.execute("UPDATE investigations SET status = 'completed', completed_at = now()")
    with api.stream("GET", f"{BASE}/{inv_id}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    blocks = [b for b in body.split("\n\n") if b.strip()]
    assert blocks[0].startswith("id: 1\nevent: investigation\ndata: ")
    assert json.loads(blocks[0].split("data: ", 1)[1])["type"] == "queued"
    assert blocks[-1].startswith("event: end")

    # Resuming with Last-Event-ID skips what the client already has.
    with api.stream("GET", f"{BASE}/{inv_id}/stream", headers={"Last-Event-ID": "1"}) as r:
        resumed = "".join(r.iter_text())
    assert "event: investigation" not in resumed and "event: end" in resumed


def test_investigations_are_isolated_per_user(api: TestClient, connection: dict):
    inv_id = _create(api, connection).json()["id"]
    bob = {"X-CloudSage-User": BOB}
    assert api.get(BASE, headers=bob).json()["total"] == 0
    assert api.get(f"{BASE}/{inv_id}", headers=bob).status_code == 404
    assert api.get(f"{BASE}/{inv_id}/events", headers=bob).status_code == 404
    assert api.get(f"{BASE}/{inv_id}/stream", headers=bob).status_code == 404
    # Bob cannot start an investigation on Alice's connection either.
    r = api.post(
        BASE,
        headers=bob,
        json={
            "prompt": "Why is checkout slow?",
            "connectionId": connection["id"],
            "region": "us-east-1",
            "timeRangeHours": 6,
        },
    )
    assert r.status_code == 404
    bob_conn = api.post("/api/v1/connections", json=connection_body(), headers=bob).json()
    assert api.get(BASE, headers=bob, params={"connectionId": bob_conn["id"]}).json()["total"] == 0


def test_bad_public_ids(api: TestClient):
    assert api.get(f"{BASE}/inv-abc").status_code == 404
    assert api.get(f"{BASE}/1001").status_code == 404
