"""Runs tools for an investigation and records every call as evidence.

For each call the runner:

1. enforces the per-investigation tool-call limit;
2. validates the input against the tool's schema (unknown fields rejected);
3. runs the tool in a worker thread with a timeout, inside the scoped ``AwsContext``;
4. redacts secrets and caps the size of the output;
5. writes a ``ToolExecution`` row (input, output or error, status, duration) plus timeline
   events. Rows are never edited afterwards.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.aws.context import AwsContext, BoundaryViolation
from app.aws.session import client_error_message
from app.core.config import Settings
from app.core.logging import redact
from app.models import Investigation, ToolExecution, ToolExecutionStatus
from app.repositories.investigations import InvestigationRepository
from app.tools.base import ToolError, get_tool


class ToolLimitReached(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolResult:
    execution_id: str
    tool_name: str
    ok: bool
    output: Any
    error: str | None


def redact_json(value: Any, max_chars: int) -> Any:
    """Redact secrets anywhere in a JSON value and cap its serialised size."""
    text = redact(json.dumps(value, default=str, ensure_ascii=False))
    if len(text) > max_chars:
        return {"truncated": True, "originalChars": len(text), "preview": text[:max_chars]}
    return json.loads(text)


def _validation_message(e: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(x) for x in err['loc']) or 'input'}: {err['msg']}" for err in e.errors()
    ]
    return redact("Invalid input: " + "; ".join(parts))[:500]


class ToolRunner:
    def __init__(
        self,
        db: AsyncSession,
        repo: InvestigationRepository,
        inv: Investigation,
        ctx: AwsContext,
        settings: Settings,
        *,
        max_calls: int | None = None,
    ) -> None:
        self.db, self.repo, self.inv, self.ctx, self.settings = db, repo, inv, ctx, settings
        self.max_calls = max_calls or settings.investigation_max_tool_calls
        self.calls = 0

    async def run(self, tool_name: str, raw_input: dict[str, Any] | None) -> ToolResult:
        if self.calls >= self.max_calls:
            raise ToolLimitReached(f"Tool call limit of {self.max_calls} reached")
        self.calls += 1
        raw_input = raw_input or {}
        safe_input = redact_json(raw_input, 4000)
        try:
            spec = get_tool(tool_name)
            service = spec.service
        except ToolError as e:
            return await self._record(tool_name, "unknown", safe_input, None, str(e), 0)

        started = time.monotonic()
        try:
            inp = spec.input_model.model_validate(raw_input)
            safe_input = redact_json(inp.model_dump(mode="json", exclude_none=True), 4000)
            output = await asyncio.wait_for(
                asyncio.to_thread(spec.run, self.ctx, inp),
                timeout=self.settings.tool_timeout_seconds,
            )
        except ValidationError as e:
            error = _validation_message(e)
        except (BoundaryViolation, ToolError) as e:
            error = redact(str(e))[:500]
        except TimeoutError:
            error = f"Timed out after {self.settings.tool_timeout_seconds} s"
        except (ClientError, BotoCoreError) as e:
            error = client_error_message(e)
        except Exception as e:  # noqa: BLE001 - recorded as a failed call, never raised raw
            error = redact(f"{type(e).__name__}: {e}")[:500]
        else:
            ms = int((time.monotonic() - started) * 1000)
            out = redact_json(output, self.settings.tool_max_output_chars)
            return await self._record(spec.name, service, safe_input, out, None, ms)
        ms = int((time.monotonic() - started) * 1000)
        return await self._record(spec.name, service, safe_input, None, error, ms)

    async def _record(
        self,
        name: str,
        service: str,
        inp: Any,
        output: Any,
        error: str | None,
        duration_ms: int,
    ) -> ToolResult:
        row = ToolExecution(
            investigation_id=self.inv.id,
            tool_name=name[:100],
            service=service[:32],
            input=inp if isinstance(inp, dict) else {"value": inp},
            output=output,
            status=ToolExecutionStatus.FAILED if error else ToolExecutionStatus.SUCCEEDED,
            error=error,
            duration_ms=duration_ms,
        )
        self.db.add(row)
        await self.db.flush()
        if error:
            await self.repo.add_event(
                self.inv, "tool_failed", f"{name} failed: {error}"[:500], tool_execution=row
            )
        else:
            await self.repo.add_event(
                self.inv,
                "tool_completed",
                f"{name} completed in {duration_ms} ms",
                tool_execution=row,
            )
        return ToolResult(str(row.id), name, error is None, output, error)
