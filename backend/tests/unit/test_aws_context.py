import asyncio
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws

from app.aws.context import BoundaryViolation, open_context
from app.core.config import AwsMode, Environment, Settings
from app.tools.ec2 import DescribeInstancesInput, describe_instances

NOW = datetime.now(UTC)


def _open(settings, region="us-east-1"):
    return asyncio.run(
        open_context(
            settings,
            role_arn="arn:aws:iam::123456789012:role/CloudSageReadOnly",
            external_id="x-1",
            account_id="123456789012",
            region=region,
            allowed_regions=["us-east-1"],
            start=NOW - timedelta(hours=1),
            end=NOW,
        )
    )


def test_region_must_be_allowed():
    with pytest.raises(BoundaryViolation):
        _open(Settings(_env_file=None, environment=Environment.TEST), region="eu-west-1")


def test_mock_context_serves_sample_data_without_aws():
    ctx = _open(Settings(_env_file=None, environment=Environment.TEST))
    out = describe_instances(ctx, DescribeInstancesInput(name_contains="api-worker-3"))
    assert out["instances"][0]["instanceId"] == "i-0a1b2c3d4e5f67890"


@mock_aws
def test_live_context_uses_assumed_role_credentials(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "testing")
    boto3.client("iam").create_role(RoleName="CloudSageReadOnly", AssumeRolePolicyDocument="{}")
    settings = Settings(_env_file=None, environment=Environment.TEST, aws_mode=AwsMode.LIVE)
    ctx = _open(settings)
    ec2 = ctx.client("ec2")
    assert ec2.meta.region_name == "us-east-1"
    creds = ec2._request_signer._credentials
    assert creds.access_key.startswith("ASIA")  # temporary STS credentials, not the caller's
    assert creds.token
    assert describe_instances(ctx, DescribeInstancesInput())["count"] == 0
