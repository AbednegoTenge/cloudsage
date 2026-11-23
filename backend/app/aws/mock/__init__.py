"""Canned AWS data for local development (CLOUDSAGE_AWS_MODE=mock). Not real infrastructure."""

from datetime import UTC, datetime, timedelta

from app.schemas.api import DiscoveredResource


def _ago(minutes: int) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


_RESOURCES: list[tuple[str, str, str, str, str, str, int]] = [
    # service, type, identifier, name, region, health, observed (min ago)
    ("ec2", "instance", "i-0a1b2c3d4e5f67890", "api-worker-3", "us-east-1", "unhealthy", 16),
    ("ec2", "instance", "i-0fedcba9876543210", "batch-runner-1", "us-east-1", "degraded", 24),
    ("ec2", "instance", "i-0123456789abcdef0", "api-worker-1", "us-east-1", "healthy", 22),
    ("ec2", "instance", "i-0abcdef1234567890", "api-worker-2", "us-east-1", "healthy", 22),
    ("ec2", "instance", "i-09a8b7c6d5e4f3210", "bastion", "us-west-2", "healthy", 40),
    (
        "ecs",
        "service",
        "arn:aws:ecs:us-east-1:{account}:service/prod-core/payments-api",
        "payments-api",
        "us-east-1",
        "degraded",
        2,
    ),
    (
        "ecs",
        "service",
        "arn:aws:ecs:us-east-1:{account}:service/prod-core/checkout",
        "checkout",
        "us-east-1",
        "healthy",
        12,
    ),
    (
        "ecs",
        "service",
        "arn:aws:ecs:eu-west-1:{account}:service/prod-eu/auth-service",
        "auth-service",
        "eu-west-1",
        "healthy",
        30,
    ),
    ("rds", "db-instance", "orders-db", "orders-db", "us-east-1", "healthy", 35),
    ("rds", "db-instance", "reporting-replica", "reporting-replica", "us-east-1", "degraded", 50),
    ("lambda", "function", "order-processor", "order-processor", "us-west-2", "degraded", 137),
    ("lambda", "function", "invoice-renderer", "invoice-renderer", "us-east-1", "healthy", 60),
    (
        "lambda",
        "function",
        "audit-event-archiver",
        "audit-event-archiver",
        "us-east-1",
        "healthy",
        75,
    ),
]


def mock_resources(
    account_id: str, regions: list[str], service: str | None = None
) -> list[DiscoveredResource]:
    """Resources visible to a connection: same account, allowed regions only."""
    out = []
    for svc, rtype, ident, name, region, health, mins in _RESOURCES:
        if region not in regions or (service and svc != service):
            continue
        out.append(
            DiscoveredResource(
                service=svc,  # type: ignore[arg-type]
                resource_type=rtype,
                identifier=ident.format(account=account_id),
                name=name,
                region=region,
                health=health,  # type: ignore[arg-type]
                observed_at=_ago(mins),
            )
        )
    return out
