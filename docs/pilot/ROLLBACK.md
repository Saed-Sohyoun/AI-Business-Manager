# Rollback playbook (Wave 5 pilot)

## Goals

Return the system to a known-good state quickly without unlocking production mode
or expanding pilot limits.

## Application rollback

1. Pause all operations via owner control: `POST /api/v1/owner/system/pause-all`.
2. Enter Safe Mode if providers are misbehaving.
3. Redeploy the previous known-good backend image / commit.
4. Confirm `ALLOW_PRODUCTION_MODE` remains unset/false.
5. Confirm pilot caps still at Wave envelope (20/10/5/2, €3/day, €20 max expense).

## Database rollback

1. Prefer forward-fix migrations when possible.
2. If a Wave 5 migration must be reversed:

   ```bash
   cd backend
   alembic downgrade 0017_wave4_production_readiness
   ```

3. Only downgrade against a restored backup or staging copy first.
4. Re-run `scripts/validate_migrations_postgres.py` on `POSTGRES_TEST_URL` after rollback drills.

## Config rollback

- Revert environment variables via the same change-control path used to deploy them.
- Never commit secrets into git to “speed up” rollback.

## Verification after rollback

- `GET /health` → ok / degraded as expected
- `GET /api/v1/owner/readiness` → inspect failing checks (do not invent pass)
- Kill-switch drill: pause-all still blocks outbound + AI
- Production remains locked
