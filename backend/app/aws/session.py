"""AWS access via STS AssumeRole. Only temporary credentials are ever used or held.

Phase 2 uses this to validate connections; Phase 4 builds tool sessions on top of it.
"""

import asyncio
from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import AwsMode, Settings
from app.core.logging import redact

_BOTO_CONFIG = Config(
    connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"}
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str | None = None


def _assume_and_verify(
    role_arn: str, external_id: str | None, account_id: str, region: str, duration: int
) -> ValidationResult:
    sts = boto3.client("sts", region_name=region, config=_BOTO_CONFIG)
    params: dict = {
        "RoleArn": role_arn,
        "RoleSessionName": "cloudsage-validate",
        "DurationSeconds": duration,
    }
    if external_id:
        params["ExternalId"] = external_id
    try:
        creds = sts.assume_role(**params)["Credentials"]
        scoped = boto3.client(
            "sts",
            region_name=region,
            config=_BOTO_CONFIG,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        identity = scoped.get_caller_identity()
    except ClientError as e:
        err = e.response.get("Error", {})
        return ValidationResult(
            False, redact(f"{err.get('Code', 'Error')}: {err.get('Message', 'AssumeRole failed')}")
        )
    except BotoCoreError as e:
        return ValidationResult(False, redact(f"Could not reach AWS STS: {e.__class__.__name__}"))
    if identity.get("Account") != account_id:
        return ValidationResult(
            False, "Assumed role belongs to a different account than configured"
        )
    return ValidationResult(True)


async def validate_connection(
    settings: Settings, *, role_arn: str, external_id: str | None, account_id: str, region: str
) -> ValidationResult:
    if settings.aws_mode is AwsMode.MOCK:
        # Local development: no AWS calls. Input was already validated by the API schema.
        return ValidationResult(True)
    return await asyncio.to_thread(
        _assume_and_verify,
        role_arn,
        external_id,
        account_id,
        region,
        settings.aws_sts_session_duration_seconds,
    )
