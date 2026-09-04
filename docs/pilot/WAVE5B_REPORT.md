# Wave 5B — Environment Validation Report

**Date:** 2026-09-04  
**Scope:** Execute blocked readiness gates only (no product features, no outreach, no niche experiment)  
**Final recommendation:** **NO-GO**

Production remains **LOCKED**. Pilot limits **unchanged**. No prospect outreach. No niche experiment started.

---

## A. Environment used

| Item | Value |
|------|--------|
| Host OS | Windows 10/11 (local workspace) |
| App `DATABASE_URL` scheme | `sqlite+pysqlite` (not Postgres) |
| `POSTGRES_TEST_URL` | **UNSET** |
| Docker / Podman | Not installed |
| WSL | Not installed |
| `psql` / `pg_dump` / `pg_restore` | Not on PATH |
| TCP `127.0.0.1:5432` | Closed |
| Disposable Postgres | **Not available** |

Provider credentials in environment:

| Variable | Present |
|----------|---------|
| `OPENAI_API_KEY` | No |
| `TAVILY_API_KEY` | No |
| `RESEND_API_KEY` | No |
| `OWNER_TEST_INBOX` | No |
| `TELEGRAM_BOT_TOKEN` | No |
| `N8N_WEBHOOK_SECRET` | No |
| `OWNER_API_KEY` | No |

---

## B. PostgreSQL version

**N/A** — no Postgres instance reachable. Version could not be queried.

---

## C–D. Postgres concurrency results

**GATE = FAIL** (not PASS; skipped runs are not accepted as PASS).

Command:

```text
pytest tests/test_wave5_postgres_concurrency.py tests/test_wave4_postgres_concurrency.py
```

| Suite | Outcome |
|-------|---------|
| Wave 5 concurrency (7 tests) | **SKIPPED** — `POSTGRES_TEST_URL` required |
| Wave 4 concurrency (1 test) | **SKIPPED** — same |

**Exact counts:** 0 passed · 0 failed · **8 skipped**

`POSTGRES_CONCURRENCY_PASS` was **not** set to `true` (no evidence).

Required races (approve/approve, approve/reject, idempotency, execution transition, webhook nonce, system_control singleton, duplicate outbound, quota/budget concurrency) were **not executed**.

---

## E. Migration validation result

**GATE = FAIL / BLOCKED**

```text
python scripts/validate_migrations_postgres.py
→ MIGRATIONS_POSTGRES=BLOCKED
→ REASON=POSTGRES_TEST_URL unset
```

Could not validate base→head, downgrade, or revisions 0015–0018 on Postgres.

SQLite Alembic head checks from Wave 5 remain green in unit tests but **do not satisfy** this Wave 5B Postgres gate.

---

## F. Backup / restore result

**GATE = FAIL / BLOCKED**

```text
python scripts/backup_restore_validate.py
→ BACKUP_RESTORE=BLOCKED
→ REASON=POSTGRES_TEST_URL unset
```

(Also: `pg_dump`/`pg_restore` absent from PATH.)

`BACKUP_RESTORE_PASS` was **not** set to `true`.

No representative seed → dump → restore → integrity verification performed.

---

## G. Provider smoke results

```text
python scripts/provider_smoke.py
```

| Provider | Result |
|----------|--------|
| AI (OpenAI) | **NOT_CONFIGURED** (SKIP) |
| Search (Tavily) | **NOT_CONFIGURED** (SKIP) |
| Browser | **NOT_CONFIGURED** / not smoked |
| Notification (Telegram) | **NOT_CONFIGURED** (SKIP) |
| Email (Resend) | **NOT_CONFIGURED** (SKIP) |

Essential research providers did **not** PASS.

---

## H. Test inbox send result

**GATE = FAIL / NOT RUN**

Missing: `RESEND_API_KEY`, `OWNER_TEST_INBOX`, Postgres-backed app stack for governed send path.

No draft → approval → fingerprint → queue → SENT exercise.

---

## I. Approval mutation protection result

**NOT RUN** (depends on governed send pipeline / Postgres staging).

Unit coverage from prior waves still exists; Wave 5B requires live path — **not evidenced here**.

---

## J. Pause-outbound test result

**NOT RUN** on staging stack (no Postgres + email path). Automated SQLite drill from Wave 5 exists but is **not** accepted as this environment gate.

---

## K. Safe Mode send-block result

**NOT RUN** on staging stack for the same reason.

---

## L. n8n signature / replay result

| Check | Result |
|-------|--------|
| Backend unit suite `test_n8n_webhook_hmac.py` | **PASS** (valid signature / invalid / replay) |
| Deployed n8n live Code-node HMAC against this env | **NOT RUN** — no deploy target / `N8N_WEBHOOK_SECRET` unset |

Wave 5B asked for deployment-compatible signing against real env → **incomplete for launch gate**.

---

## M. Readiness flags

| Flag | Value | Who/what | When | Supporting evidence |
|------|-------|----------|------|---------------------|
| `POSTGRES_CONCURRENCY_PASS` | **unset** (must remain false) | N/A — not set | 2026-09-04 | 8 concurrency tests skipped |
| `BACKUP_RESTORE_PASS` | **unset** (must remain false) | N/A — not set | 2026-09-04 | backup script BLOCKED |

No readiness PASS flags were written.

---

## N. `GET /owner/readiness` result

Not callable against a Postgres staging app (no disposable DB / owner session stack for this wave).

Expected given evidence: **`NOT_READY`**

Failing checks would include at least: database (sqlite), concurrency env gate unset, backup env gate unset, providers, n8n secret.

---

## O. Remaining blockers

1. Provide disposable **non-production** `POSTGRES_TEST_URL`
2. Install or expose `psql` / `pg_dump` / `pg_restore` (or equivalent) on the runner
3. Configure test provider keys + `OWNER_TEST_INBOX` (email to test inbox only)
4. Configure `N8N_WEBHOOK_SECRET` and live HMAC signing for n8n
5. Re-run Wave 5B gates until each is PASS (no skips)
6. Only then set `POSTGRES_CONCURRENCY_PASS=true` / `BACKUP_RESTORE_PASS=true` from evidence
7. Confirm `GET /api/v1/owner/readiness` → `READY_FOR_PILOT`
8. **Still stop** before niche research/outreach until a later explicit owner approval

---

## P. Security issues discovered

None new beyond environment absence. Production unlock not attempted. No secrets printed. No prospect email sent.

---

## Q. Cost incurred

**€0.00** — no paid provider calls executed.

---

## R. Final recommendation

# **NO-GO**

**Not ready for controlled pilot.**

Required Wave 5B inputs (`POSTGRES_TEST_URL` and related tooling/credentials) were missing. Gates that cannot run without skips are treated as **FAIL**, not PASS. Readiness flags were left unset.

---

## STOP

- Production: **LOCKED**
- Limits: **not increased**
- Prospect outreach: **not started**
- Niche experiment: **not launched**

Awaiting explicit owner provision of a disposable Postgres URL (and optional test provider credentials) before re-running Wave 5B.
