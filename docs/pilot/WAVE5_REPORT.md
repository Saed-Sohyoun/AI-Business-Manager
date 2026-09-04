# Wave 5 — Controlled Pilot Readiness Report

**Date:** 2026-09-04  
**Overall recommendation:** **NO-GO** for controlled pilot launch  
**Production:** LOCKED (`ALLOW_PRODUCTION_MODE` default false)  
**Operating mode:** Pilot (highest allowed)

---

## A. Readiness status

`GET /api/v1/owner/readiness` evaluates to **NOT_READY** in this environment.

Hard blockers present:
- Application database is not PostgreSQL (workspace uses SQLite for local/tests)
- `POSTGRES_TEST_URL` unset → concurrency suite skipped (treated as BLOCKED, not PASS)
- `POSTGRES_CONCURRENCY_PASS` unset → readiness fail
- `BACKUP_RESTORE_PASS` unset → readiness fail
- Provider smoke: all providers SKIP (keys not configured / not exercised live)
- Real research / niche experiment / test-inbox send / real outreach: **not executed** (gates not met)

---

## B. Postgres concurrency results

**BLOCKED — not PASS.**

| Check | Result |
|-------|--------|
| Suite present (`test_wave5_postgres_concurrency.py`) | Yes — approve/approve, approve/reject, command idempotency, execution cancel race, webhook nonce race, system_control singleton, duplicate outbound |
| Executed against real Postgres | **No** — `POSTGRES_TEST_URL` missing; Docker/psql not available on this machine |
| Wave 4 optional suite | Also skipped without URL |

Per Wave 5 rules: skipped concurrency **must not** be marked PASS.

---

## C. Migration results

| Check | Result |
|-------|--------|
| Alembic head | `0018_wave5_pilot_experiment` |
| SQLite structural / head tests | PASS (`test_migrations.py`) |
| Clean Postgres base→head→downgrade→upgrade | **BLOCKED** (`validate_migrations_postgres.py` exit reason: `POSTGRES_TEST_URL` unset) |

---

## D. Backup / restore result

| Check | Result |
|-------|--------|
| Procedure documented | `docs/pilot/BACKUP_RESTORE.md` |
| Script | `backend/scripts/backup_restore_restore_validate.py` / `backup_restore_validate.py` |
| Test restore performed | **BLOCKED** — requires `POSTGRES_TEST_URL` |

---

## E. Environment validation

| Item | Status |
|------|--------|
| Pilot limits ≤ envelope (20/10/5/2/€3/€20) | PASS (defaults unchanged; readiness enforces) |
| Production locked | PASS |
| Budget warnings 70% / 90% / 100% hard stop | Implemented (`budget_warning_ratio=0.70`, `budget_urgent_ratio=0.90`) |
| Session cookie secure in production | Validated by readiness when `APP_ENV=production` |
| Wildcard CORS | Fail-closed in production settings / readiness |
| Demo vs pilot | Readiness requires Postgres + gates; demo UI separate |
| `VITE_OWNER_API_KEY` as primary auth | Not required; session preferred |

---

## F. Secret scan result

| Category | Result | File category (when FOUND) | Severity |
|----------|--------|----------------------------|----------|
| openai_key | NOT_FOUND | — | — |
| aws_key | NOT_FOUND | — | — |
| private_key_block | NOT_FOUND | — | — |
| generic_api_key_assignment | NOT_FOUND | — | — |
| bearer_token | NOT_FOUND | (fixture allowlisted after review) | — |
| Dist scanned | yes | frontend build | — |
| `VITE_OWNER_API_KEY` in dist | FOUND as UI/code identifier only (no secret value) | frontend_build | INFO |

No live secrets printed.

---

## G. Provider smoke results

| Provider | Configured | Reachable | Latency | Health | Notes |
|----------|------------|-----------|---------|--------|-------|
| AI (OpenAI) | SKIP | — | — | — | Not configured / not smoked |
| Search (Tavily) | SKIP | — | — | — | Not configured / not smoked |
| Browser | SKIP | — | — | — | Script skips unless explicitly enabled |
| Email | SKIP | — | — | — | No cold outreach; needs `OWNER_TEST_INBOX` for safe send |
| Telegram | SKIP | — | — | — | Not configured / not smoked |

Script: `backend/scripts/provider_smoke.py`

---

## H. n8n validation

