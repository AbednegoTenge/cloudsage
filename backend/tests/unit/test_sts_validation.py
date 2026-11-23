"""Live-mode connection validation against a moto-mocked STS (no real AWS calls)."""

import asyncio

import boto3
import pytest
from moto import mock_aws

from app.aws.session import validate_connection
from app.core.config import AwsMode, Environment, Settings

MOTO_ACCOUNT = "123456789012"  # moto's default account


@pytest.fixture
def live_settings(monkeypatch) -> Settings:
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None, environment=Environment.TEST, aws_mode=AwsMode.LIVE)


def _run(settings: Settings, account_id: str):
    return asyncio.run(
        validate_connection(
            settings,
            role_arn=f"arn:aws:iam::{MOTO_ACCOUNT}:role/CloudSageReadOnly",
            external_id="ext-123",
            account_id=account_id,
            region="us-east-1",
        )
    )


@mock_aws
def test_assume_role_succeeds_for_matching_account(live_settings):
    boto3.client("iam").create_role(RoleName="CloudSageReadOnly", AssumeRolePolicyDocument="{}")
    assert _run(live_settings, MOTO_ACCOUNT).ok


@mock_aws
def test_account_mismatch_is_reported(live_settings):
    result = _run(live_settings, "999999999999")
    assert not result.ok
    assert "different account" in (result.message or "")


def test_mock_mode_makes_no_aws_calls():
    settings = Settings(_env_file=None, environment=Environment.TEST)
    assert _run(settings, "000000000000").ok
