"""Shared helpers for outreach body composition (approval fingerprint alignment)."""

from __future__ import annotations

from app.models.outreach import Outreach


def compose_outreach_body(outreach: Outreach) -> str:
    """Exact body text used for both approval fingerprint and send."""
    body = outreach.message or ""
    if outreach.cta and outreach.cta not in body:
        body = f"{body}\n\n{outreach.cta}"
    return body
