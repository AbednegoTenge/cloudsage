"""Live-mode EC2 discovery through the API, with AWS replaced by moto."""

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.core.config import AwsMode
from app.main import create_app
from tests.conftest import ALICE, connection_body


@pytest.fixture
def live_api(db_settings, monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    live = db_settings.model_copy(update={"aws_mode": AwsMode.LIVE})
    with mock_aws(), TestClient(create_app(live), headers={"X-CloudSage-User": ALICE}) as c:
        yield c


def _launch(region: str, name: str) -> str:
    r = boto3.client("ec2", region_name=region).run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}],
    )
    return r["Instances"][0]["InstanceId"]


def test_discovers_ec2_in_allowed_regions_only(live_api):
    boto3.client("iam").create_role(RoleName="CloudSageReadOnly", AssumeRolePolicyDocument="{}")
    east = _launch("us-east-1", "api-1")
    west = _launch("us-west-2", "bastion")
    _launch("eu-west-1", "not-allowed")
    assert live_api.post("/api/v1/connections", json=connection_body()).status_code == 201

    r = live_api.get("/api/v1/resources")
    assert r.status_code == 200, r.text
    found = {(x["identifier"], x["region"], x["name"]) for x in r.json()}
    assert found == {(east, "us-east-1", "api-1"), (west, "us-west-2", "bastion")}

    dash = live_api.get("/api/v1/dashboard").json()
    assert dash["resourcesMonitored"]["ec2"] == 2


def test_unreachable_account_is_a_clear_error(live_api, monkeypatch):
    assert (
        live_api.post(
            "/api/v1/connections",
            json=connection_body(roleArn="arn:aws:iam::123456789012:role/Missing"),
        ).status_code
        == 201
    )
    # moto allows assuming any role, so simulate an STS refusal.
    from app.aws import discovery
    from app.aws.session import AssumeRoleError

    async def refuse(*a, **k):
        raise AssumeRoleError("AccessDenied: not authorized to perform sts:AssumeRole")

    monkeypatch.setattr(discovery, "open_context", refuse)
    r = live_api.get("/api/v1/resources")
    assert r.status_code == 502
    assert "Could not access connection 'prod-us-east-1'" in r.json()["detail"]
    # The dashboard degrades gracefully instead of failing.
    assert live_api.get("/api/v1/dashboard").status_code == 200


def test_discovers_ecs_rds_and_lambda(live_api):
    import io
    import zipfile

    boto3.client("iam").create_role(RoleName="CloudSageReadOnly", AssumeRolePolicyDocument="{}")
    ecs = boto3.client("ecs", region_name="us-east-1")
    ecs.create_cluster(clusterName="prod")
    ecs.register_task_definition(
        family="api", containerDefinitions=[{"name": "app", "image": "nginx", "memory": 256}]
    )
    ecs.create_service(cluster="prod", serviceName="api", taskDefinition="api", desiredCount=1)
    boto3.client("rds", region_name="us-west-2").create_db_instance(
        DBInstanceIdentifier="orders-db",
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
        MasterUsername="admin",
        MasterUserPassword="pw-123456789",
        AllocatedStorage=20,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app.py", "def handler(e, c):\n    return 1\n")
    role = boto3.client("iam").create_role(RoleName="fn", AssumeRolePolicyDocument="{}")
    boto3.client("lambda", region_name="us-east-1").create_function(
        FunctionName="invoice-renderer",
        Runtime="python3.12",
        Role=role["Role"]["Arn"],
        Handler="app.handler",
        Code={"ZipFile": buf.getvalue()},
    )
    assert live_api.post("/api/v1/connections", json=connection_body()).status_code == 201

    found = {
        (r["service"], r["name"], r["region"]) for r in live_api.get("/api/v1/resources").json()
    }
    assert found == {
        ("ecs", "api", "us-east-1"),
        ("rds", "orders-db", "us-west-2"),
        ("lambda", "invoice-renderer", "us-east-1"),
    }
    only_rds = live_api.get("/api/v1/resources", params={"service": "rds"}).json()
    assert [r["name"] for r in only_rds] == ["orders-db"]
