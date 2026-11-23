from fastapi import APIRouter, status

from app.api.deps import DbDep, SettingsDep, UserDep
from app.schemas.api import ConnectionCreate, ConnectionOut, ConnectionUpdate
from app.services.connections import ConnectionService
from app.services.mappers import connection_out

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionOut])
async def list_connections(db: DbDep, user: UserDep, settings: SettingsDep):
    return [connection_out(c) for c in await ConnectionService(db, user, settings).list()]


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_connection(
    body: ConnectionCreate, db: DbDep, user: UserDep, settings: SettingsDep
):
    """Register a read-only IAM role. Access keys are rejected; nothing secret is stored."""
    return connection_out(await ConnectionService(db, user, settings).create(body))


@router.get("/{connection_id}", response_model=ConnectionOut)
async def get_connection(connection_id: str, db: DbDep, user: UserDep, settings: SettingsDep):
    return connection_out(await ConnectionService(db, user, settings).get(connection_id))


@router.put("/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    connection_id: str, body: ConnectionUpdate, db: DbDep, user: UserDep, settings: SettingsDep
):
    return connection_out(await ConnectionService(db, user, settings).update(connection_id, body))


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: str, db: DbDep, user: UserDep, settings: SettingsDep
) -> None:
    await ConnectionService(db, user, settings).delete(connection_id)


@router.post("/{connection_id}/validate", response_model=ConnectionOut)
async def validate_connection(connection_id: str, db: DbDep, user: UserDep, settings: SettingsDep):
    """Assume the role via STS and confirm it belongs to the configured account.

    In mock mode no AWS call is made.
    """
    return connection_out(await ConnectionService(db, user, settings).validate(connection_id))
