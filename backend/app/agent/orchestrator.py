"""Runs one investigation end to end.

1. Mark it running and emit ``planning``.
2. Open a scoped AWS context for the connection (temporary credentials, one account and region,
   the investigation's time window).
3. Let the investigator agent call the read-only tools. Every call is recorded as evidence by
   ``ToolRunner`` and committed as it happens, so the SSE stream shows progress live.
4. Write the report from the recorded evidence with a separate, tool-less model call.
5. Mark it completed, failed or timed out.

Limits: the tool-call budget and wall-clock timeout are the lower of the server limits and the
user's own settings. Evidence gathering gets 70% of the time; the report gets what is left.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from strands import Agent
from strands.models.model import Model
from strands.tools.executors import SequentialToolExecutor

from app.agent.model import ModelNotConfigured, build_model
from app.agent.prompts import INVESTIGATOR_PROMPT, build_investigation_prompt
from app.agent.report import ReportGenerationError
from app.agent.tools import agent_tools
from app.agent.untrusted import new_nonce, sanitize_text
from app.aws.context import BoundaryViolation, open_context
from app.aws.session import AssumeRoleError
from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.core.logging import redact
from app.models import (
    AwsConnection,
    Investigation,
    InvestigationStatus,
    ToolExecution,
    ToolExecutionStatus,
    User,
)
from app.repositories.investigations import InvestigationRepository
from app.services.reports import ModelUnavailable, generate_report
from app.tools.runner import ToolRunner

log = logging.getLogger(__name__)
GATHER_SHARE = 0.7

ModelFactory = Callable[[Settings], Model]


class InvestigationFailure(RuntimeError):
    """An expected failure with a message that is safe to show the user."""


def limits_for(settings: Settings, user: User) -> tuple[int, int]:
    prefs = user.preferences or {}

    def pref(key: str, server: int) -> int:
        try:
            return max(1, min(int(prefs.get(key, server)), server))
        except (TypeError, ValueError):
            return server

    return (
        pref("max_tool_calls", settings.investigation_max_tool_calls),
        pref("investigation_timeout_sec", settings.investigation_timeout_seconds),
    )


async def run_investigation(
    settings: Settings, investigation_id: uuid.UUID, *, model_factory: ModelFactory = build_model
) -> None:
    db = get_sessionmaker(settings)()
    try:
        await _run(settings, db, investigation_id, model_factory)
    finally:
        await _close(db)


async def _close(db: AsyncSession) -> None:
    try:
        await db.close()
    except Exception:  # noqa: BLE001 - a session broken by cancellation may not close cleanly
        log.debug("session close failed", exc_info=True)


async def _run(
    settings: Settings, db: AsyncSession, investigation_id: uuid.UUID, model_factory: ModelFactory
) -> None:
    inv = await db.get(Investigation, investigation_id)
    if inv is None or inv.status is not InvestigationStatus.QUEUED:
        return  # already handled (or deleted); runs are idempotent
    user = await db.get(User, inv.user_id)
    assert user is not None
    repo = InvestigationRepository(db, inv.user_id)
    max_calls, timeout = limits_for(settings, user)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    inv.status = InvestigationStatus.RUNNING
    await repo.add_event(
        inv,
        "planning",
        f"Planning the investigation in account {inv.account_id}, {inv.region}.",
        payload={"maxToolCalls": max_calls, "timeoutSeconds": timeout},
    )
    await db.commit()

    try:
        model = model_factory(settings)
        conn = await db.get(AwsConnection, inv.connection_id)
        if conn is None or conn.deleted_at is not None:
            raise InvestigationFailure("The AWS connection for this investigation was removed")
        ctx = await open_context(
            settings,
            role_arn=conn.role_arn,
            external_id=conn.external_id,
            account_id=inv.account_id,
            region=inv.region,
            allowed_regions=list(conn.allowed_regions),
            start=inv.time_range_start,
            end=inv.time_range_end,
            session_name=f"cloudsage-inv-{inv.number}",
        )
        runner = ToolRunner(
            db, repo, inv, ctx, settings, max_calls=max_calls, on_progress=db.commit
        )
        agent = Agent(
            model=model,
            system_prompt=INVESTIGATOR_PROMPT,
            tools=agent_tools(runner, new_nonce(), settings.agent_max_evidence_chars),
            tool_executor=SequentialToolExecutor(),
            callback_handler=None,
        )
        prompt = build_investigation_prompt(
            question=sanitize_text(inv.prompt, 2000),
            account_id=inv.account_id,
            region=inv.region,
            start=inv.time_range_start.isoformat(),
            end=inv.time_range_end.isoformat(),
            resources=[
                sanitize_text(str(r.get("identifier", "")), 256)
                for r in inv.resources or []
                if isinstance(r, dict)
            ],
            services=list(inv.services or []),
            max_tool_calls=max_calls,
        )
        try:
            await asyncio.wait_for(
                agent.invoke_async(prompt, limits={"turns": max_calls + 2}),
                timeout=timeout * GATHER_SHARE,
            )
        except TimeoutError:
            # Cancellation can leave the session mid-flush: continue on a fresh one.
            await _close(db)
            db = get_sessionmaker(settings)()
            await _close_running_tools(db, investigation_id)
            inv = await db.get(Investigation, investigation_id)
            assert inv is not None
            repo = InvestigationRepository(db, inv.user_id)
            await repo.add_event(
                inv,
                "analyzing",
                "The time for gathering evidence ran out; reporting on what was collected.",
            )
            await db.commit()
        except Exception as e:  # model or SDK failure while gathering
            raise InvestigationFailure(
                redact(f"The model failed while gathering evidence: {e}")[:500]
            ) from e

        remaining = deadline - loop.time()
        if remaining <= 1:
            raise TimeoutError
        await asyncio.wait_for(
            generate_report(db, repo, settings, inv, model=model), timeout=remaining
        )
        inv.status = InvestigationStatus.COMPLETED
        inv.completed_at = datetime.now(UTC)
        await db.commit()
    except TimeoutError:
        await _fail(
            settings,
            db,
            investigation_id,
            InvestigationStatus.TIMED_OUT,
            f"Timed out after {timeout} s.",
        )
    except (
        InvestigationFailure,
        ModelNotConfigured,
        ModelUnavailable,
        AssumeRoleError,
        BoundaryViolation,
        ReportGenerationError,
    ) as e:
        await _fail(settings, db, investigation_id, InvestigationStatus.FAILED, str(e))
    except Exception:
        log.exception("Investigation %s failed unexpectedly", investigation_id)
        await _fail(
            settings,
            db,
            investigation_id,
            InvestigationStatus.FAILED,
            "The investigation stopped because of an unexpected error.",
        )
    await _close(db)  # the session in use may have been replaced after a gathering timeout


async def _close_running_tools(db: AsyncSession, investigation_id: uuid.UUID) -> None:
    """Close out any tool call that was cut off, so no evidence row is left 'running'."""
    await db.execute(
        update(ToolExecution)
        .where(
            ToolExecution.investigation_id == investigation_id,
            ToolExecution.status == ToolExecutionStatus.RUNNING,
        )
        .values(status=ToolExecutionStatus.FAILED, error="Interrupted by the investigation limit")
    )


async def _fail(
    settings: Settings,
    old_db: AsyncSession,
    investigation_id: uuid.UUID,
    status: InvestigationStatus,
    message: str,
) -> None:
    """Record the outcome on a fresh session; the old one may be unusable after a cancellation."""
    await _close(old_db)
    message = redact(message)[:500]
    async with get_sessionmaker(settings)() as db:
        await _close_running_tools(db, investigation_id)
        inv = await db.get(Investigation, investigation_id)
        if inv is None:
            return
        inv.status = status
        inv.completed_at = datetime.now(UTC)
        if not inv.summary:
            inv.summary = message
        await InvestigationRepository(db, inv.user_id).add_event(inv, "failed", message)
        await db.commit()
