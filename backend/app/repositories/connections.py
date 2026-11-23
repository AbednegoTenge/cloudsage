from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AwsConnection


class ConnectionRepository:
    """AWS connections, always filtered by owner and excluding soft-deleted rows."""

    def __init__(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def _base(self):
        return select(AwsConnection).where(
            AwsConnection.user_id == self.user_id, AwsConnection.deleted_at.is_(None)
        )

    async def list(self) -> list[AwsConnection]:
        return list(
            (await self.db.execute(self._base().order_by(AwsConnection.created_at))).scalars()
        )

    async def get(self, connection_id: uuid.UUID) -> AwsConnection | None:
        return (
            await self.db.execute(self._base().where(AwsConnection.id == connection_id))
        ).scalar_one_or_none()

    async def get_by_name(self, name: str) -> AwsConnection | None:
        return (
            await self.db.execute(self._base().where(AwsConnection.name == name))
        ).scalar_one_or_none()

    async def add(self, conn: AwsConnection) -> AwsConnection:
        conn.user_id = self.user_id
        self.db.add(conn)
        await self.db.flush()
        return conn

    async def soft_delete(self, conn: AwsConnection) -> None:
        # Soft delete keeps investigation history (which references the connection) intact.
        conn.deleted_at = datetime.now(UTC)
        conn.name = f"{conn.name[:40]}~deleted~{conn.id.hex[:8]}"
        await self.db.flush()
