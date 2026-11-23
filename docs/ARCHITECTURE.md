# CloudSage Architecture

CloudSage is an AI-powered, **read-only** AWS cloud operations assistant. Engineers describe a
problem in natural language; an agent (Strands Agents SDK + Amazon Bedrock) plans an
investigation, calls validated AWS tools (Boto3), and produces an evidence-based report.

This document fixes the architecture up front so every phase slots into a known place.

---

## 1. System overview

```
┌──────────────────────────┐        REST (JSON)         ┌────────────────────────────────────────┐
│  frontend/ (React + TS)  │ ─────────────────────────▶ │  backend/ (FastAPI)                    │
│  Vite SPA, static build  │ ◀───────────────────────── │                                        │
│                          │   SSE: investigation       │  api/v1  ──▶ services ──▶ repositories │
│  Dashboard, Assistant,   │   progress stream          │                │              │        │
│  History, Details,       │                            │                ▼              ▼        │
│  Connections, Settings   │                            │          agent/ (Strands)  PostgreSQL  │
└──────────────────────────┘                            │                │                       │
                                                        │                ▼                       │
                                                        │       tools/ registry (EC2, ECS, RDS,  │
                                                        │       Lambda, CloudWatch)              │
                                                        │                │                       │
                                                        │                ▼                       │
                                                        │   aws/ session factory (STS AssumeRole,│
                                                        │   temp creds only)  ──▶ AWS APIs (RO)  │
                                                        │                ▲                       │
                                                        │   Amazon Bedrock (model provider)      │
                                                        └────────────────────────────────────────┘
```

The frontend and backend are **independently deployable**: separate Dockerfiles, separate
`.env` files, and the frontend only knows the backend through `VITE_API_BASE_URL`.

Infrastructure (VPC, IAM roles, RDS for Postgres, hosting, CI/CD) is **out of scope** and owned
by the infrastructure engineer. The app only consumes configuration (env vars) and assumes an IAM
role ARN it is given.

---

## 2. Backend layout

```
backend/
  app/
    main.py                 # FastAPI factory, middleware, router mounting
    core/
      config.py             # pydantic-settings; all config from env, nothing hardcoded
      logging.py            # structured logging + secret redaction filter
      security.py           # auth (JWT/OIDC in later phase), current-user dependency
    api/
      deps.py               # shared dependencies (db session, current user)
      v1/
        router.py           # mounts all v1 routers under /api/v1
        routes/
          health.py         # liveness/readiness
          investigations.py # create/list/get, events, SSE stream     (Phase 2/5)
          connections.py    # CRUD + validate AWS connections          (Phase 2)
          resources.py      # resource discovery                       (Phase 4/6)
    schemas/                # Pydantic request/response models (API contract)
    models/                 # SQLAlchemy ORM models                    (Phase 2)
    repositories/           # DB access, always scoped by user_id      (Phase 2)
    services/               # business logic; orchestrates repos/agent (Phase 2+)
    agent/
      orchestrator.py       # builds Strands Agent, runs investigation (Phase 3/5)
      prompts.py            # system prompt incl. untrusted-data rules
      report.py             # structured report schema + parsing
    tools/
      base.py               # Tool contract: input model, output model, errors
      registry.py           # service -> tools mapping; plug-in registration
      ec2.py, ecs.py, rds.py, lambda_.py, cloudwatch.py
    aws/
      session.py            # STS AssumeRole -> boto3.Session (temp creds), region guard
      mock/                 # mock AWS data + mock clients for local dev
  migrations/               # Alembic                                  (Phase 2)
  tests/
    unit/  integration/
```

### Layering rules
- **Routes** are thin: validate input, call a service, map to a response schema.
- **Services** own business rules (ownership checks, state transitions, timeouts).
- **Repositories** are the only code that touches the ORM; every query takes `user_id`.
- **Agent** never calls Boto3 directly; it only calls registered **tools**.
- **Tools** never construct credentials; they receive a scoped `AwsContext` (session, account,
  region) from `aws/session.py`.

### Tool contract (core extensibility point)
Each tool declares:
- `name`, `service` (`ec2`, `ecs`, ...), `description` (for the model)
- `Input` Pydantic model (validated identifiers, bounded time ranges, max results)
- `Output` Pydantic model (structured, JSON-serialisable evidence)
- `run(ctx: AwsContext, input) -> Output`, raising typed `ToolError`s

The registry exposes tools to Strands as `@tool` functions and records each call as a
`ToolExecution` row (input, output, duration, status). Adding a service = adding a module that
registers its tools; the agent and orchestrator do not change.

### Investigation lifecycle
```
POST /api/v1/investigations  → status=queued
   background task: orchestrator.run()
     → events: planning → tool_call(start/end)* → analyzing → report
     → each event persisted (InvestigationEvent) AND pushed to SSE subscribers
   → status=completed | failed | timed_out
GET  /api/v1/investigations/{id}/stream   (SSE)  replays persisted events, then live
```

