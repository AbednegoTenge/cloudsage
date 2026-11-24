"""Live resource discovery (read-only), built on the same tools investigations use.

Health comes only from what AWS reports: EC2 status checks, ECS task counts and rollout state,
and RDS instance status. Lambda configuration says nothing about errors, so a function is
``unknown`` unless its state is failed or pending; its error rate is a CloudWatch question.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.aws.context import AwsContext, open_context
from app.core.config import Settings
from app.models import AwsConnection
from app.schemas.api import DiscoveredResource
from app.tools.ec2 import (
    DescribeInstancesInput,
    InstanceStatusInput,
    describe_instance_status,
    describe_instances,
)
from app.tools.ecs import DescribeServicesInput, ListServicesInput, describe_services, list_services
from app.tools.lambda_fn import ListFunctionsInput, function_health, list_functions
from app.tools.rds import DescribeDbInstancesInput, describe_db_instances

LIVE_SERVICES = ("ec2", "ecs", "rds", "lambda")


def _ec2(ctx: AwsContext, now: datetime) -> list[DiscoveredResource]:
    instances = describe_instances(ctx, DescribeInstancesInput())
    statuses = describe_instance_status(ctx, InstanceStatusInput())
    health = {s["instanceId"]: s["health"] for s in statuses["statuses"]}
    return [
        DiscoveredResource(
            service="ec2",
            resource_type="instance",
            identifier=i["instanceId"],
            name=i["name"] or i["instanceId"],
            region=ctx.region,
            health=health.get(i["instanceId"], "unknown"),  # type: ignore[arg-type]
            observed_at=now,
        )
        for i in instances["instances"]
        if i["state"] != "terminated"
    ]


def _ecs(ctx: AwsContext, now: datetime) -> list[DiscoveredResource]:
    listed = list_services(ctx, ListServicesInput(max_results=100))["services"]
    by_cluster: dict[str, list[str]] = {}
    for s in listed:
        by_cluster.setdefault(s["cluster"], []).append(s["serviceArn"])
    out = []
    for cluster, arns in by_cluster.items():
        for i in range(0, len(arns), 10):  # DescribeServices takes up to 10
            described = describe_services(
                ctx, DescribeServicesInput(cluster=cluster, services=arns[i : i + 10], max_events=1)
            )
            out.extend(
                DiscoveredResource(
                    service="ecs",
                    resource_type="service",
                    identifier=s["serviceArn"],
                    name=s["serviceName"],
                    region=ctx.region,
                    health=s["health"],  # type: ignore[arg-type]
                    observed_at=now,
                )
                for s in described["services"]
            )
    return out


def _rds(ctx: AwsContext, now: datetime) -> list[DiscoveredResource]:
    return [
        DiscoveredResource(
            service="rds",
            resource_type="db-instance",
            identifier=d["dbInstanceIdentifier"],
            name=d["dbInstanceIdentifier"],
            region=ctx.region,
            health=d["health"],  # type: ignore[arg-type]
            observed_at=now,
        )
        for d in describe_db_instances(ctx, DescribeDbInstancesInput())["dbInstances"]
    ]


def _lambda(ctx: AwsContext, now: datetime) -> list[DiscoveredResource]:
    out = []
    for f in list_functions(ctx, ListFunctionsInput())["functions"]:
        cfg = {"State": f.get("state"), "LastUpdateStatus": f.get("lastUpdateStatus")}
        out.append(
            DiscoveredResource(
                service="lambda",
                resource_type="function",
                identifier=f["functionName"],
                name=f["functionName"],
                region=ctx.region,
                health=function_health(cfg),  # type: ignore[arg-type]
                observed_at=now,
            )
        )
    return out


_BY_SERVICE = {"ec2": _ec2, "ecs": _ecs, "rds": _rds, "lambda": _lambda}


async def discover(
    settings: Settings, conn: AwsConnection, service: str | None = None
) -> list[DiscoveredResource]:
    now = datetime.now(UTC)
    services = [service] if service else list(LIVE_SERVICES)
    out: list[DiscoveredResource] = []
    for region in conn.allowed_regions:
        ctx = await open_context(
            settings,
            role_arn=conn.role_arn,
            external_id=conn.external_id,
            account_id=conn.account_id,
            region=region,
            allowed_regions=list(conn.allowed_regions),
            start=now - timedelta(hours=1),
            end=now,
            session_name="cloudsage-discovery",
        )
        results = await asyncio.gather(
            *(asyncio.to_thread(_BY_SERVICE[s], ctx, now) for s in services)
        )
        for r in results:
            out.extend(r)
    return out
