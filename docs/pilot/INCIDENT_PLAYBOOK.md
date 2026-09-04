# Incident playbook (Wave 5 pilot)

## Severity quick guide

| Severity | Examples | First action |
|----------|----------|--------------|
| Critical | Uncontrolled outbound, spend runaway, auth breach | Pause-all + Safe Mode |
| Urgent | Provider circuit open, budget ≥90% | Pause spend/outbound; investigate |
| Important | Budget ≥70%, degraded provider | Notify owner; reduce load |
| Info | Soft readiness warnings | Track; do not ignore gates |

## Kill switch (pause all)

```http
POST /api/v1/owner/system/pause-all
```

Expected effect: AI operations, outbound, spending, and browser automation disabled.
Verify with `GET /api/v1/owner/system/status`.

## Safe Mode

```http
POST /api/v1/owner/system/safe-mode
```

Outbound and spending remain blocked until cleared by the owner.

## Budget incidents

- 70% — OwnerAlert INFO/IMPORTANT (deduped per UTC day)
- 90% — OwnerAlert URGENT (deduped)
- 100% — hard stop via `assert_daily_budget` / BudgetGuard

Do **not** raise pilot budget ceilings during an incident.

## Circuit open

Provider calls may surface `CIRCUIT_OPEN` / service unavailable.
Do not disable the circuit breaker. Wait for half-open recovery or fix the upstream key/network.

## Secrets

- Rotate compromised keys offline.
- Run `python backend/scripts/secret_scan.py` after suspected leaks.
- Never paste live secrets into tickets or chat.

## Communications

Notify the owner via existing OwnerAlert / Telegram paths only.
Do not invent pilot research results or success metrics in status updates.
