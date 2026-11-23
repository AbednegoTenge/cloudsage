"""Preparing retrieved AWS data for the model.

Everything an AWS API returns (log lines, tags, descriptions, error messages) may have been
written by someone other than the user, so it is treated as untrusted:

1. Secrets are redacted before the model (or a log) ever sees them.
2. Control characters are removed and the size is capped.
3. The data is wrapped in a boundary tag carrying a per-call random nonce. Anything inside that
   looks like our boundary is neutralised, so retrieved text cannot "close" the block and
   continue as instructions.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

from app.core.logging import redact

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_BOUNDARY_LIKE = re.compile(r"</?\s*untrusted[_-]?data[^>]*>", re.IGNORECASE)


def new_nonce() -> str:
    return secrets.token_hex(8)


def sanitize_text(text: str, max_chars: int) -> str:
    text = _CONTROL.sub("", redact(text))
    text = _BOUNDARY_LIKE.sub("[removed-tag]", text)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n[truncated {len(text) - max_chars} characters]"
    return text


def to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, ensure_ascii=False, indent=1, sort_keys=True)


@dataclass(frozen=True)
class EvidenceItem:
    """One piece of evidence as the model sees it, with a short alias such as ``E1``."""

    alias: str
    tool_name: str
    service: str
    status: str
    input: dict[str, Any]
    output: Any
    error: str | None = None


def wrap_evidence(items: list[EvidenceItem], nonce: str, max_chars: int) -> str:
    """Render evidence inside nonce-tagged untrusted blocks."""
    if not items:
        return f'<untrusted_data nonce="{nonce}">\n(no evidence was collected)\n</untrusted_data>'
    blocks = []
    for e in items:
        body = to_text(e.output) if e.error is None else f"ERROR: {e.error}"
        blocks.append(
            f'<untrusted_data nonce="{nonce}" evidence="{e.alias}">\n'
            f"tool: {e.tool_name}\nservice: {e.service}\nstatus: {e.status}\n"
            f"input: {sanitize_text(to_text(e.input), 2000)}\n"
            f"output:\n{sanitize_text(body, max_chars)}\n"
            f"</untrusted_data>"
        )
    return "\n\n".join(blocks)
