"""Generate thin n8n workflow JSON (schedule → authenticated HTTP only)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "n8n" / "workflows"

WORKFLOWS = [
    ("daily-business-cycle", "daily-cycle", "0 6 * * *", "daily-cycle"),
    ("research", "research", "0 7 * * *", "research"),
    ("auditing", "audit", "0 8 * * *", "audit"),
    ("outreach-approval-queue", "outreach-approval-queue", "0 */2 * * *", "outreach-approval-queue"),
    ("follow-ups", "follow-ups", "30 */3 * * *", "follow-ups"),
    ("daily-report", "daily-report", "0 18 * * *", "daily-report"),
    ("error-monitoring", "error-monitoring", "15 * * * *", "error-monitoring"),
]


def build(name: str, path_suffix: str, cron: str, idem_prefix: str) -> dict:
    schedule_id = str(uuid.uuid4())
    http_id = str(uuid.uuid4())
    url = f"={{{{ $env.AI_BOS_BASE_URL }}}}/api/v1/n8n/webhooks/{path_suffix}"
    # Stable per-day key so n8n retries do not create duplicate business work.
    body = (
        "={{ JSON.stringify({ "
        f"idempotency_key: '{idem_prefix}-' + $now.toFormat('yyyy-MM-dd-HH'), "
        "payload: {}, "
        "timeout_seconds: 120 "
        "}) }}"
    )
    return {
        "name": f"AI-BOS {name}",
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "cronExpression",
                                "expression": cron,
                            }
                        ]
                    }
                },
                "id": schedule_id,
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": url,
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {
                                "name": "X-N8N-Webhook-Secret",
                                "value": "={{ $env.N8N_WEBHOOK_SECRET }}",
                            },
                            {
                                "name": "X-N8N-Timestamp",
                                "value": "={{ Math.floor(Date.now() / 1000) }}",
                            },
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": body,
                    "options": {"timeout": 130000},
                },
                "id": http_id,
                "name": "Call Backend Webhook",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [320, 0],
                "retryOnFail": True,
                "maxTries": 3,
                "waitBetweenTries": 5000,
                "notes": (
                    "Thin orchestrator only. Business logic, approvals, and "
                    "source-of-truth remain in the backend. No approval bypass. "
                    "No uncontrolled loops."
                ),
            },
        ],
        "connections": {
            "Schedule Trigger": {
                "main": [[{"node": "Call Backend Webhook", "type": "main", "index": 0}]]
            }
        },
        "settings": {
            "executionOrder": "v1",
            "callerPolicy": "workflowsFromSameOwner",
            "errorWorkflow": "",
        },
        "meta": {
            "ai_bos_phase": 17,
            "orchestration_only": True,
            "approval_bypass": False,
            "uncontrolled_loops": False,
        },
        "pinData": {},
    }


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, suffix, cron, idem in WORKFLOWS:
        path = ROOT / f"{name}.json"
        path.write_text(json.dumps(build(name, suffix, cron, idem), indent=2), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
