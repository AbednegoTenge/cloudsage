import pytest
from pydantic import ValidationError
from strands.models import BedrockModel

from app.agent.model import ModelNotConfigured, build_model, model_id_of
from app.core.config import Environment, Settings


def settings(**kw) -> Settings:
    return Settings(_env_file=None, environment=Environment.TEST, **kw)


def test_unconfigured_bedrock_is_a_clear_error():
    with pytest.raises(ModelNotConfigured, match="CLOUDSAGE_BEDROCK_MODEL_ID"):
        build_model(settings())


def test_model_built_only_from_settings(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    m = build_model(
        settings(
            bedrock_model_id="example.model-v1",
            bedrock_region="eu-west-1",
            bedrock_max_tokens=2048,
            bedrock_guardrail_id="gr-1",
            bedrock_guardrail_version="3",
        )
    )
    assert isinstance(m, BedrockModel)
    cfg = m.get_config()
    assert cfg["model_id"] == "example.model-v1"
    assert cfg["max_tokens"] == 2048
    assert cfg["guardrail_id"] == "gr-1" and cfg["guardrail_version"] == "3"
    assert m.client.meta.region_name == "eu-west-1"
    assert model_id_of(m) == "example.model-v1"


def test_guardrail_id_and_version_go_together():
    with pytest.raises(ValidationError, match="go together"):
        settings(bedrock_guardrail_id="gr-1")
