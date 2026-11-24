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
| 4 | EC2 and CloudWatch tools | **Done** (read-only EC2 and CloudWatch tools, scoped STS sessions, evidence recording, live EC2 discovery) |
| 5 | Agent orchestration, multi-step investigations, SSE | **Done** (background worker, investigator agent over the read-only tools, live progress, limits, restart recovery) |
| 6 | ECS, RDS, Lambda | **Done** (read-only ECS, RDS and Lambda tools; live discovery for all four services) |
| 7 | History/reports on real data, security hardening | Next |
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
uv sync                   # or: pip install -r requirements-dev.txt
uv run alembic upgrade head
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
uv run pytest             # integration tests skip if cloudsage_test is unreachable
uv run ruff check .
```

To run the UI against the backend, set `VITE_USE_MOCKS=false` in `frontend/.env`. In local
development the API identifies the caller with an `X-CloudSage-User` email header, falling back to
`CLOUDSAGE_DEV_DEFAULT_USER_EMAIL`. That dev mode is refused when `CLOUDSAGE_ENVIRONMENT=production`;
OIDC sign-in arrives with security hardening in Phase 7.

`requirements.txt` (runtime) and `requirements-dev.txt` (runtime plus test tools) are exported
from `uv.lock` for pip users. After changing dependencies, regenerate them:
```bash
uv export --frozen --no-hashes --no-dev --no-emit-project -o requirements.txt
uv export --frozen --no-hashes --only-group dev --no-emit-project -o requirements-dev.txt
```
then put `-r requirements.txt` back at the top of `requirements-dev.txt`.

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

New investigations start straight away in the API process. The agent gathers evidence with the
read-only tools, and progress streams over SSE. The report is then written from the recorded
evidence. Without Bedrock configured, an investigation fails at once with a message saying so.

### Amazon Bedrock
Set `CLOUDSAGE_BEDROCK_MODEL_ID` and `CLOUDSAGE_BEDROCK_REGION`, make AWS credentials available
through the usual chain (for example `aws sso login` locally, an IAM role when deployed), then
check access with `uv run python -m app.agent.check`. Tests never call Bedrock; they use a scripted
stand-in model.

### AWS tools
Investigations gather evidence with read-only tools:

| Service | Tools |
|---|---|
| EC2 | `ec2_describe_instances`, `ec2_describe_instance_status` |
| ECS | `ecs_list_services`, `ecs_describe_services`, `ecs_describe_stopped_tasks` |
| RDS | `rds_describe_db_instances`, `rds_describe_events` |
| Lambda | `lambda_list_functions`, `lambda_get_function_configuration` (never returns environment variable values) |
| CloudWatch | `cloudwatch_get_metric_data`, `cloudwatch_describe_alarms`, `logs_filter_log_events`, `logs_describe_log_groups` |
 In `CLOUDSAGE_AWS_MODE=live` each
investigation assumes the connection's role through STS and uses only those temporary
credentials. In `mock` mode the same tools read a fixed sample story (an API worker whose disk
filled up, and an ECS deployment whose tasks run out of memory), so no AWS account is needed.
Live discovery covers all four services. Lambda health is `unknown` unless the function's state
is failed or pending, because configuration says nothing about errors. Tests use moto and never
reach AWS.

The role needs only read permissions for these calls: `ec2:DescribeInstances`,
`ec2:DescribeInstanceStatus`, `ecs:ListClusters`, `ecs:ListServices`, `ecs:DescribeServices`,
`ecs:ListTasks`, `ecs:DescribeTasks`, `rds:DescribeDBInstances`, `rds:DescribeEvents`,
`lambda:ListFunctions`, `lambda:GetFunctionConfiguration`, `cloudwatch:GetMetricData`,
`cloudwatch:DescribeAlarms`, `logs:FilterLogEvents` and `logs:DescribeLogGroups`. CloudSage does not create the role.

All configuration comes from environment variables (see each `.env.example`). No AWS credentials,
account IDs, regions or Bedrock model IDs are hardcoded.

## Screenshots

See `docs/screenshots/`.
