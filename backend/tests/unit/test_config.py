import pytest
from pydantic import ValidationError

from app.core.config import AwsMode, Settings


def test_defaults_are_safe_for_local_dev():
    s = Settings(_env_file=None)
    assert s.aws_mode is AwsMode.MOCK
    assert s.bedrock_model_id is None  # never hardcoded
    assert s.bedrock_region is None


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("CLOUDSAGE_AWS_MODE", "live")
    monkeypatch.setenv("CLOUDSAGE_CORS_ORIGINS", "https://a.example, https://b.example")
    s = Settings(_env_file=None)
    assert s.aws_mode is AwsMode.LIVE
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_limits_are_bounded():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, investigation_max_tool_calls=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, aws_sts_session_duration_seconds=86400)
