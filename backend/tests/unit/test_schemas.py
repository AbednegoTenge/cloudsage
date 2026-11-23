import pytest
from pydantic import ValidationError

from app.schemas.api import ConnectionCreate, InvestigationCreate, UserSettings
from tests.conftest import connection_body


def test_valid_connection_normalises_regions():
    c = ConnectionCreate.model_validate(
        connection_body(allowedRegions=["us-west-2", "us-east-1", "us-west-2"])
    )
    assert c.allowed_regions == ["us-east-1", "us-west-2"]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"accountId": "12345"}, "12 digits"),
        ({"roleArn": "arn:aws:iam::999999999999:role/X"}, "belong to account_id"),
        ({"roleArn": "arn:aws:iam::123456789012:user/alice"}, "IAM role ARN"),
        ({"defaultRegion": "eu-west-1"}, "one of allowed_regions"),
        ({"allowedRegions": ["us-east-1", "mars-1"]}, "not a valid AWS region"),
        ({"allowedRegions": []}, "at least 1"),
        ({"externalId": "has spaces in it"}, "invalid characters"),
        ({"name": "AKIAIOSFODNN7EXAMPLE"}, "access keys are never accepted"),
        ({"externalId": "AKIAIOSFODNN7EXAMPLE"}, "access keys are never accepted"),
    ],
)
def test_invalid_connections_are_rejected(override, message):
    with pytest.raises(ValidationError, match=message):
        ConnectionCreate.model_validate(connection_body(**override))


def test_blank_external_id_becomes_none():
    assert ConnectionCreate.model_validate(connection_body(externalId="")).external_id is None


def test_investigation_prompt_rejects_access_keys_and_bounds_range():
    base = {"prompt": "why is checkout slow", "connectionId": "x", "region": "us-east-1"}
    assert InvestigationCreate.model_validate(base | {"timeRangeHours": 6}).prompt
    with pytest.raises(ValidationError, match="access keys"):
        InvestigationCreate.model_validate(
            base | {"prompt": "my key is AKIAIOSFODNN7EXAMPLE", "timeRangeHours": 6}
        )
    with pytest.raises(ValidationError):
        InvestigationCreate.model_validate(base | {"timeRangeHours": 0})
    with pytest.raises(ValidationError):
        InvestigationCreate.model_validate(base | {"timeRangeHours": 24 * 32})
    with pytest.raises(ValidationError, match="valid AWS region"):
        InvestigationCreate.model_validate(base | {"region": "nowhere", "timeRangeHours": 6})


def test_user_settings_limits():
    with pytest.raises(ValidationError):
        UserSettings(display_name="A", max_tool_calls=500)
    with pytest.raises(ValidationError):
        UserSettings(display_name="A", investigation_timeout_sec=5)
