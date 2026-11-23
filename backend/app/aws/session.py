"""AWS access via STS AssumeRole. Only temporary credentials are ever used or held.

Credentials live in memory for the duration of one validation, discovery or investigation and
are never written to the database, logs or reports.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import AwsMode, Settings
from app.core.logging import redact

BOTO_CONFIG = Config(
    connect_timeout=5,
    read_timeout=15,
    retries={"max_attempts": 3, "mode": "standard"},
    user_agent_extra="cloudsage",
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str | None = None


class AssumeRoleError(RuntimeError):
    """STS refused or could not be reached. The message is redacted and safe to show."""


def client_error_message(e: Exception) -> str:
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        return redact(f"{err.get('Code', 'Error')}: {err.get('Message', 'request failed')}")[:500]
    if isinstance(e, BotoCoreError):
        return f"Could not reach AWS: {e.__class__.__name__}"
    return redact(str(e))[:500]


def assume_role_session(
    *,
    role_arn: str,
    external_id: str | None,
    region: str,
    duration: int,
    session_name: str = "cloudsage",
) -> boto3.Session:
    """Assume the connection's role and return a boto3 session holding only temporary creds."""
    sts = boto3.client("sts", region_name=region, config=BOTO_CONFIG)
    params: dict[str, Any] = {
        "RoleArn": role_arn,
        "RoleSessionName": session_name[:64],
        "DurationSeconds": duration,
    }
    if external_id:
        params["ExternalId"] = external_id
    try:
        creds = sts.assume_role(**params)["Credentials"]
    except (ClientError, BotoCoreError) as e:
        raise AssumeRoleError(client_error_message(e)) from None
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


def _assume_and_verify(
    role_arn: str, external_id: str | None, account_id: str, region: str, duration: int
) -> ValidationResult:
    try:
        session = assume_role_session(
            role_arn=role_arn,
            external_id=external_id,
            region=region,
            duration=duration,
            session_name="cloudsage-validate",
        )
        identity = session.client("sts", config=BOTO_CONFIG).get_caller_identity()
    except AssumeRoleError as e:
        return ValidationResult(False, str(e))
    except (ClientError, BotoCoreError) as e:
        return ValidationResult(False, client_error_message(e))
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
