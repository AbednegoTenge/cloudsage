"""Application configuration.

Every setting comes from the environment (prefix ``CLOUDSAGE_``) or a local ``.env`` file.
Nothing environment-specific (AWS account IDs, regions, Bedrock model IDs, credentials) is
hardcoded here; defaults are only safe local-development values.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AwsMode(StrEnum):
    MOCK = "mock"  # local development: canned AWS data, no network calls
    LIVE = "live"  # real AWS via STS AssumeRole (temporary credentials only)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLOUDSAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CloudSage"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    # HTTP
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # Database
    database_url: str = "postgresql+psycopg://cloudsage:cloudsage@localhost:5432/cloudsage"
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)

    # Authentication. "dev" trusts an X-CloudSage-User header (local development and tests
    # only); OIDC bearer-token validation arrives with security hardening (Phase 7).
    auth_mode: str = Field(default="dev", pattern="^(dev|oidc)$")
    dev_default_user_email: str = "engineer@example.com"

    # AWS (Phase 4). No credentials here: live mode assumes a role ARN stored per connection.
    aws_mode: AwsMode = AwsMode.MOCK
    aws_sts_session_duration_seconds: int = Field(default=900, ge=900, le=3600)

    # Amazon Bedrock (Phase 3). Model ID and region must be supplied by the environment.
    bedrock_model_id: str | None = None
    bedrock_region: str | None = None

    # Investigation limits
    investigation_timeout_seconds: int = Field(default=300, ge=10, le=3600)
    investigation_max_tool_calls: int = Field(default=25, ge=1, le=200)
    investigation_max_time_range_hours: int = Field(default=168, ge=1, le=24 * 31)
    sse_poll_interval_seconds: float = Field(default=1.0, gt=0, le=10)

    @model_validator(mode="after")
    def _forbid_dev_auth_in_production(self) -> "Settings":
        if self.environment is Environment.PRODUCTION and self.auth_mode == "dev":
            raise ValueError("CLOUDSAGE_AUTH_MODE=dev is not allowed in production")
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
