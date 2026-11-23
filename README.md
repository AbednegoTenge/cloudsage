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
| 1 | Application foundation and UI | **Done** (UI runs on mock data) |
| 2 | Backend API and PostgreSQL | Next |
| 3 | Amazon Bedrock integration | Planned |
| 4 | EC2 and CloudWatch tools | Planned |
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

### Backend
```bash
cd backend
cp .env.example .env      # CLOUDSAGE_AWS_MODE=mock needs no AWS account
uv sync
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
uv run pytest
uv run ruff check .
```

All configuration comes from environment variables (see each `.env.example`). No AWS credentials,
account IDs, regions or Bedrock model IDs are hardcoded.

## Screenshots

See `docs/screenshots/`.
