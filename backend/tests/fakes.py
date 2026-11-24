"""A scripted stand-in for Amazon Bedrock, so agent tests never call AWS."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from strands.models.model import Model


@dataclass
class ToolCall:
    """A scripted response that calls one named tool."""

    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class Sleep:
    """A scripted response that hangs, to exercise timeouts."""

    seconds: float


class ScriptedModel(Model):
    """Answers each call with the next scripted response.

    A response is a dict (sent as a call to the structured-output tool) or a str (plain text).
    Every request is recorded so tests can inspect exactly what the model was shown.
    """

    def __init__(
        self, *responses: dict[str, Any] | str | ToolCall | Sleep, model_id: str = "scripted-model"
    ):
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.config = {"model_id": model_id}

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):  # noqa: ANN001
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(  # noqa: ANN201
        self, messages, tool_specs=None, system_prompt=None, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        self.requests.append(
            {"messages": messages, "tool_specs": tool_specs or [], "system_prompt": system_prompt}
        )
        if not self.responses:
            raise AssertionError("ScriptedModel ran out of responses")
        response = self.responses.pop(0)
        if isinstance(response, Sleep):
            await asyncio.sleep(response.seconds)
            raise AssertionError("ScriptedModel slept past its timeout")
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(response, str):
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": response}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            return
        if isinstance(response, ToolCall):
            name, payload = response.name, response.input
        else:
            name, payload = (tool_specs or [{}])[-1].get("name", "ReportDraft"), response
        yield {
            "contentBlockStart": {
                "start": {"toolUse": {"toolUseId": f"t{len(self.requests)}", "name": name}}
            }
        }
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(payload)}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}

    def prompt_text(self, call: int = 0) -> str:
        parts = []
        for m in self.requests[call]["messages"]:
            for block in m.get("content", []):
                if "text" in block:
                    parts.append(block["text"])
        return "\n".join(parts)

    def tool_results(self) -> list[str]:
        """Text of every tool result the model was shown, in order."""
        seen: list[str] = []
        for req in self.requests:
            for m in req["messages"]:
                for block in m.get("content", []):
                    for c in block.get("toolResult", {}).get("content", []):
                        if "text" in c and c["text"] not in seen:
                            seen.append(c["text"])
        return seen