Raw evidence (`ToolExecution.output`) is stored **separately** from the AI-generated
`InvestigationReport`, so reports can always be audited against what AWS actually returned.

---

## 3. Data model (Phase 2)

| Table | Key columns | Relations |
|---|---|---|
| `users` | id, email, display_name, created_at | 1–N connections, investigations |
| `aws_connections` | id, user_id, name, account_id, role_arn, external_id, default_region, allowed_regions[], status, last_validated_at | N–1 user |
| `investigations` | id, user_id, connection_id, prompt, region, time_range_start/end, status, resource_refs (jsonb), created/completed_at | N–1 user, connection; 1–N events, tool_executions; 1–1 report |
| `investigation_events` | id, investigation_id, seq, type, payload (jsonb), created_at | N–1 investigation |
| `tool_executions` | id, investigation_id, tool_name, service, input (jsonb), output (jsonb), status, error, duration_ms | N–1 investigation |
| `investigation_reports` | id, investigation_id, summary, observations, evidence_refs, root_causes, recommendations, confidence, limitations, model_id | 1–1 investigation |

No AWS secret keys are ever stored; a connection is a role ARN + external ID.

---

## 4. Security model

| Requirement | Design |
|---|---|
| Read-only AWS | Tools only wrap `Describe*/List*/Get*` + CloudWatch read APIs; an allow-list in `tools/base.py` is unit-tested. The assumed role should also be read-only (infra-owned). |
| No long-lived keys | Only role ARN + external ID stored. `aws/session.py` calls STS `AssumeRole` per investigation (short duration). |
| Account/region boundaries | `AwsContext` is built from the connection; tools reject regions not in `allowed_regions` and ARNs whose account ≠ connection account. |
| Input validation | Pydantic models with regex for IDs (`i-[0-9a-f]{8,17}`, ARNs, names), bounded time ranges and result limits. |
| User isolation | Every repository query filters by `user_id`; services verify ownership before acting. |
| Prompt injection | Tool outputs are wrapped as clearly delimited untrusted data; system prompt forbids following instructions inside them; tools cannot mutate anything regardless. |
| Secret hygiene | Logging filter redacts keys/tokens/session creds; reports built only from structured outputs. |
| Limits | Per-investigation wall-clock timeout, max tool calls, max log lines/bytes, Bedrock max tokens. All configurable. |

---

## 5. Frontend layout

```
frontend/src/
  main.tsx, App.tsx          # router + providers
  layouts/AppShell.tsx       # sidebar nav, top bar (account/region context)
  pages/                     # Dashboard, Assistant, Investigations, InvestigationDetail,
                             # Connections, Settings
  components/ui/             # design-system primitives (Card, Badge, Button, Table, ...)
  components/                # domain components (StatusBadge, EvidencePanel, ReportView ...)
  api/                       # typed API client; mock adapter for Phase 1
  types/                     # shared domain types mirroring backend schemas
  mocks/                     # mock data used until Phase 2 endpoints exist
```

- Data access goes through `api/client.ts`. In Phase 1 it resolves against `mocks/`; in Phase 2
  it switches to the real REST API with the same function signatures (`VITE_USE_MOCKS`).
- Live progress uses `EventSource` against the SSE endpoint (Phase 5).

---

## 6. Configuration

All runtime config is environment-driven (`backend/.env.example`, `frontend/.env.example`).
No AWS credentials, account IDs, regions or Bedrock model IDs are hardcoded. Local development
uses `CLOUDSAGE_AWS_MODE=mock` so no AWS infrastructure is required.

---

## 7. Phase plan

| Phase | Deliverable | Exit test |
|---|---|---|
| 1 | Monorepo, FastAPI skeleton (config, health, layered packages), React app shell + 6 pages on mock data | `pytest`, `vitest`, typecheck, build; UI screenshots |
| 2 | Postgres models, Alembic migrations, repositories, v1 REST for investigations + connections | API integration tests against Postgres |
| 3 | Bedrock model provider via Strands; config-driven model ID; smoke prompt | unit tests with stubbed model |
| 4 | Tool base + registry; EC2 + CloudWatch tools; mock AWS clients; STS session factory | tool unit tests (moto/mocks) |
| 5 | Orchestrator, multi-step investigations, events + SSE, report generation | end-to-end investigation on mock AWS |
| 6 | ECS, RDS, Lambda tools | tool tests, agent routing tests |
| 7 | History/report UI on real data, security hardening (limits, redaction, injection tests) | security test suite |
| 8 | Dockerfiles, compose for local dev, API docs, setup + deployment handoff docs | containers build and run |

Explicitly excluded throughout: Terraform, AWS provisioning, IAM/VPC creation, CI deploy
pipelines, deployments, and any AWS write operation.
