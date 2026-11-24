"""Exposes the registered read-only tools to a Strands agent.

Every call goes through ``ToolRunner``, so it is validated, limited, recorded as evidence and
redacted before anything reaches the model. Results are returned to the model as nonce-tagged
untrusted data.
"""

from __future__ import annotations

import copy
from typing import Any

from strands.tools.tools import PythonAgentTool

from app.agent.untrusted import EvidenceItem, sanitize_text, wrap_evidence
from app.tools.base import REGISTRY, ToolSpec
from app.tools.runner import ToolLimitReached, ToolRunner


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve local ``$ref``s so every model provider gets a self-contained schema."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def _result(tool_use: dict[str, Any], ok: bool, text: str) -> dict[str, Any]:
    return {
        "toolUseId": tool_use["toolUseId"],
        "status": "success" if ok else "error",
        "content": [{"text": text}],
    }


def _agent_tool(spec: ToolSpec, runner: ToolRunner, nonce: str, max_chars: int) -> PythonAgentTool:
    async def call(tool_use: dict[str, Any], **_: Any) -> dict[str, Any]:
        try:
            result = await runner.run(spec.name, tool_use.get("input") or {})
        except ToolLimitReached as e:
            return _result(tool_use, False, f"{e}. Stop calling tools and give your summary.")
        item = EvidenceItem(
            alias=f"E{runner.calls}",
            tool_name=spec.name,
            service=spec.service,
            status="succeeded" if result.ok else "failed",
            input=tool_use.get("input") or {},
            output=result.output,
            error=result.error,
        )
        return _result(tool_use, result.ok, wrap_evidence([item], nonce, max_chars))

    tool_spec = {
        "name": spec.name,
        "description": sanitize_text(spec.description, 2000),
        "inputSchema": {"json": inline_schema(spec.input_model.model_json_schema())},
    }
    return PythonAgentTool(spec.name, tool_spec, call)


def agent_tools(runner: ToolRunner, nonce: str, max_chars: int) -> list[PythonAgentTool]:
    return [_agent_tool(spec, runner, nonce, max_chars) for spec in REGISTRY.values()]
