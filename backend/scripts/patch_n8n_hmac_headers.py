"""Patch n8n workflow JSON to include nonce + signature headers."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "n8n" / "workflows"


def main() -> None:
    for path in sorted(ROOT.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for node in data.get("nodes", []):
            params = node.get("parameters") or {}
            headers = (params.get("headerParameters") or {}).get("parameters")
            if not isinstance(headers, list):
                continue
            names = {h.get("name") for h in headers}
            if "X-N8N-Timestamp" not in names:
                continue
            if "X-N8N-Nonce" not in names:
                headers.append(
                    {
                        "name": "X-N8N-Nonce",
                        "value": "={{ $execution.id + '-' + String(Math.floor(Date.now())) }}",
                    }
                )
                changed = True
            if "X-N8N-Signature" not in names:
                headers.append(
                    {
                        "name": "X-N8N-Signature",
                        "value": "={{ $env.N8N_WEBHOOK_HMAC_SIGNATURE }}",
                    }
                )
                changed = True
            if changed and node.get("type") == "n8n-nodes-base.httpRequest":
                node["notes"] = (
                    "Thin orchestrator only. Send X-N8N-Timestamp, X-N8N-Nonce, and "
                    "X-N8N-Signature (HMAC-SHA256 over timestamp.METHOD.path.body). "
                    "Set N8N_WEBHOOK_HMAC_SIGNATURE via a Sign Code node. "
                    "Backend remains source of truth."
                )
        if changed:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print("updated", path.name)
        else:
            print("skip", path.name)


if __name__ == "__main__":
    main()
