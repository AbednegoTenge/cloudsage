"""SQLAlchemy ORM models.

Every user-owned row carries ``user_id`` (directly or via its investigation) so repositories can
enforce per-user isolation. No AWS secret material is ever stored: a connection is a role ARN
plus an optional external ID.
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow
    )


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ConnectionStatus(enum.StrEnum):
    CONNECTED = "connected"
    UNVALIDATED = "unvalidated"
    ERROR = "error"


class InvestigationStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class IdentificationMode(enum.StrEnum):
    EXPLICIT = "explicit"
    DISCOVERED = "discovered"


class ToolExecutionStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    preferences: Mapped[dict[str, Any]] = mapped_column(default=dict)

    connections: Mapped[list["AwsConnection"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    investigations: Mapped[list["Investigation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AwsConnection(TimestampMixin, Base):
    __tablename__ = "aws_connections"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_connection_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(12))
    role_arn: Mapped[str] = mapped_column(String(2048))
    external_id: Mapped[str | None] = mapped_column(String(1224))
    default_region: Mapped[str] = mapped_column(String(32))
    allowed_regions: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    status: Mapped[ConnectionStatus] = mapped_column(
        _enum(ConnectionStatus, "connection_status"), default=ConnectionStatus.UNVALIDATED
    )
    status_message: Mapped[str | None] = mapped_column(Text)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="connections")


investigation_number_seq = Sequence("investigation_number_seq", start=1001)


class Investigation(TimestampMixin, Base):
    __tablename__ = "investigations"
    __table_args__ = (Index("ix_investigations_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Human-friendly sequential reference, e.g. INV-1042.
    number: Mapped[int] = mapped_column(
        BigInteger,
        investigation_number_seq,
        server_default=investigation_number_seq.next_value(),
        unique=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("aws_connections.id", ondelete="RESTRICT"), index=True
    )
    # Account is copied at creation so history stays accurate if a connection changes.
    account_id: Mapped[str] = mapped_column(String(12))
    region: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[InvestigationStatus] = mapped_column(
        _enum(InvestigationStatus, "investigation_status"),
        default=InvestigationStatus.QUEUED,
        index=True,
    )
    identification_mode: Mapped[IdentificationMode] = mapped_column(
        _enum(IdentificationMode, "identification_mode"), default=IdentificationMode.DISCOVERED
    )
    services: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    resources: Mapped[list[Any]] = mapped_column(default=list)
    time_range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(16))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="investigations")
    connection: Mapped[AwsConnection] = relationship()
    events: Mapped[list["InvestigationEvent"]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        order_by="InvestigationEvent.seq",
    )
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        order_by="ToolExecution.started_at",
    )
    report: Mapped["InvestigationReport | None"] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", uselist=False
    )


class InvestigationEvent(TimestampMixin, Base):
    __tablename__ = "investigation_events"
    __table_args__ = (
        UniqueConstraint("investigation_id", "seq", name="uq_event_investigation_seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    tool_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_executions.id", ondelete="SET NULL")
    )

    investigation: Mapped[Investigation] = relationship(back_populates="events")


class ToolExecution(Base):
    """Raw evidence: exactly what a tool returned. Never edited by the model."""

    __tablename__ = "tool_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100))
    service: Mapped[str] = mapped_column(String(32))
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[ToolExecutionStatus] = mapped_column(
        _enum(ToolExecutionStatus, "tool_execution_status"), default=ToolExecutionStatus.RUNNING
    )
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    investigation: Mapped[Investigation] = relationship(back_populates="tool_executions")


class InvestigationReport(TimestampMixin, Base):
    """AI-generated report. Stored separately from the evidence it cites."""

    __tablename__ = "investigation_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)
    observations: Mapped[list[Any]] = mapped_column(default=list)
    metrics: Mapped[list[Any]] = mapped_column(default=list)
    log_excerpts: Mapped[list[Any]] = mapped_column(default=list)
    hypotheses: Mapped[list[Any]] = mapped_column(default=list)
    recommendations: Mapped[list[Any]] = mapped_column(default=list)
    confidence: Mapped[str] = mapped_column(String(8))
    limitations: Mapped[list[Any]] = mapped_column(default=list)
    model_id: Mapped[str] = mapped_column(String(200))

    investigation: Mapped[Investigation] = relationship(back_populates="report")
