# CloudSage

AI-powered, **read-only** AWS cloud operations assistant. Engineers describe a problem in natural
language; an agent (Strands Agents SDK + Amazon Bedrock) identifies the AWS resources, gathers
evidence through validated Boto3 tools, and produces an evidence-based investigation report.

- `frontend/`: React + TypeScript (Vite) SPA
- `backend/`: Python + FastAPI API
- `docs/ARCHITECTURE.md`: architecture, data model, security model and phase plan

Frontend and backend are independently deployable. Infrastructure (AWS accounts, IAM roles,
networking, hosting, CI/CD) is owned by the infrastructure engineer and is out of scope here.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Application foundation and UI | **Done** (7 pages on mock data: Overview, AI Assistant, Investigations, Investigation report, Infrastructure, AWS Connections, Settings) |
| 2 | Backend API and PostgreSQL | **Done** (models, migrations, versioned REST API, SSE, per-user isolation; UI wired to the API) |
| 3 | Amazon Bedrock integration | **Done** (Strands + Bedrock model from settings, injection-resistant evidence handling, evidence-cited report synthesis) |
| 4 | EC2 and CloudWatch tools | Next |
| 5 | Agent orchestration, multi-step investigations, SSE | Planned |
| 6 | ECS, RDS, Lambda | Planned |
| 7 | History/reports on real data, security hardening | Planned |
| 8 | Testing, Docker, deployment documentation | Planned |

## Local development

Requirements: Node 20+, Python 3.11+, [uv](https://docs.astral.sh/uv/).

### Frontend
```bash
cd frontend
cp .env.example .env      # VITE_USE_MOCKS=true runs the UI without the backend
npm install
npm run dev               # http://localhost:5173
npm test                  # Vitest
npm run typecheck
npm run build
```

### Database
PostgreSQL 14+ with two databases, one for development and one for tests (the test suite
truncates it on every run):
```bash
createuser --createdb cloudsage --pwprompt     # password: cloudsage (matches .env.example)
createdb -O cloudsage cloudsage
createdb -O cloudsage cloudsage_test
```

### Backend
```bash
cd backend
cp .env.example .env      # CLOUDSAGE_AWS_MODE=mock needs no AWS account
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
uv run pytest             # integration tests skip if cloudsage_test is unreachable
uv run ruff check .
```

To run the UI against the backend, set `VITE_USE_MOCKS=false` in `frontend/.env`. In local
development the API identifies the caller with an `X-CloudSage-User` email header, falling back to
`CLOUDSAGE_DEV_DEFAULT_USER_EMAIL`. That dev mode is refused when `CLOUDSAGE_ENVIRONMENT=production`;
OIDC sign-in arrives with security hardening in Phase 7.

### API (v1)
| Method | Path | Purpose |
|---|---|---|
| POST / GET | `/api/v1/investigations` | Queue an investigation; list with `status`, `connectionId`, `search`, `limit`, `offset` |
| GET | `/api/v1/investigations/{id}` | Investigation, events, raw tool evidence and (separately) the report |
| GET | `/api/v1/investigations/{id}/events?after=N` | Events after sequence N |
| GET | `/api/v1/investigations/{id}/stream` | Server-Sent Events; resumes from `Last-Event-ID` |
| GET / POST | `/api/v1/connections` | List or register an IAM role connection |
| GET / PUT / DELETE | `/api/v1/connections/{id}` | Read, update, soft-delete |
| POST | `/api/v1/connections/{id}/validate` | STS AssumeRole check (no AWS call in mock mode) |
| GET | `/api/v1/resources` | Resource discovery within each connection's allowed regions |
| GET | `/api/v1/dashboard` | Overview aggregates |
| GET / PUT | `/api/v1/settings` | Per-user preferences |

Investigations stay `queued` until the agent runs them (Phase 5).

### Amazon Bedrock
Set `CLOUDSAGE_BEDROCK_MODEL_ID` and `CLOUDSAGE_BEDROCK_REGION`, make AWS credentials available
through the usual chain (for example `aws sso login` locally, an IAM role when deployed), then
check access with `uv run python -m app.agent.check`. Tests never call Bedrock; they use a scripted
stand-in model. Live resource discovery
returns 501 until the AWS tools land in Phase 4; mock mode serves sample resources.

All configuration comes from environment variables (see each `.env.example`). No AWS credentials,
account IDs, regions or Bedrock model IDs are hardcoded.

## Screenshots

See `docs/screenshots/`.
