from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbDep, SettingsDep, UserDep
from app.schemas.api import DashboardOut, DiscoveredResource, UserSettings
from app.services import overview

router = APIRouter(tags=["resources"])


@router.get("/resources", response_model=list[DiscoveredResource])
async def list_resources(
    db: DbDep,
    user: UserDep,
    settings: SettingsDep,
    connection_id: Annotated[str | None, Query(alias="connectionId")] = None,
    service: Annotated[Literal["ec2", "ecs", "rds", "lambda"] | None, Query()] = None,
):
    """Discover resources in the user's connected accounts.

    Discovery is limited to each connection's allowed regions.
    """
    return await overview.discover_resources(db, user, settings, connection_id, service)


@router.get("/dashboard", response_model=DashboardOut, tags=["dashboard"])
async def get_dashboard(db: DbDep, user: UserDep, settings: SettingsDep):
    return await overview.dashboard(db, user, settings)


@router.get("/settings", response_model=UserSettings, tags=["settings"])
async def get_user_settings(user: UserDep):
    return overview.get_settings_for(user)


@router.put("/settings", response_model=UserSettings, tags=["settings"])
async def put_user_settings(body: UserSettings, db: DbDep, user: UserDep):
    return await overview.update_settings(db, user, body)
