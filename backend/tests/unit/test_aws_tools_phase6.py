"""ECS, RDS and Lambda tools against moto, plus the mock-mode sample data."""

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError

import app.tools  # noqa: F401
from app.aws.context import AwsContext, BoundaryViolation
from app.aws.mock.clients import mock_client_factory
from app.core.config import AwsMode
from app.tools.base import ToolError
from app.tools.ecs import (
    DescribeServicesInput,
    ListServicesInput,
    StoppedTasksInput,
    describe_services,
    describe_stopped_tasks,
    list_services,
    service_health,
)
from app.tools.lambda_fn import (
    FunctionConfigInput,
    ListFunctionsInput,
    get_function_configuration,
    list_functions,
)
from app.tools.rds import (
    DbEventsInput,
    DescribeDbInstancesInput,
    db_health,
    describe_db_instances,
    describe_events,
)

REGION = "us-east-1"
ACCOUNT = "123456789012"


@pytest.fixture
def aws(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        yield


def ctx(factory=None) -> AwsContext:
    now = datetime.now(UTC)
    return AwsContext(
        account_id=ACCOUNT,
        region=REGION,
        allowed_regions=(REGION,),
        start=now - timedelta(hours=6),
        end=now + timedelta(minutes=5),
        client_factory=factory or (lambda svc: boto3.client(svc, region_name=REGION)),
        mode=AwsMode.LIVE,
    )


def mock_ctx(region=REGION) -> AwsContext:
    now = datetime.now(UTC)
    return AwsContext(
        account_id=ACCOUNT,
        region=region,
        allowed_regions=(region,),
        start=now - timedelta(hours=6),
        end=now,
        client_factory=mock_client_factory(ACCOUNT, region, now),
        mode=AwsMode.MOCK,
    )


# ---------- ECS ----------


def test_ecs_services(aws):
    ecs = boto3.client("ecs", region_name=REGION)
    ecs.create_cluster(clusterName="prod")
    ecs.register_task_definition(
        family="api", containerDefinitions=[{"name": "app", "image": "nginx", "memory": 256}]
    )
    ecs.create_service(cluster="prod", serviceName="api", taskDefinition="api", desiredCount=2)
    listed = list_services(ctx(), ListServicesInput())
    assert [(s["cluster"], s["service"]) for s in listed["services"]] == [("prod", "api")]
    out = describe_services(ctx(), DescribeServicesInput(cluster="prod", services=["api"]))
    svc = out["services"][0]
    assert svc["serviceName"] == "api" and svc["desiredCount"] == 2
    assert svc["taskDefinition"].startswith("api:")
    assert describe_stopped_tasks(ctx(), StoppedTasksInput(cluster="prod"))["count"] == 0


def test_ecs_arn_boundary():
    with pytest.raises(BoundaryViolation):
        describe_services(
            ctx(lambda s: None),
            DescribeServicesInput(
                cluster="prod", services=["arn:aws:ecs:us-east-1:999999999999:service/prod/api"]
            ),
        )


@pytest.mark.parametrize(
    ("svc", "expected"),
    [
        (
            {
                "status": "ACTIVE",
                "desiredCount": 2,
                "runningCount": 2,
                "deployments": [{"status": "PRIMARY", "rolloutState": "COMPLETED"}],
            },
            "healthy",
        ),
        (
            {
                "status": "ACTIVE",
                "desiredCount": 4,
                "runningCount": 2,
                "deployments": [{"status": "PRIMARY", "rolloutState": "IN_PROGRESS"}],
            },
            "degraded",
        ),
        (
            {"status": "ACTIVE", "desiredCount": 2, "runningCount": 0, "deployments": []},
            "unhealthy",
        ),
        (
            {
                "status": "ACTIVE",
                "desiredCount": 2,
                "runningCount": 2,
                "deployments": [{"status": "PRIMARY", "rolloutState": "FAILED"}],
            },
            "unhealthy",
        ),
    ],
)
def test_ecs_health(svc, expected):
    assert service_health(svc) == expected


def test_mock_ecs_tells_the_failed_deployment_story():
    c = mock_ctx()
    svc = describe_services(
        c, DescribeServicesInput(cluster="prod-core", services=["payments-api"])
    )["services"][0]
    assert svc["health"] == "degraded" and svc["deployments"][0]["failedTasks"] == 6
    tasks = describe_stopped_tasks(
        c, StoppedTasksInput(cluster="prod-core", service="payments-api")
    )
    assert {t["containers"][0]["exitCode"] for t in tasks["tasks"]} == {137}
    with pytest.raises(ToolError, match="Cluster not found"):
        describe_stopped_tasks(c, StoppedTasksInput(cluster="nope"))


# ---------- RDS ----------


def test_rds(aws):
    rds = boto3.client("rds", region_name=REGION)
    rds.create_db_instance(
        DBInstanceIdentifier="orders-db",
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
        MasterUsername="admin",
        MasterUserPassword="secret-password-1",
        AllocatedStorage=20,
    )
    out = describe_db_instances(ctx(), DescribeDbInstancesInput())
    db = out["dbInstances"][0]
    assert db["dbInstanceIdentifier"] == "orders-db" and db["engine"] == "postgres"
    assert db["health"] == "healthy"
    assert "secret-password-1" not in json.dumps(out)
    one = describe_db_instances(ctx(), DescribeDbInstancesInput(db_instance_identifier="orders-db"))
    assert one["count"] == 1
    with pytest.raises(ToolError, match="not found"):
        describe_db_instances(ctx(), DescribeDbInstancesInput(db_instance_identifier="missing"))
    assert describe_events(ctx(), DbEventsInput(db_instance_identifier="orders-db"))["count"] >= 0


@pytest.mark.parametrize(
    ("status", "health"),
    [
        ("available", "healthy"),
        ("modifying", "degraded"),
        ("storage-full", "unhealthy"),
        ("failed", "unhealthy"),
        ("stopped", "unknown"),
    ],
)
def test_db_health(status, health):
    assert db_health(status) == health


def test_db_identifier_validation():
    with pytest.raises(ValidationError):
        DescribeDbInstancesInput(db_instance_identifier="orders db; drop")


def test_mock_rds_events_within_window():
    out = describe_events(mock_ctx(), DbEventsInput(db_instance_identifier="reporting-replica"))
    assert any("Replica lag" in e["message"] for e in out["events"])


# ---------- Lambda ----------


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app.py", "def handler(e, c):\n    return 1\n")
    return buf.getvalue()


def test_lambda_never_returns_environment_values(aws):
    role = boto3.client("iam").create_role(RoleName="fn", AssumeRolePolicyDocument="{}")["Role"]
    boto3.client("lambda", region_name=REGION).create_function(
        FunctionName="order-processor",
        Runtime="python3.12",
        Role=role["Arn"],
        Handler="app.handler",
        Code={"ZipFile": _zip()},
        Timeout=30,
        MemorySize=512,
        Environment={"Variables": {"DB_PASSWORD": "hunter2-secret"}},
    )
    cfg = get_function_configuration(ctx(), FunctionConfigInput(function="order-processor"))
    assert cfg["memoryMB"] == 512 and cfg["timeoutSeconds"] == 30
    assert cfg["environmentVariableCount"] == 1
    listed = list_functions(ctx(), ListFunctionsInput(name_contains="order"))
    assert [f["functionName"] for f in listed["functions"]] == ["order-processor"]
    for out in (cfg, listed):
        assert "hunter2-secret" not in json.dumps(out) and "DB_PASSWORD" not in json.dumps(out)
    with pytest.raises(ToolError, match="not found"):
        get_function_configuration(ctx(), FunctionConfigInput(function="missing"))


def test_lambda_arn_boundary():
    with pytest.raises(BoundaryViolation, match="different AWS account"):
        get_function_configuration(
            ctx(lambda s: None),
            FunctionConfigInput(function="arn:aws:lambda:us-east-1:999999999999:function:x"),
        )


def test_mock_lambda_by_region():
    assert list_functions(mock_ctx("us-west-2"), ListFunctionsInput())["count"] == 1
    cfg = get_function_configuration(mock_ctx(), FunctionConfigInput(function="invoice-renderer"))
    assert "never-returned" not in json.dumps(cfg)
