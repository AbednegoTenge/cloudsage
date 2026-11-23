"""Runs queued investigations in the API process, with bounded concurrency.

On startup it recovers from a restart: investigations left ``running`` are marked failed (their
in-memory state is gone) and ``queued`` ones are started again.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.agent.model import build_model
from app.agent.orchestrator import ModelFactory, run_investigation
from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.models import Investigation, InvestigationEvent, InvestigationStatus

log = logging.getLogger(__name__)


class InvestigationWorker:
    def __init__(self, settings: Settings, model_factory: ModelFactory | None = None) -> None:
        self.settings = settings
        self.model_factory = model_factory or build_model
        self._slots = asyncio.Semaphore(settings.investigation_max_concurrent)
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(self, investigation_id: uuid.UUID) -> asyncio.Task[None]:
        task = asyncio.create_task(self._run(investigation_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run(self, investigation_id: uuid.UUID) -> None:
        async with self._slots:
            try:
                await run_investigation(
                    self.settings, investigation_id, model_factory=self.model_factory
                )
            except Exception:
                log.exception("Investigation worker crashed for %s", investigation_id)

    async def recover(self) -> None:
        async with get_sessionmaker(self.settings)() as db:
            stale = (
                (
                    await db.execute(
                        select(Investigation).where(
                            Investigation.status == InvestigationStatus.RUNNING
                        )
                    )
                )
                .scalars()
                .all()
            )
            for inv in stale:
                last = (
                    await db.execute(
                        select(InvestigationEvent.seq)
                        .where(InvestigationEvent.investigation_id == inv.id)
                        .order_by(InvestigationEvent.seq.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none() or 0
                db.add(
                    InvestigationEvent(
                        investigation_id=inv.id,
                        seq=last + 1,
                        type="failed",
                        message="Interrupted by a server restart. Start a new investigation.",
                        payload={},
                    )
                )
            if stale:
                await db.execute(
                    update(Investigation)
                    .where(Investigation.id.in_([i.id for i in stale]))
                    .values(
                        status=InvestigationStatus.FAILED,
                        completed_at=datetime.now(UTC),
                        summary="Interrupted by a server restart.",
                    )
                )
            queued = (
                (
                    await db.execute(
                        select(Investigation.id)
                        .where(Investigation.status == InvestigationStatus.QUEUED)
                        .order_by(Investigation.created_at)
                    )
                )
                .scalars()
                .all()
            )
            await db.commit()
        for inv_id in queued:
            self.submit(inv_id)

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
