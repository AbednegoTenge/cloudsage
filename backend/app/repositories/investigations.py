from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Investigation, InvestigationEvent, InvestigationStatus, ToolExecution


class InvestigationRepository:
    """Investigations and their events/evidence, always filtered by owner."""

    def __init__(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def _base(self) -> Select[tuple[Investigation]]:
        return select(Investigation).where(Investigation.user_id == self.user_id)

    def _filtered(
        self,
        status: InvestigationStatus | None,
        connection_id: uuid.UUID | None,
        search: str | None,
    ) -> Select[tuple[Investigation]]:
        q = self._base()
        if status:
            q = q.where(Investigation.status == status)
        if connection_id:
            q = q.where(Investigation.connection_id == connection_id)
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            q = q.where(
                or_(
                    Investigation.title.ilike(like),
                    Investigation.prompt.ilike(like),
                    Investigation.summary.ilike(like),
                    Investigation.resources.cast(Text).ilike(like),
                )
            )
        return q

    async def list(
        self,
        *,
        status: InvestigationStatus | None = None,
        connection_id: uuid.UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Investigation], int]:
        q = self._filtered(status, connection_id, search)
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        rows = await self.db.execute(
            q.options(selectinload(Investigation.tool_executions))
            .order_by(Investigation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars()), total

    async def get_by_number(self, number: int, *, full: bool = False) -> Investigation | None:
        q = self._base().where(Investigation.number == number)
        opts = [selectinload(Investigation.tool_executions)]
        if full:
            opts += [selectinload(Investigation.events), selectinload(Investigation.report)]
        return (await self.db.execute(q.options(*opts))).scalar_one_or_none()

    async def add(self, inv: Investigation) -> Investigation:
        inv.user_id = self.user_id
        self.db.add(inv)
        await self.db.flush()
        await self.db.refresh(inv, ["number", "tool_executions"])
        return inv

    async def add_event(
        self,
        inv: Investigation,
        type_: str,
        message: str,
        *,
        tool_execution: ToolExecution | None = None,
        payload: dict | None = None,
    ) -> InvestigationEvent:
        seq = (
            await self.db.execute(
                select(func.coalesce(func.max(InvestigationEvent.seq), 0)).where(
                    InvestigationEvent.investigation_id == inv.id
                )
            )
        ).scalar_one() + 1
        ev = InvestigationEvent(
            investigation_id=inv.id,
            seq=seq,
            type=type_,
            message=message,
            payload=payload or {},
            tool_execution_id=tool_execution.id if tool_execution else None,
        )
        self.db.add(ev)
        await self.db.flush()
        return ev

    async def events_after(self, inv_id: uuid.UUID, after_seq: int) -> list[InvestigationEvent]:
        q = (
            select(InvestigationEvent)
            .join(Investigation)
            .where(
                Investigation.user_id == self.user_id,
                InvestigationEvent.investigation_id == inv_id,
                InvestigationEvent.seq > after_seq,
            )
            .order_by(InvestigationEvent.seq)
        )
        return list((await self.db.execute(q)).scalars())

    async def stats_since(self, since: datetime) -> list[Investigation]:
        rows = await self.db.execute(self._base().where(Investigation.created_at >= since))
        return list(rows.scalars())

    async def status_of(self, inv_id: uuid.UUID) -> InvestigationStatus | None:
        return (
            await self.db.execute(
                select(Investigation.status).where(
                    Investigation.user_id == self.user_id, Investigation.id == inv_id
                )
            )
        ).scalar_one_or_none()
