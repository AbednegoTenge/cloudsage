"""EC2 tools: instance descriptions and status checks."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

from app.aws.context import AwsContext
from app.tools.base import INSTANCE_ID, ToolInput, iso, register, trim

InstanceId = Annotated[str, StringConstraints(pattern=INSTANCE_ID)]
MAX_INSTANCES = 50


class DescribeInstancesInput(ToolInput):
    instance_ids: list[InstanceId] = Field(default_factory=list, max_length=MAX_INSTANCES)
    name_contains: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[\w .:/@+=-]+$",
        description="Match instances whose Name tag contains this text.",
    )
    state: (
        Literal["pending", "running", "stopping", "stopped", "shutting-down", "terminated"] | None
    ) = None


def _instance(i: dict[str, Any]) -> dict[str, Any]:
    tags = {t["Key"]: t.get("Value", "") for t in i.get("Tags", [])[:20]}
    return {
        "instanceId": i["InstanceId"],
        "name": trim(tags.get("Name")),
        "state": i.get("State", {}).get("Name"),
        "stateReason": trim(i.get("StateReason", {}).get("Message")),
        "instanceType": i.get("InstanceType"),
        "availabilityZone": i.get("Placement", {}).get("AvailabilityZone"),
        "launchTime": iso(i.get("LaunchTime")),
        "privateIpAddress": i.get("PrivateIpAddress"),
        "imageId": i.get("ImageId"),
        "vpcId": i.get("VpcId"),
        "subnetId": i.get("SubnetId"),
        "securityGroups": [g.get("GroupId") for g in i.get("SecurityGroups", [])][:10],
        "iamInstanceProfile": i.get("IamInstanceProfile", {}).get("Arn"),
        "tags": {trim(k, 128): trim(v) for k, v in tags.items()},
    }


@register(
    name="ec2_describe_instances",
    service="ec2",
    description="""
Describe EC2 instances in the investigation's account and region: state, type, placement,
launch time, network and tags. Filter by instance IDs, a Name tag substring, or state.
Returns at most 50 instances. Read-only (DescribeInstances).""",
    input_model=DescribeInstancesInput,
    operations=("DescribeInstances",),
)
def describe_instances(ctx: AwsContext, inp: DescribeInstancesInput) -> dict[str, Any]:
    params: dict[str, Any] = {}
    filters = []
    if inp.instance_ids:
        params["InstanceIds"] = inp.instance_ids
    else:
        params["MaxResults"] = MAX_INSTANCES
    if inp.name_contains:
        filters.append({"Name": "tag:Name", "Values": [f"*{inp.name_contains}*"]})
    if inp.state:
        filters.append({"Name": "instance-state-name", "Values": [inp.state]})
    if filters:
        params["Filters"] = filters
    resp = ctx.client("ec2").describe_instances(**params)
    instances = [_instance(i) for r in resp.get("Reservations", []) for i in r.get("Instances", [])]
    return {
        "instances": instances[:MAX_INSTANCES],
        "count": len(instances[:MAX_INSTANCES]),
        "truncated": bool(resp.get("NextToken")) or len(instances) > MAX_INSTANCES,
    }


class InstanceStatusInput(ToolInput):
    instance_ids: list[InstanceId] = Field(default_factory=list, max_length=MAX_INSTANCES)
    only_impaired: bool = Field(
        default=False, description="Return only instances whose status checks are not ok."
    )


def _health(status: dict[str, Any]) -> str:
    system = status.get("SystemStatus", {}).get("Status")
    instance = status.get("InstanceStatus", {}).get("Status")
    if "impaired" in (system, instance):
        return "unhealthy"
    if system == "ok" and instance == "ok":
        return "healthy"
    if status.get("InstanceState", {}).get("Name") != "running":
        return "unknown"
    return "degraded"


@register(
    name="ec2_describe_instance_status",
    service="ec2",
    description="""
Get EC2 status checks (system and instance reachability) and scheduled events for instances in
the investigation's account and region. Read-only (DescribeInstanceStatus).""",
    input_model=InstanceStatusInput,
    operations=("DescribeInstanceStatus",),
)
def describe_instance_status(ctx: AwsContext, inp: InstanceStatusInput) -> dict[str, Any]:
    params: dict[str, Any] = {"IncludeAllInstances": True}
    if inp.instance_ids:
        params["InstanceIds"] = inp.instance_ids
    else:
        params["MaxResults"] = MAX_INSTANCES
    resp = ctx.client("ec2").describe_instance_status(**params)
    statuses = []
    for s in resp.get("InstanceStatuses", [])[:MAX_INSTANCES]:
        item = {
            "instanceId": s["InstanceId"],
            "state": s.get("InstanceState", {}).get("Name"),
            "systemStatus": s.get("SystemStatus", {}).get("Status"),
            "instanceStatus": s.get("InstanceStatus", {}).get("Status"),
            "details": [
                {
                    "name": d.get("Name"),
                    "status": d.get("Status"),
                    "impairedSince": iso(d.get("ImpairedSince")),
                }
                for part in ("SystemStatus", "InstanceStatus")
                for d in s.get(part, {}).get("Details", [])
            ],
            "events": [
                {
                    "code": e.get("Code"),
                    "description": trim(e.get("Description")),
                    "notBefore": iso(e.get("NotBefore")),
                }
                for e in s.get("Events", [])[:10]
            ],
            "health": _health(s),
        }
        if not inp.only_impaired or item["health"] != "healthy":
            statuses.append(item)
    return {"statuses": statuses, "count": len(statuses), "truncated": bool(resp.get("NextToken"))}
