"""Evidence-grounded report synthesis.

The model drafts a report against a strict schema. ``finalize`` then enforces, in code, what the
prompt asks for: observations must cite evidence that was actually collected, hypotheses must
rest on surviving observations, secrets are redacted, and metric and log panels are built
directly from tool output rather than from model text, so the model cannot invent them.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from strands import Agent
from strands.models.model import Model

from app.agent.model import model_id_of
from app.agent.prompts import SYSTEM_PROMPT, build_report_prompt
from app.agent.untrusted import EvidenceItem, new_nonce, sanitize_text, wrap_evidence
from app.core.logging import redact

Confidence = Literal["low", "medium", "high"]
Severity = Literal["info", "low", "medium", "high", "critical"]


# ---------- What the model must produce ----------


class DraftObservation(BaseModel):
    statement: str = Field(max_length=600, description="A fact shown directly by the evidence.")
    evidence: list[str] = Field(
        min_length=1, max_length=10, description="Evidence aliases, e.g. ['E1', 'E3']."
    )


class DraftHypothesis(BaseModel):
    title: str = Field(max_length=120)
    statement: str = Field(max_length=800, description="A possible cause. Not a fact.")
    confidence: Confidence
    likelihood: float | None = Field(default=None, ge=0, le=1)
    supporting_facts: list[str] = Field(
        min_length=1, max_length=20, description="Observation labels, e.g. ['F1', 'F2']."
    )


class DraftRecommendation(BaseModel):
    title: str = Field(max_length=160)
    detail: str = Field(max_length=1000)
    priority: Literal["now", "next", "later"]


class ReportDraft(BaseModel):
    """CloudSage investigation report."""

    summary: str = Field(max_length=1500)
    severity: Severity
    confidence: Confidence
    observations: list[DraftObservation] = Field(default_factory=list, max_length=20)
    hypotheses: list[DraftHypothesis] = Field(default_factory=list, max_length=5)
    recommendations: list[DraftRecommendation] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=10)


# ---------- Inputs and outputs ----------


@dataclass(frozen=True)
class ReportRequest:
    question: str
    account_id: str
    region: str
    time_range: str
    resources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    """A stored tool execution, as handed to the synthesizer."""

    id: str
    tool_name: str
    service: str
    status: str
    input: dict[str, Any]
    output: Any
    error: str | None = None


@dataclass
class FinalReport:
    summary: str
    severity: Severity
    confidence: Confidence
    observations: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    log_excerpts: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    limitations: list[str]
    model_id: str


class ReportGenerationError(RuntimeError):
    pass


_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_LABEL = re.compile(r"^\s*[A-Za-z]?(\d{1,3})\s*$")


def _clean(text: str, limit: int) -> str:
    return sanitize_text(redact(text).strip(), limit)


def _index(label: str) -> int | None:
    m = _LABEL.match(label)
    return int(m.group(1)) - 1 if m else None


# ---------- Deterministic evidence panels ----------


def metric_panels(evidence: list[Evidence]) -> list[dict[str, Any]]:
    """Metric series exactly as tools returned them (``kind: metric_series``)."""
    out = []
    for e in evidence:
        for item in _items(e.output):
            if item.get("kind") != "metric_series" or not isinstance(item.get("points"), list):
                continue
            points = [
                {"t": str(p["t"]), "v": float(p["v"])}
                for p in item["points"]
                if isinstance(p, dict) and "t" in p and isinstance(p.get("v"), int | float)
            ]
            panel = {
                "label": str(item.get("label", e.tool_name))[:120],
                "unit": str(item.get("unit", ""))[:32],
                "evidenceId": e.id,
                "points": points,
            }
            if isinstance(item.get("threshold"), int | float):
                panel["threshold"] = float(item["threshold"])
            out.append(panel)
    return out[:12]


def log_panels(evidence: list[Evidence], max_lines: int = 20) -> list[dict[str, Any]]:
    """Log excerpts exactly as tools returned them (``kind: log_events``), redacted."""
    out = []
    for e in evidence:
        for item in _items(e.output):
            if item.get("kind") != "log_events" or not isinstance(item.get("events"), list):
                continue
            lines = [
                sanitize_text(f"{ev.get('timestamp', '')} {ev.get('message', '')}".strip(), 500)
                for ev in item["events"][:max_lines]
                if isinstance(ev, dict)
            ]
            out.append(
                {
                    "evidenceId": e.id,
                    "logGroup": str(item.get("logGroup", ""))[:512],
                    "lines": lines,
                }
            )
    return out[:8]


def _items(output: Any) -> list[dict[str, Any]]:
    if isinstance(output, dict):
        return [output, *[v for v in output.get("panels", []) if isinstance(v, dict)]]
    if isinstance(output, list):
        return [v for v in output if isinstance(v, dict)]
    return []


# ---------- Validation ----------


def finalize(
    draft: ReportDraft, evidence: list[Evidence], aliases: dict[str, str], model_id: str
) -> FinalReport:
    """Enforce grounding rules on a model draft. ``aliases`` maps E-labels to evidence ids."""
    limitations = [_clean(x, 400) for x in draft.limitations if x.strip()]

    observations: list[dict[str, Any]] = []
    remap: dict[int, int] = {}
    dropped_obs = 0
    for i, o in enumerate(draft.observations):
        ids = list(
            dict.fromkeys(
                aliases[a.strip().upper()] for a in o.evidence if a.strip().upper() in aliases
            )
        )
        if not ids:
            dropped_obs += 1
            continue
        remap[i] = len(observations)
        observations.append({"statement": _clean(o.statement, 600), "evidenceIds": ids})
    if dropped_obs:
        limitations.append(
            f"{dropped_obs} statement(s) were removed because they did not cite collected evidence."
        )

    hypotheses: list[dict[str, Any]] = []
    dropped_hyp = 0
    for h in draft.hypotheses:
        support = sorted(
            {
                remap[j]
                for lbl in h.supporting_facts
                if (j := _index(lbl)) is not None and j in remap
            }
        )
        if not support:
            dropped_hyp += 1
            continue
        hyp: dict[str, Any] = {
            "title": _clean(h.title, 120),
            "statement": _clean(h.statement, 800),
            "confidence": h.confidence,
            "supportingObservations": support,
        }
        if h.likelihood is not None:
            hyp["score"] = round(h.likelihood, 2)
        hypotheses.append(hyp)
    if dropped_hyp:
        limitations.append(
            f"{dropped_hyp} hypothesis(es) were removed because they were not based on "
            "evidence-backed observations."
        )

    confidence: Confidence = draft.confidence
    if not evidence:
        limitations.insert(0, "No AWS evidence was collected, so no findings can be confirmed.")
        confidence = "low"
    elif not observations:
        confidence = "low"
    elif all(e.status != "succeeded" for e in evidence):
        confidence = "low"
        limitations.append("Every evidence-gathering call failed.")
    # A hypothesis cannot be more certain than the report as a whole.
    for h in hypotheses:
        if _ORDER[h["confidence"]] > _ORDER[confidence]:
            h["confidence"] = confidence

    return FinalReport(
        summary=_clean(draft.summary, 1500),
        severity=draft.severity,
        confidence=confidence,
        observations=observations,
        metrics=metric_panels(evidence),
        log_excerpts=log_panels(evidence),
        hypotheses=hypotheses,
        recommendations=[
            {
                "title": _clean(r.title, 160),
                "detail": _clean(r.detail, 1000),
                "priority": r.priority,
            }
            for r in draft.recommendations
        ],
        limitations=list(dict.fromkeys(limitations))[:12],
        model_id=model_id,
    )


# ---------- Synthesis ----------


async def synthesize_report(
    model: Model,
    request: ReportRequest,
    evidence: list[Evidence],
    *,
    timeout_seconds: float,
    max_evidence_chars: int,
) -> FinalReport:
    aliases = {f"E{i + 1}": e.id for i, e in enumerate(evidence)}
    items = [
        EvidenceItem(
            alias=f"E{i + 1}",
            tool_name=e.tool_name,
            service=e.service,
            status=e.status,
            input=e.input,
            output=e.output,
            error=e.error,
        )
        for i, e in enumerate(evidence)
    ]
    nonce = new_nonce()
    prompt = build_report_prompt(
        question=sanitize_text(request.question, 2000),
        account_id=request.account_id,
        region=request.region,
        time_range=request.time_range,
        resources=[sanitize_text(r, 256) for r in request.resources],
        nonce=nonce,
        evidence_block=wrap_evidence(items, nonce, max_evidence_chars),
    )
    # No tools: the analysis model can only read the evidence it is given.
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[], callback_handler=None)
    try:
        result = await asyncio.wait_for(
            agent.invoke_async(prompt, structured_output_model=ReportDraft),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        raise ReportGenerationError("The model did not respond in time") from None
    except Exception as e:  # noqa: BLE001 - surfaced as a redacted, user-safe error
        raise ReportGenerationError(redact(f"Report generation failed: {e}")[:500]) from e
    draft = result.structured_output
    if not isinstance(draft, ReportDraft):
        raise ReportGenerationError("The model did not return a structured report")
    return finalize(draft, evidence, aliases, model_id_of(model))
