"""Dashboard aggregation, resource discovery and user settings."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.aws.mock import mock_resources
from app.core.config import AwsMode, Settings
from app.models import InvestigationStatus, User
from app.repositories.connections import ConnectionRepository
from app.repositories.investigations import InvestigationRepository
from app.repositories.users import UserRepository
from app.schemas.api import DashboardOut, DiscoveredResource, ServiceHealth, UserSettings
from app.services.connections import parse_uuid
from app.services.errors import NotFound, ServiceError

SERVICES = ("ec2", "ecs", "rds", "lambda")


class NotImplementedYet(ServiceError):
    status_code = 501


async def discover_resources(
    db: AsyncSession, user: User, settings: Settings, connection_id: str | None, service: str | None
) -> list[DiscoveredResource]:
    repo = ConnectionRepository(db, user.id)
    if connection_id:
        conn = await repo.get(parse_uuid(connection_id, "Connection"))
        if not conn:
            raise NotFound("Connection not found")
        conns = [conn]
    else:
        conns = await repo.list()
    if settings.aws_mode is not AwsMode.MOCK:
        raise NotImplementedYet("Live resource discovery arrives with the AWS tools (Phase 4)")
    out: list[DiscoveredResource] = []
    for c in conns:
        out.extend(mock_resources(c.account_id, list(c.allowed_regions), service))
    order = {"unhealthy": 0, "degraded": 1, "unknown": 2, "healthy": 3}
    return sorted(out, key=lambda r: (order[r.health], r.name))


async def dashboard(db: AsyncSession, user: User, settings: Settings) -> DashboardOut:
    now = datetime.now(UTC)
    invs = await InvestigationRepository(db, user.id).stats_since(now - timedelta(days=7))
    done = [i for i in invs if i.completed_at and i.status is InvestigationStatus.COMPLETED]
    avg = (
        sum((i.completed_at - i.created_at).total_seconds() for i in done) / len(done)
        if done
        else 0.0
    )  # type: ignore[operator]
    per_day = Counter(i.created_at.astimezone(UTC).date() for i in invs)
    days = [(now - timedelta(days=d)).date() for d in range(6, -1, -1)]

    resources: list[DiscoveredResource] = []
    if settings.aws_mode is AwsMode.MOCK:
        resources = await discover_resources(db, user, settings, None, None)
    by_svc = {s: Counter(r.health for r in resources if r.service == s) for s in SERVICES}
    unhealthy_now = sum(c["unhealthy"] + c["degraded"] for c in by_svc.values())
    healthy_now = sum(c["healthy"] for c in by_svc.values())
    # Health history needs CloudWatch-backed sampling (Phase 4+); until then show the current
    # snapshot as a flat series so the chart is honest rather than invented.
    timeline = [
        {
            "t": (now - timedelta(minutes=5 * k)).isoformat(),
            "healthy": healthy_now,
            "unhealthy": unhealthy_now,
        }
        for k in range(12, -1, -1)
    ]
    return DashboardOut(
        investigations_last_7d=len(invs),
        open_issues=unhealthy_now,
        avg_time_to_report_sec=round(avg, 1),
        resources_monitored={s: sum(by_svc[s].values()) for s in SERVICES} | {"cloudwatch": 0},
        health_by_service=[
            ServiceHealth(
                service=s,
                healthy=by_svc[s]["healthy"],
                degraded=by_svc[s]["degraded"],
                unhealthy=by_svc[s]["unhealthy"],
            )  # type: ignore[arg-type]
            for s in SERVICES
        ],
        daily_investigations=[
            {"day": d.strftime("%b %d"), "count": per_day.get(d, 0)} for d in days
        ],
        health_timeline=timeline,
    )


def get_settings_for(user: User) -> UserSettings:
    prefs = {k: v for k, v in (user.preferences or {}).items() if k in UserSettings.model_fields}
    return UserSettings(**prefs, display_name=user.display_name, email=user.email)


async def update_settings(db: AsyncSession, user: User, data: UserSettings) -> UserSettings:
    if data.default_connection_id:
        if not await ConnectionRepository(db, user.id).get(
            parse_uuid(data.default_connection_id, "Connection")
        ):
            raise NotFound("Connection not found")
    prefs = data.model_dump(exclude={"display_name", "email"})
    await UserRepository(db).update_preferences(user, data.display_name, prefs)
    return get_settings_for(user)
