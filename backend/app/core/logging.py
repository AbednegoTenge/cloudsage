"""Logging setup with secret redaction.

Retrieved AWS data and exceptions can contain credentials; the redaction filter scrubs
common secret shapes before anything is written to logs.
"""

import logging
import re

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY_ID]"),
    (
        re.compile(
            r"(?i)(aws_secret_access_key|secretaccesskey|aws_session_token|sessiontoken"
            r"|password|authorization)([\"']?\s*[:=]\s*[\"']?)([^\s\"',}]+)"
        ),
        r"\1\2[REDACTED]",
    ),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
