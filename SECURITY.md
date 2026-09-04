# Security — Phase 20

This document records threat-model decisions for the AI Business Operating System.
External content is always **untrusted**. Agents have only **explicitly defined**
capabilities. AI never receives unrestricted system access.

## Principles

1. **Fail closed** — missing secrets, invalid approvals, unsafe URLs, and budget
   overruns reject the action.
2. **Least privilege** — browser, search, email, and finance each expose a narrow
   API; Manager cannot invent new tools.
3. **Human gate** — YELLOW/RED actions go through `ApprovalService`. Agents cannot
   bypass approvals or auto-approve RED actions.
4. **Money is Decimal** — ledger math uses `Decimal`; single-expense and daily
   budget ceilings are enforced on cost recording and Manager stop checks.
5. **Untrusted framing** — web/search content is labeled for LLM use and must not
   be placed in system prompts as instructions.

## Authentication & authorization

| Surface | Control |
| --- | --- |
| n8n webhooks | Shared secret (`N8N_WEBHOOK_SECRET`) via `X-N8N-Webhook-Secret` or Bearer; constant-time compare |
| Replay mitigation | `X-N8N-Timestamp` (Unix seconds) required by default; max skew `N8N_WEBHOOK_MAX_SKEW_SECONDS` |
| Owner HTTP (future approve/dashboard APIs) | `OWNER_API_KEY` via `X-Owner-API-Key`; resolver must be in `APPROVAL_AUTHORIZED_RESOLVERS` |
| Approvals | Policy GREEN/YELLOW/RED; authorized resolvers only; no agent self-approve |

There is **no** public approve-by-name API that trusts a free-text `resolved_by`
without `OWNER_API_KEY`.

## Network & browser

- Document and **all http(s) subresources** are SSRF-checked (`should_abort_browser_request`).
- Blocked: private/loopback/link-local/metadata hosts, non-http(s) schemes, downloads.
- `BROWSER_JAVASCRIPT_ENABLED` defaults to **false** to reduce JS-driven SSRF.
- Search result URL filter blocks private IPv4/IPv6 literals and metadata hostnames.

## API hardening

- Explicit CORS allow-list; production forbids `*`; headers allow-list (not `*`).
- Sliding-window rate limits: n8n / health / other API paths (process-local).
- Production: OpenAPI/docs disabled; health omits version/environment fingerprinting.
- `APP_DEBUG` must be false in production (`assert_production_settings`).

## Financial safety & runaway agents

- `MAX_SINGLE_EXPENSE` / `DAILY_BUDGET_LIMIT` enforced on `FinanceAgent.record_cost`.
- Manager stops on runtime, per-run AI cost, task count, retry budget, and daily budget.
- Outbound email/Telegram caps and notification priority floors reduce spam/cost abuse.
- n8n workflows are thin schedulers only — no business logic loops in n8n.

## Prompt injection & logging

- Search/browser services expose `format_untrusted_context` with an explicit
  untrusted preamble.
- Provider logs use sanitizers; secrets use `SecretStr` / masking helpers.
- Do not log raw webhook secrets, owner keys, or full email bodies in production.

## Webhooks (ops)

1. Set a long random `N8N_WEBHOOK_SECRET`.
2. Keep `N8N_WEBHOOK_REQUIRE_TIMESTAMP=true` (default).
3. Ensure workflow templates send `X-N8N-Timestamp` (see `n8n/workflows/*.json`).
4. Prefer private network / reverse-proxy ACLs in front of the API.

## What Phase 20 does not claim

- Distributed rate limiting / WAF
- Full OAuth / session SSO for the React dashboard (demo UI remains non-authoritative)
- Signed webhook body HMAC (timestamp + shared secret is the current bar)
- Automated dependency CVE CI (run `pip-audit` / `npm audit` in release process)

## Tests

See `backend/tests/test_security.py` for SSRF abort rules, budget caps, webhook
timestamp skew, constant-time compare edge cases, owner auth stub, rate limiter,
production settings asserts, and private IPv6 URL blocks.
