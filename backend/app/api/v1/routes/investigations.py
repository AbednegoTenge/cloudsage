import asyncio
import json
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbDep, SettingsDep, UserDep
from app.core.db import get_sessionmaker
from app.models import InvestigationStatus
from app.schemas.api import (
    InvestigationCreate,
    InvestigationDetailOut,
    InvestigationEventOut,
    InvestigationOut,
    Page,
)
from app.services.investigations import InvestigationService
from app.services.mappers import detail_out, event_out, investigation_out

router = APIRouter(prefix="/investigations", tags=["investigations"])

StatusFilter = Literal["queued", "running", "completed", "failed", "timed_out"]


@router.post("", response_model=InvestigationOut, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    body: InvestigationCreate, db: DbDep, user: UserDep, settings: SettingsDep
):
    """Queue an investigation bound to one connection (account) and one allowed region."""
    return investigation_out(await InvestigationService(db, user, settings).create(body))


@router.get("", response_model=Page[InvestigationOut])
async def list_investigations(
    db: DbDep,
    user: UserDep,
    settings: SettingsDep,
    status_: Annotated[StatusFilter | None, Query(alias="status")] = None,
    connection_id: Annotated[str | None, Query(alias="connectionId")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = await InvestigationService(db, user, settings).list(
        status=InvestigationStatus(status_) if status_ else None,
        connection_id=connection_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return Page[InvestigationOut](
        items=[investigation_out(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/{investigation_id}", response_model=InvestigationDetailOut)
async def get_investigation(investigation_id: str, db: DbDep, user: UserDep, settings: SettingsDep):
    """Investigation, its timeline, raw tool evidence and (separately) the AI report."""
    return detail_out(await InvestigationService(db, user, settings).get(investigation_id))


@router.get("/{investigation_id}/events", response_model=list[InvestigationEventOut])
async def get_events(
    investigation_id: str,
    db: DbDep,
    user: UserDep,
    settings: SettingsDep,
    after: Annotated[int, Query(ge=0)] = 0,
):
    svc = InvestigationService(db, user, settings)
    inv = await svc.get(investigation_id, full=False)
    return [event_out(inv, e) for e in await svc.events_after(inv, after)]


@router.get("/{investigation_id}/stream", response_class=StreamingResponse)
async def stream_events(
    investigation_id: str,
    request: Request,
    db: DbDep,
    user: UserDep,
    settings: SettingsDep,
    after: Annotated[int, Query(ge=0)] = 0,
):
    """Server-Sent Events: replays events after ``after`` (or Last-Event-ID), then streams new ones
    until the investigation finishes. Each SSE ``id`` is the event sequence number."""
    inv = await InvestigationService(db, user, settings).get(investigation_id, full=False)
    last = int(request.headers.get("last-event-id", after) or 0)
    deadline = time.monotonic() + settings.investigation_timeout_seconds + 60
    sessionmaker = get_sessionmaker(settings)

    async def gen():
        nonlocal last
        idle = 0.0
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            async with sessionmaker() as s:
                svc = InvestigationService(s, user, settings)
                events = await svc.events_after(inv, last)
                finished = await svc.is_finished(inv)
            for e in events:
                last = e.seq
                payload = event_out(inv, e).model_dump(mode="json", by_alias=True)
                yield f"id: {e.seq}\nevent: investigation\ndata: {json.dumps(payload)}\n\n"
            if finished and not events:
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0.0 if events else idle + settings.sse_poll_interval_seconds
            if idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"
            await asyncio.sleep(settings.sse_poll_interval_seconds)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
