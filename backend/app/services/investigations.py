from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    ConnectionStatus,
    IdentificationMode,
    Investigation,
    InvestigationEvent,
    InvestigationStatus,
    User,
)
from app.repositories.connections import ConnectionRepository
from app.repositories.investigations import InvestigationRepository
from app.schemas.api import InvestigationCreate
from app.services.connections import parse_uuid
from app.services.errors import Forbidden, NotFound, Unprocessable
from app.services.hints import extract_resources, guess_services, make_title

_PUBLIC_ID = re.compile(r"^inv-(\d{1,18})$", re.I)


def parse_public_id(value: str) -> int:
    m = _PUBLIC_ID.match(value)
    if not m:
        raise NotFound("Investigation not found")
    return int(m.group(1))


class InvestigationService:
    def __init__(self, db: AsyncSession, user: User, settings: Settings) -> None:
        self.db = db
        self.user = user
        self.settings = settings
        self.repo = InvestigationRepository(db, user.id)

    async def create(self, data: InvestigationCreate) -> Investigation:
        conn = await ConnectionRepository(self.db, self.user.id).get(
            parse_uuid(data.connection_id, "Connection")
        )
        if not conn:
            raise NotFound("Connection not found")
        if conn.status is ConnectionStatus.ERROR:
            raise Unprocessable(
                f"Connection '{conn.name}' failed validation; re-validate it before investigating"
            )
        if data.region not in conn.allowed_regions:
            raise Forbidden(f"Region {data.region} is not allowed for connection '{conn.name}'")
        max_hours = self.settings.investigation_max_time_range_hours
        if data.time_range_hours > max_hours:
            raise Unprocessable(f"Time range exceeds the maximum of {max_hours} hours")
        # Identifiers that name a different account are outside this connection's boundary.
        resources = extract_resources(data.prompt)
        for r in resources:
            if not r.identifier.startswith("arn:"):
                continue
            arn_region, arn_account = r.identifier.split(":")[3:5]
            if arn_account != conn.account_id:
                raise Forbidden(
                    "The request references a resource in a different AWS account "
                    "than the selected connection"
                )
            if arn_region != data.region:
                raise Forbidden(
                    f"The request references a resource in {arn_region}, "
                    f"but this investigation is scoped to {data.region}"
                )
        now = datetime.now(UTC)
        inv = Investigation(
            connection_id=conn.id,
            account_id=conn.account_id,
            region=data.region,
            title=make_title(data.prompt),
            prompt=data.prompt,
            status=InvestigationStatus.QUEUED,
            identification_mode=IdentificationMode.EXPLICIT
            if resources
            else IdentificationMode.DISCOVERED,
            services=guess_services(data.prompt, resources),
            resources=[r.model_dump(mode="json") for r in resources],
            time_range_start=now - timedelta(hours=data.time_range_hours),
            time_range_end=now,
        )
        inv = await self.repo.add(inv)
        await self.repo.add_event(inv, "queued", "Investigation queued.")
        return inv

    async def list(self, **filters) -> tuple[list[Investigation], int]:
        if filters.get("connection_id"):
            filters["connection_id"] = parse_uuid(filters["connection_id"], "Connection")
        return await self.repo.list(**filters)

    async def get(self, public_id: str, *, full: bool = True) -> Investigation:
        inv = await self.repo.get_by_number(parse_public_id(public_id), full=full)
        if not inv:
            raise NotFound("Investigation not found")
        return inv

    async def events_after(self, inv: Investigation, after_seq: int) -> list[InvestigationEvent]:
        return await self.repo.events_after(inv.id, after_seq)

    async def is_finished(self, inv: Investigation) -> bool:
        status = await self.repo.status_of(inv.id)
        return status in (
            InvestigationStatus.COMPLETED,
            InvestigationStatus.FAILED,
            InvestigationStatus.TIMED_OUT,
        )
