"""Wave 1 — approval fingerprint rebinding tests."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from app.approvals import ApprovalRequest, ApprovalResolver, ApprovalService, ResolveApprovalRequest
from app.approvals.fingerprint import build_outbound_email_payload, compute_fingerprint
from app.config import Settings
from app.exceptions import ApprovalPayloadMismatchError, ForbiddenError
from app.models import Company, Lead, Outreach
from app.models.enums import (
    ApprovalStatus,
    CompanyStatus,
    LeadScoreCategory,
    LeadStatus,
    OutreachStatus,
)
from app.providers.email.types import EmailSendResponse
from app.services.email_service import EmailService
from app.services.outreach_body import compose_outreach_body


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        resend_api_key=SecretStr("re_test_key"),
        email_from="ops@example.com",
        max_outbound_messages_per_day=50,
        max_followups=2,
        approval_authorized_resolvers="owner,admin",
        approval_default_ttl_seconds=3600,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def env(db_session):
    cfg = _settings()
    company = Company(name="Acme", status=CompanyStatus.PROSPECT, source="test")
    db_session.add(company)
    db_session.flush()
    lead = Lead(
        company_id=company.id,
        name="Alex",
        email="alex@acme.example",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    db_session.add(lead)
    db_session.flush()
    outreach = Outreach(
        company_id=company.id,
        lead_id=lead.id,
        outreach_version="1.0.0",
        status=OutreachStatus.DRAFT,
        subject="Quick note for Acme",
        message="Hi Alex,\n\nShort note.",
        cta="Open to a call?",
        confidence=Decimal("0.7"),
        recipient_email="alex@acme.example",
        recipient_name="Alex",
        personalization_reasons=[],
        evidence_used=[],
        evidence_catalog=[],
        input_snapshot={},
    )
    db_session.add(outreach)
    db_session.commit()
    approvals = ApprovalService(db_session, cfg)
    resolver = ApprovalResolver(db_session, cfg, service=approvals)
    return {
        "session": db_session,
        "settings": cfg,
        "company": company,
        "lead": lead,
        "outreach": outreach,
        "approvals": approvals,
        "resolver": resolver,
    }


def _approve(env, outreach: Outreach):
    payload = build_outbound_email_payload(
        action_type="sales.send_outreach",
        recipient_email=outreach.recipient_email or "",
        subject=outreach.subject,
        body_text=compose_outreach_body(outreach),
        outreach_id=outreach.id,
        lead_id=outreach.lead_id,
        company_id=outreach.company_id,
        sender_from=env["settings"].email_from or "",
    )
    view = env["approvals"].request_approval(
        ApprovalRequest(
            action_type="sales.send_outreach",
            description="Send",
            requested_by="sales",
            action_payload=payload,
        )
    )
    env["session"].commit()
    env["resolver"].approve(
        ResolveApprovalRequest(approval_id=view.id, resolved_by="owner", note="ok")
    )
    outreach.approval_id = view.id
    outreach.status = OutreachStatus.PENDING_APPROVAL
    env["session"].commit()
    return view.id, payload


def _service(env) -> EmailService:
    provider = MagicMock()
    provider.name = "resend"
    provider.is_configured.return_value = True
    provider.send.return_value = EmailSendResponse(
        provider="resend",
        provider_message_id="msg_1",
        delivery_status="accepted",
        estimated_cost=Decimal("0.001"),
        latency_ms=1.0,
        attempts=1,
        to_email="alex@acme.example",
        subject="Quick note for Acme",
    )
    return EmailService(
        provider,
        session=env["session"],
        settings=env["settings"],
        approval_service=env["approvals"],
    )


def test_unchanged_payload_allows_send(env):
    _approve(env, env["outreach"])
    msg = _service(env).send_outreach(env["outreach"].id)
    assert msg is not None


@pytest.mark.parametrize(
    "mutator",
    [
        lambda o: setattr(o, "message", "MUTATED BODY — should invalidate approval"),
        lambda o: setattr(o, "subject", "Mutated subject"),
        lambda o: setattr(o, "recipient_email", "other@example.com"),
    ],
)
def test_material_field_change_invalidates_approval(env, mutator):
    approval_id, _ = _approve(env, env["outreach"])
    mutator(env["outreach"])
    env["session"].commit()
    with pytest.raises(ApprovalPayloadMismatchError) as exc:
        _service(env).send_outreach(env["outreach"].id)
    assert exc.value.code == "approval_payload_mismatch"
    from app.models import Approval

    row = env["session"].get(Approval, approval_id)
    assert row is not None
    assert row.status == ApprovalStatus.CANCELLED.value


def test_company_change_invalidates(env):
    _approve(env, env["outreach"])
    other = Company(name="OtherCo", status=CompanyStatus.PROSPECT, source="test")
    env["session"].add(other)
    env["session"].flush()
    env["outreach"].company_id = other.id
    env["session"].commit()
    with pytest.raises(ApprovalPayloadMismatchError):
        _service(env).send_outreach(env["outreach"].id)


def test_action_type_mismatch_still_denied(env):
    approval_id, payload = _approve(env, env["outreach"])
    gate = env["approvals"].evaluate_gate(
        "commerce.purchase",
        approval_id=approval_id,
        action_payload=payload,
    )
    assert gate.may_execute is False


def test_fingerprint_deterministic():
    a = build_outbound_email_payload(
        action_type="sales.send_outreach",
        recipient_email="a@b.com",
        subject="Hi",
        body_text="Body",
        outreach_id="11111111-1111-1111-1111-111111111111",
    )
    b = build_outbound_email_payload(
        action_type="sales.send_outreach",
        recipient_email="a@b.com",
        subject="Hi",
        body_text="Body",
        outreach_id="11111111-1111-1111-1111-111111111111",
    )
    assert compute_fingerprint(action_type="sales.send_outreach", action_payload=a) == (
        compute_fingerprint(action_type="sales.send_outreach", action_payload=b)
    )
    b["subject"] = "Changed"
    assert compute_fingerprint(action_type="sales.send_outreach", action_payload=a) != (
        compute_fingerprint(action_type="sales.send_outreach", action_payload=b)
    )
