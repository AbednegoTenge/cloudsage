"""Live resource discovery (read-only), built on the same tools investigations use.

Phase 4 covers EC2. ECS, RDS and Lambda discovery arrive with their tools in Phase 6.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.aws.context import open_context
from app.core.config import Settings
from app.models import AwsConnection
from app.schemas.api import DiscoveredResource
from app.tools.ec2 import (
    DescribeInstancesInput,
    InstanceStatusInput,
    describe_instance_status,
    describe_instances,
)

LIVE_SERVICES = ("ec2",)


async def discover_ec2(settings: Settings, conn: AwsConnection) -> list[DiscoveredResource]:
    now = datetime.now(UTC)
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
        instances, statuses = await asyncio.gather(
            asyncio.to_thread(describe_instances, ctx, DescribeInstancesInput()),
            asyncio.to_thread(describe_instance_status, ctx, InstanceStatusInput()),
        )
        health = {s["instanceId"]: s["health"] for s in statuses["statuses"]}
        for i in instances["instances"]:
            if i["state"] == "terminated":
                continue
            out.append(
                DiscoveredResource(
                    service="ec2",
                    resource_type="instance",
                    identifier=i["instanceId"],
                    name=i["name"] or i["instanceId"],
                    region=region,
                    health=health.get(i["instanceId"], "unknown"),  # type: ignore[arg-type]
                    observed_at=now,
                )
            )
    return out
