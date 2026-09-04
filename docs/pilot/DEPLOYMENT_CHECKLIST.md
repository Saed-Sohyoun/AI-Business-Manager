# Deployment checklist (Wave 5 pilot)

Use this before pointing real traffic at a pilot environment. Production mode stays **locked**.

## Pre-deploy

- [ ] Postgres is the application database (not sqlite)
- [ ] Migrations applied to head (`0018_wave5_pilot_experiment`)
- [ ] `scripts/validate_migrations_postgres.py` PASS on `POSTGRES_TEST_URL`
- [ ] `scripts/backup_restore_validate.py` PASS → set `BACKUP_RESTORE_PASS=true`
- [ ] Postgres concurrency suite PASS → set `POSTGRES_CONCURRENCY_PASS=true`
- [ ] `scripts/secret_scan.py` reports NOT_FOUND for committed secret categories
- [ ] `scripts/provider_smoke.py` run (email remains config-only unless `OWNER_TEST_INBOX`)
- [ ] Owner auth configured (session bootstrap and/or API key for emergency)
- [ ] `N8N_WEBHOOK_SECRET` set; n8n HMAC not left as placeholder
- [ ] `SESSION_COOKIE_SECURE=true` behind HTTPS
- [ ] `APP_DEBUG=false` for production-like env
- [ ] No wildcard CORS with credentials
- [ ] `ALLOW_PRODUCTION_MODE` unset/false
- [ ] Pilot limits ≤ 20 companies / 10 audits / 5 first outreach / 2 follow-ups / €3 day / €20 expense

## Deploy

- [ ] Deploy backend + frontend artifacts
- [ ] Confirm `/health`
- [ ] Owner login works without embedding secrets in the frontend bundle
- [ ] `GET /api/v1/owner/readiness` reviewed (READY_FOR_PILOT only when all hard checks pass)

## Post-deploy drills

- [ ] Pause-all blocks outbound + AI
- [ ] Safe Mode drill
- [ ] Budget warning thresholds observed in staging (do not burn real budget)
- [ ] Create pilot experiment draft; niche approval required before active use
