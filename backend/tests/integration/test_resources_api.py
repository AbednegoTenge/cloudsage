from fastapi.testclient import TestClient

from app.core.config import AwsMode
from app.main import create_app
from tests.conftest import ALICE, BOB, connection_body


def test_resources_scoped_to_allowed_regions_and_account(api: TestClient, connection: dict):
    resources = api.get("/api/v1/resources").json()
    assert resources
    assert {r["region"] for r in resources} <= {"us-east-1", "us-west-2"}
    assert all("999999999999" not in r["identifier"] for r in resources)
    assert resources[0]["health"] == "unhealthy"  # worst first

    narrow = api.post(
        "/api/v1/connections",
        json=connection_body(name="west", allowedRegions=["us-west-2"], defaultRegion="us-west-2"),
    ).json()
    west = api.get("/api/v1/resources", params={"connectionId": narrow["id"]}).json()
    assert west and {r["region"] for r in west} == {"us-west-2"}
    ec2 = api.get("/api/v1/resources", params={"service": "ec2"}).json()
    assert ec2 and {r["service"] for r in ec2} == {"ec2"}


def test_resources_empty_without_connections_and_isolated(api: TestClient, connection: dict):
    assert api.get("/api/v1/resources", headers={"X-CloudSage-User": BOB}).json() == []
    r = api.get(
        "/api/v1/resources",
        params={"connectionId": connection["id"]},
        headers={"X-CloudSage-User": BOB},
    )
    assert r.status_code == 404


def test_live_discovery_for_other_services_not_available_yet(db_settings):
    live = db_settings.model_copy(update={"aws_mode": AwsMode.LIVE})
    with TestClient(create_app(live), headers={"X-CloudSage-User": ALICE}) as c:
        assert c.get("/api/v1/resources", params={"service": "rds"}).status_code == 501


def test_dashboard_counts(api: TestClient, connection: dict):
    api.post(
        "/api/v1/investigations",
        json={
            "prompt": "Why is checkout slow?",
            "connectionId": connection["id"],
            "region": "us-east-1",
            "timeRangeHours": 6,
        },
    )
    d = api.get("/api/v1/dashboard").json()
    assert d["investigationsLast7d"] == 1
    assert sum(day["count"] for day in d["dailyInvestigations"]) == 1
    assert len(d["dailyInvestigations"]) == 7
    assert d["resourcesMonitored"]["ec2"] > 0
    assert {s["service"] for s in d["healthByService"]} == {"ec2", "ecs", "rds", "lambda"}
    # Without sampled history the timeline is a flat snapshot, never invented variation.
    assert len({(p["healthy"], p["unhealthy"]) for p in d["healthTimeline"]}) == 1


def test_settings_roundtrip_and_validation(api: TestClient, connection: dict):
    s = api.get("/api/v1/settings").json()
    assert s["email"] == ALICE and s["maxToolCalls"] == 25
    s |= {"displayName": "Alice", "maxToolCalls": 10, "defaultConnectionId": connection["id"]}
    s["email"] = "attacker@example.com"  # read-only: ignored
    r = api.put("/api/v1/settings", json=s)
    assert r.status_code == 200, r.text
    assert r.json()["maxToolCalls"] == 10 and r.json()["email"] == ALICE
    assert api.get("/api/v1/settings").json()["displayName"] == "Alice"

    assert api.put("/api/v1/settings", json=s | {"maxToolCalls": 999}).status_code == 422
    foreign = s | {"defaultConnectionId": "00000000-0000-0000-0000-000000000000"}
    assert api.put("/api/v1/settings", json=foreign).status_code == 404
    # Bob's settings are untouched.
    assert (
        api.get("/api/v1/settings", headers={"X-CloudSage-User": BOB}).json()["maxToolCalls"] == 25
    )


def test_invalid_identity_header_rejected(api: TestClient):
    r = api.get("/api/v1/connections", headers={"X-CloudSage-User": "not an email"})
    assert r.status_code == 401


def test_oidc_mode_refuses_until_implemented(db_settings):
    oidc = db_settings.model_copy(update={"auth_mode": "oidc"})
    with TestClient(create_app(oidc)) as c:
        assert c.get("/api/v1/connections").status_code == 501
