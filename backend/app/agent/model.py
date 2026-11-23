"""Amazon Bedrock model provider.

The model ID, region and optional guardrail come only from settings. AWS credentials come from
the standard boto3 chain (an IAM role in deployed environments, a developer's SSO profile
locally); CloudSage never reads or stores access keys for Bedrock.
"""

from __future__ import annotations

from botocore.config import Config
from strands.models import BedrockModel
from strands.models.model import Model

from app.core.config import Settings


class ModelNotConfigured(RuntimeError):
    """Raised when Bedrock settings are missing; callers surface this as a clear error."""


def build_model(settings: Settings) -> Model:
    if not settings.bedrock_configured:
        raise ModelNotConfigured(
            "Amazon Bedrock is not configured: set CLOUDSAGE_BEDROCK_MODEL_ID and "
            "CLOUDSAGE_BEDROCK_REGION"
        )
    config: dict = {
        "model_id": settings.bedrock_model_id,
        "max_tokens": settings.bedrock_max_tokens,
        "temperature": settings.bedrock_temperature,
    }
    if settings.bedrock_guardrail_id:
        config |= {
            "guardrail_id": settings.bedrock_guardrail_id,
            "guardrail_version": settings.bedrock_guardrail_version,
            "guardrail_redact_output": True,
        }
    return BedrockModel(
        region_name=settings.bedrock_region,
        boto_client_config=Config(
            connect_timeout=10,
            read_timeout=settings.bedrock_timeout_seconds,
            retries={"max_attempts": 3, "mode": "adaptive"},
            user_agent_extra="cloudsage",
        ),
        **config,
    )


def model_id_of(model: Model) -> str:
    """Best-effort model identifier for the report record (never used to pick a model)."""
    try:
        cfg = model.get_config()
        return str(cfg.get("model_id") or type(model).__name__)
    except Exception:  # noqa: BLE001 - informational only
        return type(model).__name__
