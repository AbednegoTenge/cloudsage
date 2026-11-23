"""ORM -> API schema mapping."""

from app.models import (
    AwsConnection,
    Investigation,
    InvestigationEvent,
    InvestigationReport,
    ToolExecution,
)
from app.schemas.api import (
    ConnectionOut,
    InvestigationDetailOut,
    InvestigationEventOut,
    InvestigationOut,
    InvestigationReportOut,
    ResourceRef,
    TimeRange,
    ToolExecutionOut,
)


def public_id(inv: Investigation) -> str:
    return f"inv-{inv.number}"


def connection_out(c: AwsConnection) -> ConnectionOut:
    return ConnectionOut(
        id=str(c.id),
        name=c.name,
        account_id=c.account_id,
        role_arn=c.role_arn,
        external_id=c.external_id,
        default_region=c.default_region,
        allowed_regions=list(c.allowed_regions),
        status=c.status.value,
        status_message=c.status_message,
        last_validated_at=c.last_validated_at,
    )


def investigation_out(inv: Investigation) -> InvestigationOut:
    return InvestigationOut(
        id=public_id(inv),
        title=inv.title,
        prompt=inv.prompt,
        connection_id=str(inv.connection_id),
        account_id=inv.account_id,
        region=inv.region,
        status=inv.status.value,
        identification_mode=inv.identification_mode.value,
        services=list(inv.services or []),
        resources=[ResourceRef.model_validate(r) for r in inv.resources or []],
        time_range=TimeRange(start=inv.time_range_start, end=inv.time_range_end),
        created_at=inv.created_at,
        completed_at=inv.completed_at,
        tool_call_count=len(inv.tool_executions),
        severity=inv.severity,
        summary=inv.summary,
    )


def event_out(inv: Investigation, e: InvestigationEvent) -> InvestigationEventOut:
    return InvestigationEventOut(
        id=str(e.id),
        investigation_id=public_id(inv),
        seq=e.seq,
        type=e.type,
        message=e.message,
        created_at=e.created_at,
        tool_execution_id=str(e.tool_execution_id) if e.tool_execution_id else None,
    )


def tool_out(inv: Investigation, t: ToolExecution) -> ToolExecutionOut:
    return ToolExecutionOut(
        id=str(t.id),
        investigation_id=public_id(inv),
        tool_name=t.tool_name,
        service=t.service,
        input=t.input,
        output=t.output,
        status=t.status.value,
        error=t.error,
        duration_ms=t.duration_ms,
        started_at=t.started_at,
    )


def report_out(inv: Investigation, r: InvestigationReport) -> InvestigationReportOut:
    return InvestigationReportOut(
        investigation_id=public_id(inv),
        summary=r.summary,
        observations=r.observations,
        metrics=r.metrics,
        log_excerpts=r.log_excerpts,
        hypotheses=r.hypotheses,
        recommendations=r.recommendations,
        confidence=r.confidence,  # type: ignore[arg-type]
        limitations=r.limitations,
        model_id=r.model_id,
        generated_at=r.created_at,
    )


def detail_out(inv: Investigation) -> InvestigationDetailOut:
    return InvestigationDetailOut(
        investigation=investigation_out(inv),
        events=[event_out(inv, e) for e in inv.events],
        tool_executions=[tool_out(inv, t) for t in inv.tool_executions],
        report=report_out(inv, inv.report) if inv.report else None,
    )
