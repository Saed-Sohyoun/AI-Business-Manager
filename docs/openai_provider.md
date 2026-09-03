# OpenAI Configuration

This project’s AI layer is provider-based (no direct OpenAI dependency in the rest of the app).

## Required Environment Variables

Add the following to your environment (or to a local `.env` file):

- `OPENAI_API_KEY`: your OpenAI API key.

### Optional Configuration

- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `OPENAI_TIMEOUT_SECONDS` (default: `30.0`)
- `OPENAI_MAX_RETRIES` (default: `2`)
- `OPENAI_RETRY_BACKOFF_SECONDS_BASE` (default: `1.0`)
- `OPENAI_RETRY_BACKOFF_SECONDS_MAX` (default: `30.0`)

## Token Cost Estimation (Optional)

Estimated API cost is computed from token usage when available.

- `OPENAI_PROMPT_TOKEN_COST_USD_PER_1K_TOKENS` (default: `0.00`)
- `OPENAI_COMPLETION_TOKEN_COST_USD_PER_1K_TOKENS` (default: `0.00`)

If these are left as `0.00`, the service will still return token usage, but estimated cost may be `0.0` or `None` depending on provider usage data.

