from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.aws.session import validate_connection
from app.core.config import Settings
from app.models import AwsConnection, ConnectionStatus, User
from app.repositories.connections import ConnectionRepository
from app.schemas.api import ConnectionCreate, ConnectionUpdate
from app.services.errors import Conflict, NotFound


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        raise NotFound(f"{what} not found") from None


class ConnectionService:
    def __init__(self, db: AsyncSession, user: User, settings: Settings) -> None:
        self.db = db
        self.user = user
        self.settings = settings
        self.repo = ConnectionRepository(db, user.id)

    async def list(self) -> list[AwsConnection]:
        return await self.repo.list()

    async def get(self, connection_id: str) -> AwsConnection:
        conn = await self.repo.get(parse_uuid(connection_id, "Connection"))
        if not conn:
            raise NotFound("Connection not found")
        return conn

    async def create(self, data: ConnectionCreate) -> AwsConnection:
        if await self.repo.get_by_name(data.name):
            raise Conflict(f"A connection named '{data.name}' already exists")
        conn = AwsConnection(**data.model_dump(), status=ConnectionStatus.UNVALIDATED)
        try:
            return await self.repo.add(conn)
        except IntegrityError:
            raise Conflict(f"A connection named '{data.name}' already exists") from None

    async def update(self, connection_id: str, data: ConnectionUpdate) -> AwsConnection:
        conn = await self.get(connection_id)
        other = await self.repo.get_by_name(data.name)
        if other and other.id != conn.id:
            raise Conflict(f"A connection named '{data.name}' already exists")
        changed_target = (conn.role_arn, conn.external_id, conn.account_id) != (
            data.role_arn,
            data.external_id,
            data.account_id,
        )
        for k, v in data.model_dump().items():
            setattr(conn, k, v)
        if changed_target:
            # The trust relationship changed; the previous validation no longer applies.
            conn.status, conn.status_message, conn.last_validated_at = (
                ConnectionStatus.UNVALIDATED,
                None,
                None,
            )
        await self.db.flush()
        return conn

    async def delete(self, connection_id: str) -> None:
        conn = await self.get(connection_id)
        await self.repo.soft_delete(conn)

    async def validate(self, connection_id: str) -> AwsConnection:
        conn = await self.get(connection_id)
        result = await validate_connection(
            self.settings,
            role_arn=conn.role_arn,
            external_id=conn.external_id,
            account_id=conn.account_id,
            region=conn.default_region,
        )
        conn.status = ConnectionStatus.CONNECTED if result.ok else ConnectionStatus.ERROR
        conn.status_message = result.message
        conn.last_validated_at = datetime.now(UTC)
        await self.db.flush()
        return conn
