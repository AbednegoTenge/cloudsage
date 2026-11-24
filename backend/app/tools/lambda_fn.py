"""Lambda tools: function configuration and the function list.

Environment variables are never returned: they commonly hold secrets, and CloudSage does not
need their values to investigate.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, StringConstraints

from app.aws.context import AwsContext
from app.tools.base import ToolError, ToolInput, register, trim

FunctionRef = Annotated[
    str,
    StringConstraints(
        pattern=r"^(arn:aws[a-z-]*:lambda:[a-z0-9-]+:\d{12}:function:[\w-]{1,64}(:[\w$-]+)?|[\w-]{1,64})$"
    ),
]


def function_health(cfg: dict[str, Any]) -> str:
    """From configuration state only. Error rates come from CloudWatch, not from here."""
    if cfg.get("State") == "Failed" or cfg.get("LastUpdateStatus") == "Failed":
        return "unhealthy"
    if cfg.get("State") in {"Pending", "Inactive"} or cfg.get("LastUpdateStatus") == "InProgress":
        return "degraded"
    return "unknown"


def _config(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "functionName": c.get("FunctionName"),
        "functionArn": c.get("FunctionArn"),
        "runtime": c.get("Runtime"),
        "packageType": c.get("PackageType"),
        "handler": c.get("Handler"),
        "memoryMB": c.get("MemorySize"),
        "timeoutSeconds": c.get("Timeout"),
        "ephemeralStorageMB": (c.get("EphemeralStorage") or {}).get("Size"),
        "architectures": c.get("Architectures"),
        "lastModified": c.get("LastModified"),
        "version": c.get("Version"),
        "state": c.get("State"),
        "stateReason": trim(c.get("StateReason"), 500),
        "lastUpdateStatus": c.get("LastUpdateStatus"),
        "lastUpdateStatusReason": trim(c.get("LastUpdateStatusReason"), 500),
        "deadLetterTarget": (c.get("DeadLetterConfig") or {}).get("TargetArn"),
        "layers": [layer.get("Arn") for layer in c.get("Layers", [])][:10],
        "inVpc": bool((c.get("VpcConfig") or {}).get("SubnetIds")),
        "environmentVariableCount": len(((c.get("Environment") or {}).get("Variables")) or {}),
    }


class FunctionConfigInput(ToolInput):
    function: FunctionRef


@register(
    name="lambda_get_function_configuration",
    service="lambda",
    description="""
Get one Lambda function's configuration: runtime, memory, timeout, state, last update status and
reason, last modified time, layers and dead-letter target. Environment variable values are never
returned. Use cloudwatch_get_metric_data (AWS/Lambda Errors, Throttles, Duration) for behaviour.
Read-only (GetFunctionConfiguration).""",
    input_model=FunctionConfigInput,
    operations=("GetFunctionConfiguration",),
)
def get_function_configuration(ctx: AwsContext, inp: FunctionConfigInput) -> dict[str, Any]:
    if inp.function.startswith("arn:"):
        ctx.check_arn(inp.function)
    client = ctx.client("lambda")
    try:
        cfg = client.get_function_configuration(FunctionName=inp.function)
    except client.exceptions.ResourceNotFoundException:
        raise ToolError(f"Function not found: {inp.function}") from None
    out = _config(cfg)
    out["health"] = function_health(cfg)
    return out


class ListFunctionsInput(ToolInput):
    name_contains: str | None = Field(default=None, max_length=64, pattern=r"^[\w-]+$")
    max_results: int = Field(default=50, ge=1, le=50)


@register(
    name="lambda_list_functions",
    service="lambda",
    description="""
List Lambda functions in the investigation's account and region (optionally filtered by a name
substring) with runtime, memory, timeout and last modified time. Read-only (ListFunctions).""",
    input_model=ListFunctionsInput,
    operations=("ListFunctions",),
)
def list_functions(ctx: AwsContext, inp: ListFunctionsInput) -> dict[str, Any]:
    client = ctx.client("lambda")
    found: list[dict[str, Any]] = []
    marker = None
    for _ in range(5):  # bounded pagination
        params: dict[str, Any] = {"MaxItems": 50}
        if marker:
            params["Marker"] = marker
        resp = client.list_functions(**params)
        for f in resp.get("Functions", []):
            if inp.name_contains and inp.name_contains.lower() not in f["FunctionName"].lower():
                continue
            found.append({k: v for k, v in _config(f).items() if v not in (None, [], "")})
        marker = resp.get("NextMarker")
        if not marker or len(found) >= inp.max_results:
            break
    return {
        "functions": found[: inp.max_results],
        "count": min(len(found), inp.max_results),
        "truncated": bool(marker) or len(found) > inp.max_results,
    }
