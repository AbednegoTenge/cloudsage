"""EC2 and CloudWatch tools against moto (no real AWS)."""

import time
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws
from pydantic import ValidationError

import app.tools  # noqa: F401 - registers tools
from app.aws.context import AwsContext, BoundaryViolation
from app.core.config import AwsMode
from app.tools.base import READ_ONLY_PREFIXES, REGISTRY, ToolError, ToolInput, register
from app.tools.cloudwatch import (
    AlarmsInput,
    LogEventsInput,
    LogGroupsInput,
    MetricInput,
    describe_alarms,
    describe_log_groups,
    filter_log_events,
    get_metric_data,
)
from app.tools.ec2 import (
    DescribeInstancesInput,
    InstanceStatusInput,
    describe_instance_status,
    describe_instances,
)

REGION = "us-east-1"


@pytest.fixture
def aws(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        yield


def ctx(hours: int = 6) -> AwsContext:
    now = datetime.now(UTC)
    return AwsContext(
        account_id="123456789012",
        region=REGION,
        allowed_regions=(REGION,),
        start=now - timedelta(hours=hours),
        end=now + timedelta(minutes=5),
        client_factory=lambda svc: boto3.client(svc, region_name=REGION),
        mode=AwsMode.LIVE,
    )


def _instances(names: list[str]) -> list[str]:
    ec2 = boto3.client("ec2", region_name=REGION)
    ids = []
    for n in names:
        r = ec2.run_instances(
            ImageId="ami-12345678",
            MinCount=1,
            MaxCount=1,
            InstanceType="t3.micro",
            TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": n}]}],
        )
        ids.append(r["Instances"][0]["InstanceId"])
    return ids


def test_describe_instances(aws):
    ids = _instances(["api-worker-1", "api-worker-2", "bastion"])
    out = describe_instances(ctx(), DescribeInstancesInput())
    assert out["count"] == 3 and {i["name"] for i in out["instances"]} >= {"bastion"}
    one = describe_instances(ctx(), DescribeInstancesInput(instance_ids=[ids[0]]))
    assert [i["instanceId"] for i in one["instances"]] == [ids[0]]
    assert one["instances"][0]["state"] == "running"
    named = describe_instances(ctx(), DescribeInstancesInput(name_contains="api-worker"))
    assert named["count"] == 2


def test_instance_status(aws):
    ids = _instances(["a"])
    out = describe_instance_status(ctx(), InstanceStatusInput(instance_ids=ids))
    assert out["statuses"][0]["instanceId"] == ids[0]
    assert out["statuses"][0]["health"] in {"healthy", "degraded", "unknown"}


@pytest.mark.parametrize("bad", ["i-123", "sg-12345678", "i-0123; rm -rf /", "I-0123456789ABCDEF0"])
def test_instance_ids_are_validated(bad):
    with pytest.raises(ValidationError):
        DescribeInstancesInput(instance_ids=[bad])


def test_unknown_fields_and_namespaces_rejected():
    with pytest.raises(ValidationError):
        DescribeInstancesInput(instance_ids=[], dry_run=False)
    with pytest.raises(ValidationError):
        MetricInput(namespace="AWS/Billing", metric_name="EstimatedCharges")
    with pytest.raises(ValidationError):
        MetricInput(namespace="AWS/EC2", metric_name="CPU\nUtilization")
    with pytest.raises(ValidationError):
        LogEventsInput(log_group="/a", max_events=10_000)


def test_metric_series(aws):
    cw = boto3.client("cloudwatch", region_name=REGION)
    now = datetime.now(UTC)
    for m, v in [(30, 20.0), (20, 60.0), (10, 99.0)]:
        cw.put_metric_data(
            Namespace="AWS/EC2",
            MetricData=[
                {
                    "MetricName": "CPUUtilization",
                    "Value": v,
                    "Timestamp": now - timedelta(minutes=m),
                    "Dimensions": [{"Name": "InstanceId", "Value": "i-0123456789abcdef0"}],
                }
            ],
        )
    out = get_metric_data(
        ctx(),
        MetricInput(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            period_seconds=300,
            stat="Maximum",
            dimensions=[{"name": "InstanceId", "value": "i-0123456789abcdef0"}],
        ),
    )
    assert out["kind"] == "metric_series" and out["unit"] == "Percent"
    assert out["summary"]["max"] == 99.0 and out["summary"]["count"] == 3
    assert [p["v"] for p in out["points"]] == [20.0, 60.0, 99.0]


def test_metric_window_is_clamped_to_investigation(aws):
    c = ctx(hours=1)
    out = get_metric_data(
        c,
        MetricInput(
            namespace="AWS/EC2", metric_name="CPUUtilization", start=c.start - timedelta(days=30)
        ),
    )
    assert out["start"] == c.start.isoformat()
    with pytest.raises(BoundaryViolation):
        get_metric_data(
            c,
            MetricInput(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                start=c.start - timedelta(days=30),
                end=c.start - timedelta(days=29),
            ),
        )


def test_metric_period_keeps_points_bounded(aws):
    out = get_metric_data(
        ctx(hours=24 * 30),
        MetricInput(namespace="AWS/EC2", metric_name="CPUUtilization", period_seconds=60),
    )
    assert out["periodSeconds"] >= 60 * 24 * 30 * 60 / 500


def test_alarms(aws):
    cw = boto3.client("cloudwatch", region_name=REGION)
    for name in ("disk-high", "cpu-high"):
        cw.put_metric_alarm(
            AlarmName=name,
            MetricName="CPUUtilization",
            Namespace="AWS/EC2",
            Statistic="Average",
            Period=60,
            EvaluationPeriods=1,
            Threshold=80,
            ComparisonOperator="GreaterThanThreshold",
        )
    cw.set_alarm_state(AlarmName="disk-high", StateValue="ALARM", StateReason="disk at 100%")
    out = describe_alarms(ctx(), AlarmsInput(state="ALARM"))
    assert [a["name"] for a in out["alarms"]] == ["disk-high"]
    assert out["alarms"][0]["reason"] == "disk at 100%"
    assert describe_alarms(ctx(), AlarmsInput(name_prefix="cpu"))["count"] == 1


def test_logs(aws):
    logs = boto3.client("logs", region_name=REGION)
    logs.create_log_group(logGroupName="/platform/api")
    logs.create_log_stream(logGroupName="/platform/api", logStreamName="w3")
    now_ms = int(time.time() * 1000)
    logs.put_log_events(
        logGroupName="/platform/api",
        logStreamName="w3",
        logEvents=[
            {"timestamp": now_ms - 2000, "message": "INFO ok"},
            {"timestamp": now_ms - 1000, "message": "ERROR No space left on device"},
        ],
    )
    out = filter_log_events(
        ctx(), LogEventsInput(log_group="/platform/api", filter_pattern="ERROR")
    )
    assert out["kind"] == "log_events"
    assert [e["message"] for e in out["events"]] == ["ERROR No space left on device"]
    groups = describe_log_groups(ctx(), LogGroupsInput(prefix="/platform"))
    assert [g["name"] for g in groups["logGroups"]] == ["/platform/api"]
    with pytest.raises(ToolError, match="not found"):
        filter_log_events(ctx(), LogEventsInput(log_group="/missing"))


def test_every_registered_operation_is_read_only():
    assert len(REGISTRY) == 6
    for spec in REGISTRY.values():
        assert spec.operations and all(op.startswith(READ_ONLY_PREFIXES) for op in spec.operations)
        assert spec.description and spec.service in {"ec2", "cloudwatch"}


def test_write_operations_cannot_be_registered():
    with pytest.raises(ValueError, match="non read-only"):
        register(
            name="ec2_stop_instances",
            service="ec2",
            description="x",
            input_model=ToolInput,
            operations=("StopInstances",),
        )


def test_arn_boundaries():
    c = ctx()
    c.check_arn("arn:aws:lambda:us-east-1:123456789012:function:f")
    with pytest.raises(BoundaryViolation, match="different AWS account"):
        c.check_arn("arn:aws:lambda:us-east-1:999999999999:function:f")
    with pytest.raises(BoundaryViolation, match="scoped to us-east-1"):
        c.check_arn("arn:aws:lambda:eu-west-1:123456789012:function:f")
