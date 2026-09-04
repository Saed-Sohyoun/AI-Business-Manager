"""Canonical approval fingerprints — SHA-256 over deterministic serialization.

Approvals authorize one exact immutable action. Execution must recompute
the fingerprint from live fields and match the stored value.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from app.approvals.policy import normalize_action_type

# Bump when material fingerprint fields change (invalidates old approvals safely).
APPROVAL_POLICY_VERSION = "1.0.0"


def content_sha256(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON — sorted keys, no whitespace, str for non-JSON types."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def compute_fingerprint(
    *,
    action_type: str,
    action_payload: dict[str, Any],
    manager_task_id: UUID | None = None,
) -> str:
    """SHA-256 hex digest of action_type|task|canonical_payload."""
    task = str(manager_task_id) if manager_task_id else ""
    raw = f"{normalize_action_type(action_type)}|{task}|{canonical_json(action_payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_outbound_email_payload(
    *,
    action_type: str,
    recipient_email: str,
    subject: str,
    body_text: str,
    outreach_id: UUID | str | None = None,
    lead_id: UUID | str | None = None,
    company_id: UUID | str | None = None,
    outbound_message_id: UUID | str | None = None,
    sender_from: str | None = None,
    body_html: str | None = None,
    campaign_id: str | None = None,
    estimated_cost: str | None = None,
    attachment_meta: list[dict[str, Any]] | None = None,
    policy_version: str = APPROVAL_POLICY_VERSION,
) -> dict[str, Any]:
    """Material fields for outbound email approvals (body stored as hash only)."""
    return {
        "action_type": normalize_action_type(action_type),
        "policy_version": policy_version,
        "sender_from": (sender_from or "").strip().lower(),
        "recipient_email": (recipient_email or "").strip().lower(),
        "subject": subject or "",
        "body_text_hash": content_sha256(body_text),
        "body_html_hash": content_sha256(body_html) if body_html else "",
        "outreach_id": str(outreach_id) if outreach_id else "",
        "lead_id": str(lead_id) if lead_id else "",
        "company_id": str(company_id) if company_id else "",
        "outbound_message_id": str(outbound_message_id) if outbound_message_id else "",
        "campaign_id": campaign_id or "",
        "estimated_cost": estimated_cost or "",
        "attachment_meta": attachment_meta or [],
    }


# Actions that must rebind fingerprint at execution (fail closed if payload omitted).
REBIND_REQUIRED_ACTIONS = frozenset(
    {
        "sales.send_outreach",
        "sales.first_outreach",
        "sales.send_followup",
    }
)
