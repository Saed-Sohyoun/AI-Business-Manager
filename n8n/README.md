# n8n orchestration (Wave 4 / Wave 5)

n8n schedules and routes only. The FastAPI backend remains the source of truth for
business logic, approvals, Pilot limits, and Safe Mode.

## Required webhook headers

When `N8N_WEBHOOK_REQUIRE_SIGNATURE=true` (recommended outside local smoke tests):

| Header | Purpose |
|--------|---------|
| `X-N8N-Webhook-Secret` | Shared secret (or `Authorization: Bearer …`) |
| `X-N8N-Timestamp` | Unix seconds (skew-checked) |
| `X-N8N-Nonce` | Unique per request (replay protection) |
| `X-N8N-Signature` | `sha256=` + HMAC-SHA256 hex |

Canonical signing string:

```text
{timestamp}.{METHOD}.{path}.{raw_body}
```

Example (Python):

```python
import hashlib, hmac
sig = "sha256=" + hmac.new(
    secret.encode(),
    f"{ts}.POST./api/v1/n8n/webhooks/research.".encode() + body,
    hashlib.sha256,
).hexdigest()
```

## Wave 5 deploy gate — replace placeholder HMAC

Workflow JSON examples include timestamp, nonce, and signature header slots.
They currently reference a **placeholder** `N8N_WEBHOOK_HMAC_SIGNATURE` env expression.

**Before any pilot deploy (Wave 5 launch gate):**

1. Add a Code node that computes HMAC-SHA256 over the exact request body bytes you send
2. Populate `X-N8N-Signature` from that Code-node output (live HMAC), not a blank/static env stub
3. Confirm the backend accepts signed requests and rejects modified body, old timestamps, reused nonces, and invalid signatures

Do **not** leave `N8N_WEBHOOK_HMAC_SIGNATURE` as an unset/blank placeholder in a deployed pilot workflow.
Leaving placeholder signing logic is a **NO-GO** for the Wave 5 pilot launch gate.
