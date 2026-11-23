"""The tool contract.

A tool is a read-only function over one AWS service. It declares:

* ``name`` and ``service``, and a ``description`` written for the model;
* an ``Input`` Pydantic model that validates every identifier and bounds every limit
  (unknown fields are rejected);
* ``run(ctx, input) -> dict``: JSON-serialisable evidence, built from Describe/List/Get calls only.

Tools never construct credentials and never call mutating APIs. ``READ_ONLY_PREFIXES`` is checked
when a tool registers its AWS operations, so a write call cannot be added by accident.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.aws.context import AwsContext

READ_ONLY_PREFIXES = ("Describe", "List", "Get", "Filter", "Lookup")

INSTANCE_ID = r"^i-[0-9a-f]{8}([0-9a-f]{9})?$"
LOG_GROUP = r"^[\w./#-]{1,512}$"


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, regex_engine="python-re")


class ToolError(RuntimeError):
    """An expected failure with a message that is safe to show and store."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    service: str
    description: str
    input_model: type[ToolInput]
    run: Callable[[AwsContext, Any], dict[str, Any]]
    operations: tuple[str, ...]


ToolFn = Callable[[AwsContext, Any], dict[str, Any]]
REGISTRY: dict[str, ToolSpec] = {}
_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def register(
    *,
    name: str,
    service: str,
    description: str,
    input_model: type[ToolInput],
    operations: tuple[str, ...],
) -> Callable[[ToolFn], ToolFn]:
    if not _NAME.match(name) or name in REGISTRY:
        raise ValueError(f"Invalid or duplicate tool name: {name}")
    for op in operations:
        if not op.startswith(READ_ONLY_PREFIXES):
            raise ValueError(f"Tool {name} declares a non read-only AWS operation: {op}")

    def wrap(fn: ToolFn) -> ToolFn:
        REGISTRY[name] = ToolSpec(name, service, description.strip(), input_model, fn, operations)
        return fn

    return wrap


def get_tool(name: str) -> ToolSpec:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ToolError(f"Unknown tool: {name}") from None


def iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def trim(value: Any, limit: int = 256) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value
