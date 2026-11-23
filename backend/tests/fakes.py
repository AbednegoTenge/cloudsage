"""A scripted stand-in for Amazon Bedrock, so agent tests never call AWS."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from strands.models.model import Model


class ScriptedModel(Model):
    """Answers each call with the next scripted response.

    A response is a dict (sent as a call to the structured-output tool) or a str (plain text).
    Every request is recorded so tests can inspect exactly what the model was shown.
    """

    def __init__(self, *responses: dict[str, Any] | str, model_id: str = "scripted-model"):
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
        yield {"messageStart": {"role": "assistant"}}
        if isinstance(response, str):
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": response}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            return
        name = (tool_specs or [{}])[-1].get("name", "ReportDraft")
        yield {
            "contentBlockStart": {
                "start": {"toolUse": {"toolUseId": f"t{len(self.requests)}", "name": name}}
            }
        }
        yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(response)}}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use"}}

    def prompt_text(self, call: int = 0) -> str:
        parts = []
        for m in self.requests[call]["messages"]:
            for block in m.get("content", []):
                if "text" in block:
                    parts.append(block["text"])
        return "\n".join(parts)
