# Pilot launch gate (Wave 5)

## Overall statuses

| Status | Meaning |
|--------|---------|
| `READY_FOR_PILOT` | All hard readiness checks pass |
| `NOT_READY` | One or more hard checks fail or are unset |

Source of truth: `GET /api/v1/owner/readiness` (owner auth required).
This endpoint **never** unlocks production and **never** returns secrets.

## Hard checks (fail → NOT_READY)

- PostgreSQL database (sqlite fails)
- Owner auth configured
- Pilot limits within envelope
- Production locked (`ALLOW_PRODUCTION_MODE` false)
- n8n webhook secret configured
- Session cookie secure when `APP_ENV=production`
- Debug false in production
- No wildcard CORS
- `POSTGRES_CONCURRENCY_PASS=true` (unset → fail)
- `BACKUP_RESTORE_PASS=true` (unset → fail)

## Soft / warn

- Providers may be warn if none configured (boot still allowed)
- `SESSION_COOKIE_SECURE` warn in non-production when false

## Experiment gate

- Create draft: `POST /api/v1/owner/pilot/experiment`
- Approve niche: `POST /api/v1/owner/pilot/experiment/{id}/approve-niche`
- Activation requires `owner_approved_niche`
- Observability: `GET /api/v1/owner/pilot/status` (DB counters only)

## Non-negotiables

- Do not raise pilot limits above Wave envelope
- Do not enable unrestricted outreach
- Do not unlock production as a shortcut to “green” readiness
- Do not invent pilot research results
