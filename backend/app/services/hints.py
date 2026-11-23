"""Lightweight, deterministic hints extracted from a request before the agent runs.

These only pre-fill the investigation record (explicit vs. discovery, likely service). The agent
(Phase 5) makes the real determination and can override them. Matching is strict so arbitrary
user text never becomes an AWS identifier.
"""

import re

from app.schemas.api import ResourceRef

_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("ec2", "instance", re.compile(r"\bi-[0-9a-f]{8}(?:[0-9a-f]{9})?\b")),
    (
        "ecs",
        "service",
        re.compile(r"\barn:aws[a-z-]*:ecs:[a-z0-9-]+:\d{12}:service/[\w-]+/[\w-]+\b"),
    ),
    (
        "lambda",
        "function",
        re.compile(r"\barn:aws[a-z-]*:lambda:[a-z0-9-]+:\d{12}:function:[\w-]+\b"),
    ),
    (
        "rds",
        "db-instance",
        re.compile(r"\barn:aws[a-z-]*:rds:[a-z0-9-]+:\d{12}:db:[a-z][a-z0-9-]{0,62}\b"),
    ),
]
_NAMED: list[tuple[str, str, re.Pattern[str]]] = [
    ("lambda", "function", re.compile(r"\blambda(?: function)?\s+([A-Za-z0-9_-]{1,64})\b", re.I)),
    ("ecs", "service", re.compile(r"\becs service\s+([A-Za-z0-9_-]{1,255})\b", re.I)),
    (
        "rds",
        "db-instance",
        re.compile(r"\brds (?:instance |database )?([a-z][a-z0-9-]{0,62})\b", re.I),
    ),
]
_SERVICE_WORDS = {
    "ec2": re.compile(r"\b(ec2|instance|instances|ami)\b", re.I),
    "ecs": re.compile(r"\b(ecs|fargate|container|task definition)\b", re.I),
    "rds": re.compile(r"\b(rds|database|aurora|postgres|mysql)\b", re.I),
    "lambda": re.compile(r"\b(lambda|function)\b", re.I),
}
_STOPWORDS = {
    "is",
    "are",
    "in",
    "the",
    "that",
    "has",
    "function",
    "functions",
    "instance",
    "instances",
    "service",
}


def extract_resources(prompt: str) -> list[ResourceRef]:
    found: dict[str, ResourceRef] = {}
    for service, rtype, pat in _PATTERNS:
        for m in pat.finditer(prompt):
            found.setdefault(
                m.group(0), ResourceRef(service=service, resource_type=rtype, identifier=m.group(0))
            )
    if not found:
        for service, rtype, pat in _NAMED:
            m = pat.search(prompt)
            if m and m.group(1).lower() not in _STOPWORDS:
                found[m.group(1)] = ResourceRef(
                    service=service, resource_type=rtype, identifier=m.group(1), name=m.group(1)
                )
    return list(found.values())[:10]


def guess_services(prompt: str, resources: list[ResourceRef]) -> list[str]:
    services = [r.service for r in resources]
    for svc, pat in _SERVICE_WORDS.items():
        if svc not in services and pat.search(prompt):
            services.append(svc)
    return list(dict.fromkeys(services))


def make_title(prompt: str) -> str:
    title = " ".join(prompt.split())
    return title if len(title) <= 120 else title[:117].rstrip() + "..."
