"""Email provider and EmailService tests."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.approvals import ApprovalRequest, ApprovalResolver, ApprovalService, ResolveApprovalRequest
from app.config import Settings
from app.exceptions import ForbiddenError
from app.models import Company, Lead, OutboundMessage, Outreach
from app.models.enums import (
    CompanyStatus,
    LeadScoreCategory,
    LeadStatus,
    OutboundMessageStatus,
    OutreachStatus,
)
from app.providers.email.exceptions import (
    EmailConfigurationError,
    EmailProviderError,
    EmailRateLimitError,
    EmailValidationError,
)
from app.providers.email.recipient import normalize_and_validate_recipient
from app.providers.email.resend_provider import ResendEmailProvider
from app.providers.email.types import EmailAddress, EmailSendRequest, EmailSendResponse
from app.services.email_service import EmailService


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        resend_api_key=SecretStr("re_test_key"),
        email_from="ops@example.com",
        resend_max_retries=2,
        resend_timeout=5.0,
        resend_cost_per_email=Decimal("0.001"),
        max_outbound_messages_per_day=5,
        max_followups=2,
        approval_authorized_resolvers="owner,admin",
        approval_default_ttl_seconds=3600,
    )
    base.update(overrides)
    return Settings(**base)


class _FakeResponse:
    def __init__(self, status_code: int, data: dict | None = None):
        self.status_code = status_code
        self._data = data or {}
        self.headers = {}

    def json(self):
        return self._data


@pytest.fixture()
def email_env(db_session):
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
        personalization_reasons=[{"reason": "name", "evidence_ids": ["lead.name"]}],
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


def _approve_send(env, outreach: Outreach):
    view = env["approvals"].request_approval(
        ApprovalRequest(
            action_type="sales.send_outreach",
            description="Send outreach",
            requested_by="manager",
            action_payload={"outreach_id": str(outreach.id)},
        )
    )
    env["session"].commit()
    env["resolver"].approve(
        ResolveApprovalRequest(approval_id=view.id, resolved_by="owner", note="ok")
    )
    outreach.approval_id = view.id
    outreach.status = OutreachStatus.PENDING_APPROVAL
    env["session"].commit()
    return view.id


def _mock_provider_ok() -> MagicMock:
    provider = MagicMock()
    provider.name = "resend"
    provider.is_configured.return_value = True
    provider.send.return_value = EmailSendResponse(
        provider="resend",
        provider_message_id="msg_123",
        delivery_status="accepted",
        estimated_cost=Decimal("0.001"),
        latency_ms=12.0,
        attempts=1,
        to_email="alex@acme.example",
        subject="Quick note for Acme",
    )
    return provider


def test_successful_email(email_env):
    _approve_send(email_env, email_env["outreach"])
    provider = _mock_provider_ok()
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=email_env["settings"],
        approval_service=email_env["approvals"],
    )
    msg = service.send_outreach(email_env["outreach"].id)
    assert msg.status == OutboundMessageStatus.SENT
    assert msg.provider_message_id == "msg_123"
    assert msg.estimated_cost == Decimal("0.001")
    assert msg.delivery_status == "accepted"
    email_env["session"].refresh(email_env["outreach"])
    assert email_env["outreach"].status == OutreachStatus.SENT
    assert email_env["outreach"].sent_at is not None
    provider.send.assert_called_once()


def test_duplicate_prevention(email_env):
    _approve_send(email_env, email_env["outreach"])
    provider = _mock_provider_ok()
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=email_env["settings"],
        approval_service=email_env["approvals"],
    )
    first = service.send_outreach(email_env["outreach"].id)
    second = service.send_outreach(email_env["outreach"].id)
    assert first.id == second.id
    assert provider.send.call_count == 1


def test_invalid_recipient():
    with pytest.raises(EmailValidationError):
        normalize_and_validate_recipient("not-an-email")
    with pytest.raises(EmailValidationError):
        normalize_and_validate_recipient("noreply@example.com")


def test_invalid_recipient_via_service(email_env):
    approval_id = _approve_send(email_env, email_env["outreach"])
    provider = _mock_provider_ok()
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=email_env["settings"],
        approval_service=email_env["approvals"],
    )
    with pytest.raises(EmailValidationError):
        service.send(
            to_email="bad",
            subject="Hi",
            body_text="Body",
            idempotency_key="bad-1",
            approval_id=approval_id,
        )


def test_provider_failure(email_env):
    _approve_send(email_env, email_env["outreach"])
    provider = MagicMock()
    provider.name = "resend"
    provider.is_configured.return_value = True
    provider.send.side_effect = EmailProviderError("boom")
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=email_env["settings"],
        approval_service=email_env["approvals"],
    )
    with pytest.raises(EmailProviderError):
        service.send_outreach(email_env["outreach"].id)
    row = email_env["session"].query(OutboundMessage).one()
    assert row.status == OutboundMessageStatus.FAILED
    email_env["session"].refresh(email_env["outreach"])
    assert email_env["outreach"].status == OutreachStatus.FAILED


def test_resend_provider_retry_then_success():
    cfg = _settings(resend_max_retries=2)
    client = MagicMock()
    client.post.side_effect = [
        _FakeResponse(500, {"message": "unavailable"}),
        _FakeResponse(200, {"id": "msg_ok"}),
    ]
    provider = ResendEmailProvider(cfg, http_client=client, sleep_fn=lambda _s: None)
    result = provider.send(
        EmailSendRequest(
            to=EmailAddress(email="alex@acme.example"),
            subject="Hello",
            body_text="Body text",
            idempotency_key="retry-1",
        )
    )
    assert result.provider_message_id == "msg_ok"
    assert result.attempts == 2
    assert client.post.call_count == 2


def test_resend_provider_not_configured():
    cfg = _settings(resend_api_key=None)
    provider = ResendEmailProvider(cfg, http_client=MagicMock())
    with pytest.raises(EmailConfigurationError):
        provider.send(
            EmailSendRequest(
                to=EmailAddress(email="a@b.co"),
                subject="x",
                body_text="y",
                idempotency_key="k",
            )
        )


def test_approval_requirement(email_env):
    provider = _mock_provider_ok()
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=email_env["settings"],
        approval_service=email_env["approvals"],
    )
    with pytest.raises(ForbiddenError):
        service.send_outreach(email_env["outreach"].id)

    view = email_env["approvals"].request_approval(
        ApprovalRequest(
            action_type="sales.send_outreach",
            description="Send",
            requested_by="manager",
            action_payload={"outreach_id": str(email_env["outreach"].id)},
        )
    )
    email_env["session"].commit()
    email_env["outreach"].approval_id = view.id
    email_env["session"].commit()
    with pytest.raises(ForbiddenError):
        service.send_outreach(email_env["outreach"].id)
    assert provider.send.call_count == 0


def test_rate_limit_daily(email_env):
    cfg = email_env["settings"].model_copy(update={"max_outbound_messages_per_day": 1})
    approval_id = _approve_send(email_env, email_env["outreach"])
    provider = _mock_provider_ok()
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=cfg,
        approval_service=email_env["approvals"],
    )
    service.send_outreach(email_env["outreach"].id)

    with pytest.raises(EmailRateLimitError):
        service.send(
            to_email="other@acme.example",
            subject="Another",
            body_text="Body",
            idempotency_key="other-1",
            approval_id=approval_id,
            lead_id=uuid4(),
        )


def test_followup_limit(email_env):
    cfg = email_env["settings"].model_copy(update={"max_followups": 1})
    approval_id = _approve_send(email_env, email_env["outreach"])
    provider = _mock_provider_ok()
    service = EmailService(
        provider,
        session=email_env["session"],
        settings=cfg,
        approval_service=email_env["approvals"],
    )
    service.send(
        to_email="alex@acme.example",
        subject="First",
        body_text="Body",
        idempotency_key="fu-1",
        approval_id=approval_id,
        lead_id=email_env["lead"].id,
    )
    service.send(
        to_email="alex@acme.example",
        subject="Follow 1",
        body_text="Body",
        idempotency_key="fu-2",
        approval_id=approval_id,
        lead_id=email_env["lead"].id,
    )
    with pytest.raises(EmailRateLimitError):
        service.send(
            to_email="alex@acme.example",
            subject="Follow 2",
            body_text="Body",
            idempotency_key="fu-3",
            approval_id=approval_id,
            lead_id=email_env["lead"].id,
        )


def test_app_boots_without_resend_key():
    cfg = _settings(resend_api_key=None, email_from=None)
    assert cfg.resend_configured is False
    provider = ResendEmailProvider(cfg)
    assert provider.is_configured() is False
