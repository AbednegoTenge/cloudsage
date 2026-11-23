"""Request/response models for the v1 API.

JSON uses camelCase (matching the frontend's TypeScript types); Python uses snake_case.
Input models validate every identifier and bound every range, because these values later
flow into AWS API calls and agent prompts.
"""

import re
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

AwsService = Literal["ec2", "ecs", "rds", "lambda", "cloudwatch"]
ResourceHealth = Literal["healthy", "degraded", "unhealthy", "unknown"]

AWS_REGION_RE = re.compile(r"^[a-z]{2}(-gov)?-[a-z]+-\d$")
ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
ROLE_ARN_RE = re.compile(r"^arn:aws(-[a-z]+)?:iam::(\d{12}):role/[\w+=,.@\-/]{1,512}$")
EXTERNAL_ID_RE = re.compile(r"^[\w+=,.@:/-]{2,1224}$")
ACCESS_KEY_RE = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


def _region(value: str) -> str:
    if not AWS_REGION_RE.match(value):
        raise ValueError(f"'{value}' is not a valid AWS region code")
    return value


def _reject_access_keys(value: str | None) -> str | None:
    if value and ACCESS_KEY_RE.search(value):
        raise ValueError("AWS access keys are never accepted; use an IAM role ARN")
    return value


# ---------- Connections ----------


class ConnectionBase(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    account_id: str
    role_arn: str = Field(max_length=2048)
    external_id: str | None = Field(default=None, max_length=1224)
    default_region: str
    allowed_regions: list[str] = Field(min_length=1, max_length=30)

    @field_validator("name", "role_arn", "external_id")
    @classmethod
    def _no_keys(cls, v: str | None) -> str | None:
        return _reject_access_keys(v.strip() if isinstance(v, str) else v)

    @field_validator("account_id")
    @classmethod
    def _account(cls, v: str) -> str:
        if not ACCOUNT_ID_RE.match(v):
            raise ValueError("AWS account IDs are exactly 12 digits")
        return v

    @field_validator("external_id")
    @classmethod
    def _external(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not EXTERNAL_ID_RE.match(v):
            raise ValueError("external ID contains invalid characters")
        return v

    @field_validator("default_region")
    @classmethod
    def _default_region(cls, v: str) -> str:
        return _region(v)

    @field_validator("allowed_regions")
    @classmethod
    def _regions(cls, v: list[str]) -> list[str]:
        return sorted({_region(r) for r in v})

    @model_validator(mode="after")
    def _consistency(self) -> "ConnectionBase":
        m = ROLE_ARN_RE.match(self.role_arn)
        if not m:
            raise ValueError("role_arn must be an IAM role ARN")
        if m.group(2) != self.account_id:
            raise ValueError("role_arn must belong to account_id")
        if self.default_region not in self.allowed_regions:
            raise ValueError("default_region must be one of allowed_regions")
        return self


class ConnectionCreate(ConnectionBase):
    pass


class ConnectionUpdate(ConnectionBase):
    pass


class ConnectionOut(ApiModel):
    id: str
    name: str
    account_id: str
    role_arn: str
    external_id: str | None
    default_region: str
    allowed_regions: list[str]
    status: Literal["connected", "unvalidated", "error"]
    status_message: str | None = None
    last_validated_at: datetime | None


# ---------- Investigations ----------


class ResourceRef(ApiModel):
    service: AwsService
    resource_type: str = Field(max_length=64)
    identifier: str = Field(max_length=2048)
    name: str | None = Field(default=None, max_length=256)
    health: ResourceHealth | None = None


class TimeRange(ApiModel):
    start: datetime
    end: datetime


class InvestigationCreate(ApiModel):
    prompt: str = Field(min_length=3, max_length=2000)
    connection_id: str
    region: str
    time_range_hours: int = Field(ge=1, le=24 * 31)

    @field_validator("region")
    @classmethod
    def _r(cls, v: str) -> str:
        return _region(v)

    @field_validator("prompt")
    @classmethod
    def _p(cls, v: str) -> str:
        v = v.strip()
        _reject_access_keys(v)
        return v


class InvestigationOut(ApiModel):
    id: str
    title: str
    prompt: str
    connection_id: str
    account_id: str
    region: str
    status: Literal["queued", "running", "completed", "failed", "timed_out"]
    identification_mode: Literal["explicit", "discovered"]
    services: list[str]
    resources: list[ResourceRef]
    time_range: TimeRange
    created_at: datetime
    completed_at: datetime | None
    tool_call_count: int
    severity: str | None = None
    summary: str | None = None


class InvestigationEventOut(ApiModel):
    id: str
    investigation_id: str
    seq: int
    type: str
    message: str
    created_at: datetime
    tool_execution_id: str | None = None


class ToolExecutionOut(ApiModel):
    id: str
    investigation_id: str
    tool_name: str
    service: str
    input: dict[str, Any]
    output: Any
    status: Literal["running", "succeeded", "failed"]
    error: str | None = None
    duration_ms: int
    started_at: datetime


class InvestigationReportOut(ApiModel):
    investigation_id: str
    summary: str
    observations: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    log_excerpts: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    confidence: Literal["low", "medium", "high"]
    limitations: list[str]
    model_id: str
    generated_at: datetime


class InvestigationDetailOut(ApiModel):
    investigation: InvestigationOut
    events: list[InvestigationEventOut]
    tool_executions: list[ToolExecutionOut]
    report: InvestigationReportOut | None


T = TypeVar("T")


class Page(ApiModel, Generic[T]):  # noqa: UP046 - keeps Python 3.11 support
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------- Resources, dashboard, settings ----------


class DiscoveredResource(ApiModel):
    service: AwsService
    resource_type: str
    identifier: str
    name: str
    region: str
    health: ResourceHealth
    observed_at: datetime


class ServiceHealth(ApiModel):
    service: AwsService
    healthy: int
    degraded: int
    unhealthy: int


class DashboardOut(ApiModel):
    investigations_last_7d: int = Field(alias="investigationsLast7d")
    open_issues: int
    avg_time_to_report_sec: float
    resources_monitored: dict[str, int]
    health_by_service: list[ServiceHealth]
    daily_investigations: list[dict[str, Any]]
    health_timeline: list[dict[str, Any]]


class UserSettings(ApiModel):
    display_name: str = Field(min_length=1, max_length=120)
    email: str = ""  # read-only; managed by the identity provider
    default_time_range_hours: int = Field(default=6, ge=1, le=24 * 31)
    default_connection_id: str | None = None
    show_raw_evidence_by_default: bool = False
    max_tool_calls: int = Field(default=25, ge=1, le=50)
    investigation_timeout_sec: int = Field(default=300, ge=30, le=900)
    default_region: str = "us-east-1"
    investigation_depth: Literal["fast", "balanced", "thorough"] = "balanced"
    auto_open_report: bool = False
    include_logs: bool = True
    include_deployments: bool = True
    notify_on_failed: bool = True
    notify_on_completed: bool = False
    weekly_digest: bool = True

    @field_validator("default_region")
    @classmethod
    def _r(cls, v: str) -> str:
        return _region(v)
