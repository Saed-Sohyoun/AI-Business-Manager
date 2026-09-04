# Definition of Done — AI Business Operating System (Phase 21)

A change or release is **done** only when all applicable items below are true.

## Product / behavior

- [ ] No major unintended features sneaked in; scope matches the phase brief
- [ ] Agents use only explicitly registered capabilities (no unrestricted system access)
- [ ] External content remains untrusted (search/browser framing)
- [ ] Approvals cannot be bypassed (GREEN/YELLOW/RED enforced)
- [ ] **Pilot Mode** is the default (`OPERATING_MODE=pilot`); production requires `ALLOW_PRODUCTION_MODE=true`
- [ ] Pilot caps enforced: companies/audits/outreach/day, follow-ups/lead, daily spend, single expense
- [ ] Financial ceilings (`MAX_SINGLE_EXPENSE`, `DAILY_BUDGET_LIMIT`, run cost/runtime/task limits) enforced
- [ ] n8n is schedule/trigger only — business logic stays in the backend

## Quality gates (must pass locally)

```bash
# Backend
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt   # ruff, etc.
python -m pytest -q
python -m ruff check app tests scripts
python -m compileall -q app tests scripts
alembic heads   # expect single head: 0014_workflow_executions

# Frontend
cd frontend
npm ci
npm run build
```

- [ ] **Backend tests:** `pytest` green (happy paths, failures, retries, timeouts, invalid inputs, duplicates, provider outages, approval/budget/permission cases, n8n, security, Phase 21 QA)
- [ ] **Lint:** `ruff check` green on `app`, `tests`, `scripts`
- [ ] **Compile:** `compileall` green
- [ ] **Migrations:** linear Alembic chain to current head; `tests/test_migrations.py` green
- [ ] **Frontend:** `npm run build` green
- [ ] **Config:** `.env.example` documents required/optional settings; production rejects `APP_DEBUG` and CORS `*`

## Runtime smoke

- [ ] API starts without provider keys: `uvicorn app.main:app --port 8000`
- [ ] `GET /health` returns `ok` or `degraded` with `request_id`
- [ ] Process shutdown disposes DB engine cleanly (no hang)

## Security (Phase 20 bar still holds)

- [ ] Secrets not logged; `SecretStr` for keys
- [ ] n8n webhooks authenticated (+ timestamp when enabled)
- [ ] Browser SSRF controls remain on; JS default off
- [ ] See `SECURITY.md` for decisions

## Documentation

- [ ] README matches current layout (backend / frontend / n8n)
- [ ] `SECURITY.md` and this file remain accurate for the release

## Explicitly out of scope until later

- Full OAuth / multi-tenant auth for the React dashboard
- Distributed rate limiting / WAF
- Live dependency CVE CI (run `pip-audit` / `npm audit` in release process)