| Check | Result |
|-------|--------|
| Workflow JSON includes timestamp, nonce, signature headers | Yes (Wave 4 + README) |
| HMAC unit/replay tests (backend) | PASS (`test_n8n_webhook_hmac.py`) |
| Live Code-node HMAC in deployed n8n | **Not verified** — placeholder env still required per `n8n/README.md` Wave 5 gate |
| Deployed workflow end-to-end against this env | NOT RUN |

---

## I. Budget / quota validation

| Check | Result |
|-------|--------|
| Daily budget hard stop | Existing `assert_daily_budget` |
| 70% / 90% OwnerAlert warnings (deduped) | Implemented |
| Pilot day caps | Unchanged; not raised |
| Postgres-safe quota counters | Code paths use DB; **concurrency not proven on Postgres here** |

---

## J. Kill switch drill

Automated in `test_wave5_readiness.py` (SQLite): Pause All → AI/outbound/spending blocked; status paused.  
**Staging drill on Postgres:** NOT RUN (environment blocker).

---

## K. Safe Mode drill

Automated in Wave 5 readiness tests: enter Safe Mode → outbound/spending blocked; owner can clear; agents cannot.  
**Staging on Postgres:** NOT RUN.

---

## L. Provider outage drill

Circuit breaker unit coverage + Wave 4/5 tests for `CIRCUIT_OPEN`.  
Full “search 503 mid-execution” staging drill: NOT RUN (no live providers / no Postgres pilot stack).

---

## M. Selected niche

**None selected / none owner-approved.**  
API exists to draft + approve niche; no automatic niche activation without owner approval.

---

## N. Experiment configuration

Model + migration `0018` + owner APIs present.  
**No live experiment started** (launch gate failed).

Suggested template (for when gates pass) — **not activated**:
- Niche: owner-approved only (e.g. local cleaning services — recommendation only)
- Geography: single city
- Caps: within daily pilot limits; lifecycle target ≤100 discoveries
- Evaluation targets only: 30 qualified / 15 contact-consideration / 5 replies / 2 calls / 1 customer (not guarantees)

---

## O–U. Research / qualification / audits / drafts / outreach

| Item | Result |
|------|--------|
| O Research | NOT RUN |
| P Qualification | NOT RUN |
| Q Audits | NOT RUN |
| R Draft outreach count | 0 (not run) |
| S Test inbox send | NOT RUN / BLOCKED |
| T Real outreach | **None** (correct under NO-GO) |
| U Replies | N/A |

---

## V. Spend

€0 attributed to Wave 5 live pilot work (no paid provider smoke executed).

---

## W. Security / governance events

No SEV-1/2 incidents during Wave 5 tooling work.  
Governance controls remain intact (contracts, ToolGateway, approvals, Safe Mode, pilot limits, production lock).

---

## X. Remaining risks / production-readiness blockers

1. **CRITICAL for pilot:** No Postgres concurrency PASS in this environment  
2. **CRITICAL:** No backup/restore proof  
3. **HIGH:** No Postgres migration upgrade/downgrade proof  
4. **HIGH:** Provider smoke not executed  
5. **HIGH:** Test-inbox send pipeline not proven  
6. **MEDIUM:** n8n live HMAC still env/placeholder until Code-node wired in deploy  
7. Unrestricted production unlock still correctly deferred  

---

## Y. GO / NO-GO

# **NO-GO**

**Recommendation:** NOT ready for controlled real-world pilot.

**READY FOR CONTROLLED PILOT** only after owner provides a disposable `POSTGRES_TEST_URL`, and these all PASS without skip:
1. Wave 5 Postgres concurrency suite  
2. Postgres migrations validate script  
3. Backup/restore validate script → set `BACKUP_RESTORE_PASS=true`  
4. Set `POSTGRES_CONCURRENCY_PASS=true` only after (1)  
5. Provider smoke (at least AI + Search; email config or test inbox)  
6. Test inbox full send pipeline  
7. Owner approves niche + explicitly approves pilot start  
8. `GET /owner/readiness` → `READY_FOR_PILOT`

Production remains **LOCKED**. Limits **not raised**. Unrestricted outreach **not enabled**.

---

## Artifacts added this wave

- Postgres concurrency suite expansion  
- Readiness API + UI badge  
- Pilot experiment model/API  
- Budget 70/90 warnings  
- Scripts: secret_scan, provider_smoke, backup_restore_validate, validate_migrations_postgres  
- Docs: `docs/pilot/*`  
- Frontend readiness helpers + tests  

**STOP.** Awaiting explicit owner approval for next steps (e.g. provisioning Postgres test DB).
