# Backup & restore validation (Wave 5)

## Purpose

Prove that a PostgreSQL backup can be taken and inspected before a real-world pilot.
This is a **launch gate** — unset validation is treated as **BLOCKED**, not a pass.

## Script

```bash
cd backend
python scripts/backup_restore_validate.py
```

## Environment

| Variable | Required | Notes |
|----------|----------|-------|
| `POSTGRES_TEST_URL` | yes | Dedicated test DB URL (never production write targets) |
| `BACKUP_RESTORE_PASS` | for readiness | Set `true` only after a successful validation run |

Exit codes:

- `0` — PASS (dump + `pg_restore -l`)
- `1` — FAIL
- `2` — BLOCKED (`POSTGRES_TEST_URL` missing or tools not on PATH)

## Operator steps

1. Provision an isolated Postgres database for validation.
2. Ensure `pg_dump` and `pg_restore` are on `PATH`.
3. Run the script; confirm `BACKUP_RESTORE=PASS`.
4. Export `BACKUP_RESTORE_PASS=true` for the readiness endpoint / gate.
5. Document where production backups are stored (off-box) and retention.

## Safety

- The script does **not** print connection passwords or dump contents.
- Do not point `POSTGRES_TEST_URL` at production.
- Restoring into production is **out of scope** for this validator — use a scratch DB for full restore drills.
