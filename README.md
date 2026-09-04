# AI Business Operating System

Autonomous AI-powered business operating system. Specialized AI agents act as employees; the owner sets goals, permissions, and limits, then approves sensitive actions while the system handles operational work.

**Definition of Done:** see [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md).  
**Security decisions:** see [`SECURITY.md`](SECURITY.md).

## Repository layout

```
backend/     FastAPI + SQLAlchemy + Alembic application + pytest suite
frontend/    React + Vite owner dashboard (demo data; proxy to API)
n8n/         Thin schedule/trigger workflow JSON templates
prompts/     Reserved for agent prompt templates
tests/       Cross-cutting notes (automated tests live under backend/tests)
```

## Prerequisites

- Python 3.12+
- Node.js 20+ (frontend)
- PostgreSQL 15+ (production / local persistence)

Backend unit/integration tests use in-memory SQLite and do not require PostgreSQL.

## Backend quick start

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Set a real `DATABASE_URL` for local PostgreSQL. Provider keys are optional for API startup.

### Database migrations

```bash
cd backend
alembic upgrade head
```

### Run the API

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health: `http://127.0.0.1:8000/health`
- OpenAPI (non-production): `http://127.0.0.1:8000/docs`

### Tests & QA

```bash
cd backend
python -m pytest -q
python -m ruff check app tests scripts
python -m compileall -q app tests scripts
```

## Frontend

```bash
cd frontend
npm ci
npm run dev      # http://127.0.0.1:5173 (proxies /api and /health)
npm run build
```

## Architecture (Phases 0–21)

- **Config:** Pydantic Settings — app, DB, CORS, safety limits, providers, n8n, owner key
- **Persistence:** SQLAlchemy 2 models + Alembic migrations through `0014_workflow_executions`
- **API:** FastAPI `/health`, request IDs, structured errors, rate limits, n8n webhooks
- **Providers:** AI (OpenAI), Search (Tavily), Browser (Playwright), Email (Resend), Telegram — adapters only
- **Agents:** Research, Scoring, Audit, Sales, Delivery, Finance, Report; **Manager** orchestrates with limits
- **Approvals:** GREEN auto / YELLOW human-then-execute / RED human-only — no agent bypass
- **Finance:** Decimal ledger; single-expense + daily budget ceilings
- **n8n:** authenticated webhooks with idempotency, retries, soft-timeout success retention, stale RUNNING reclaim
- **Dashboard:** React demo UI for oversight (not authoritative; no approve-by-name without owner key)

## Safety limits

Enforced via settings + Manager / Finance / Email / Notification services:

- Runtime, retries, tasks/run, AI cost/run
- Daily budget + max single expense
- Outbound message + follow-up caps
- Approval required for external actions

## Intentionally not included

- Mass email / blast campaigns
- Sales auto-send without approval
- Autonomous payments / voice
- Full OAuth / multi-tenancy for the dashboard
- Distributed rate limiting / WAF
