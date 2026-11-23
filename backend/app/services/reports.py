"""Generating and storing the AI report for an investigation.

Evidence (``tool_executions``) is read, never modified. The report is written to its own table,
so the raw evidence and the model's interpretation of it always stay separate.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strands.models.model import Model

from app.agent.model import ModelNotConfigured, build_model
from app.agent.report import Evidence, FinalReport, ReportRequest, synthesize_report
from app.core.config import Settings
from app.models import Investigation, InvestigationReport
from app.repositories.investigations import InvestigationRepository
from app.services.errors import ServiceError


class ModelUnavailable(ServiceError):
    status_code = 503


def evidence_for(inv: Investigation) -> list[Evidence]:
    return [
        Evidence(
            id=str(t.id),
            tool_name=t.tool_name,
            service=t.service,
            status=t.status.value,
            input=t.input or {},
            output=t.output,
            error=t.error,
        )
        for t in sorted(inv.tool_executions, key=lambda t: t.started_at)
    ]


def request_for(inv: Investigation) -> ReportRequest:
    hours = round((inv.time_range_end - inv.time_range_start).total_seconds() / 3600, 1)
    return ReportRequest(
        question=inv.prompt,
        account_id=inv.account_id,
        region=inv.region,
        time_range=(
            f"last {hours:g} h ({inv.time_range_start.isoformat()} to "
            f"{inv.time_range_end.isoformat()})"
        ),
        resources=[r.get("identifier", "") for r in inv.resources or [] if isinstance(r, dict)],
    )


async def store_report(
    db: AsyncSession, repo: InvestigationRepository, inv: Investigation, report: FinalReport
) -> InvestigationReport:
    existing = (
        await db.execute(
            select(InvestigationReport).where(InvestigationReport.investigation_id == inv.id)
        )
    ).scalar_one_or_none()
    row = existing or InvestigationReport(investigation_id=inv.id)
    row.summary = report.summary
    row.observations = report.observations
    row.metrics = report.metrics
    row.log_excerpts = report.log_excerpts
    row.hypotheses = report.hypotheses
    row.recommendations = report.recommendations
    row.confidence = report.confidence
    row.limitations = report.limitations
    row.model_id = report.model_id[:200]
    if existing is None:
        db.add(row)
    inv.summary = report.summary[:500]
    inv.severity = report.severity
    await db.flush()
    await repo.add_event(inv, "report_ready", "Report ready.")
    return row


async def generate_report(
    db: AsyncSession,
    repo: InvestigationRepository,
    settings: Settings,
    inv: Investigation,
    *,
    model: Model | None = None,
) -> InvestigationReport:
    """Synthesize a report from the investigation's stored evidence and save it."""
    try:
        model = model or build_model(settings)
    except ModelNotConfigured as e:
        raise ModelUnavailable(str(e)) from None
    await db.refresh(inv, ["tool_executions"])
    await repo.add_event(inv, "analyzing", "Analyzing collected evidence.")
    report = await synthesize_report(
        model,
        request_for(inv),
        evidence_for(inv),
        timeout_seconds=settings.bedrock_timeout_seconds,
        max_evidence_chars=settings.agent_max_evidence_chars,
    )
    return await store_report(db, repo, inv, report)
