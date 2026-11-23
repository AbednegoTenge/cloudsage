"""Check that Amazon Bedrock is reachable with the configured model.

    uv run python -m app.agent.check

Sends one small, synthetic evidence item (no AWS account data) and prints the validated report.
Uses the standard AWS credential chain; nothing is stored.
"""

from __future__ import annotations

import asyncio
import sys

from app.agent.model import ModelNotConfigured, build_model
from app.agent.report import Evidence, ReportGenerationError, ReportRequest, synthesize_report
from app.core.config import get_settings

SAMPLE = Evidence(
    id="sample-1",
    tool_name="sample_metric",
    service="cloudwatch",
    status="succeeded",
    input={"metric": "CPUUtilization", "resource": "i-0123456789abcdef0"},
    output={
        "kind": "metric_series",
        "label": "CPUUtilization",
        "unit": "Percent",
        "points": [
            {"t": f"2026-01-01T00:{m:02d}:00Z", "v": v}
            for m, v in [(0, 12.0), (5, 14.0), (10, 97.5), (15, 98.9)]
        ],
    },
)


async def main() -> int:
    settings = get_settings()
    try:
        model = build_model(settings)
    except ModelNotConfigured as e:
        print(e, file=sys.stderr)
        return 2
    try:
        report = await synthesize_report(
            model,
            ReportRequest(
                question="Why did CPU spike on this synthetic instance?",
                account_id="000000000000",
                region=settings.bedrock_region or "",
                time_range="synthetic sample",
                resources=["i-0123456789abcdef0"],
            ),
            [SAMPLE],
            timeout_seconds=settings.bedrock_timeout_seconds,
            max_evidence_chars=settings.agent_max_evidence_chars,
        )
    except ReportGenerationError as e:
        print(f"Bedrock check failed: {e}", file=sys.stderr)
        return 1
    print(f"Bedrock OK ({report.model_id}). Confidence: {report.confidence}")
    print(f"Summary: {report.summary}")
    for o in report.observations:
        print(f"  fact: {o['statement']}")
    for h in report.hypotheses:
        print(f"  hypothesis ({h['confidence']}): {h['statement']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
