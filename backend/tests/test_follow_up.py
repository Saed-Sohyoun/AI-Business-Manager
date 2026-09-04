"""Phase 12 — follow-up system tests."""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.approvals import ApprovalRequest, ApprovalResolver, ApprovalService, ResolveApprovalRequest
from app.config import Settings
from app.exceptions import ForbiddenError
from app.models import Company, FollowUpItem, FollowUpSequence, Lead, Outreach
from app.models.base import utc_now
from app.models.enums import (
    CompanyStatus,
    FollowUpItemStatus,
    FollowUpSequenceStatus,
    FollowUpStopReason,
    LeadScoreCategory,
    LeadStatus,
    OutboundMessageStatus,
    OutreachStatus,
)
from app.providers.email.types import EmailSendResponse
from app.services.email_service import EmailService
from app.services.follow_up_service import FollowUpService


def _aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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
        followup_delay_days_first=3,
        followup_delay_days_second=7,
        approval_authorized_resolvers="owner,admin",
        approval_default_ttl_seconds=3600,
    )
    base.update(overrides)
    return Settings(**base)


def _mock_provider_ok(to_email: str = "alex@acme.example") -> MagicMock:
    provider = MagicMock()
    provider.name = "resend"
    provider.is_configured.return_value = True
    provider.send.return_value = EmailSendResponse(
        provider="resend",
        provider_message_id="msg_fu_1",
        delivery_status="accepted",
        estimated_cost=Decimal("0.001"),
        latency_ms=10.0,
        attempts=1,
        to_email=to_email,
        subject="test",
    )
    return provider


def _email_service(env, provider: MagicMock | None = None) -> EmailService:
    return EmailService(
        provider or _mock_provider_ok(),
        session=env["session"],
        settings=env["settings"],
        approval_service=env["approvals"],
    )


def _followups(env, provider: MagicMock | None = None) -> FollowUpService:
    return FollowUpService(
        session=env["session"],
        settings=env["settings"],
        approval_service=env["approvals"],
        email_service=_email_service(env, provider),
    )


@pytest.fixture()
def fu_env(db_session):
    cfg = _settings()
    company = Company(name="Acme", status=CompanyStatus.PROSPECT, source="test")
    db_session.add(company)
    db_session.flush()
    lead = Lead(
        company_id=company.id,
        name="Alex Rivera",
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
        recipient_name="Alex Rivera",
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


def _approve_initial(env) -> None:
    from app.approvals.fingerprint import build_outbound_email_payload
    from app.services.outreach_body import compose_outreach_body

    outreach = env["outreach"]
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
            description="Send initial",
            requested_by="manager",
            action_payload=payload,
        )
    )
    env["session"].commit()
    env["resolver"].approve(
        ResolveApprovalRequest(approval_id=view.id, resolved_by="owner", note="ok")
    )
    env["outreach"].approval_id = view.id
    env["outreach"].status = OutreachStatus.PENDING_APPROVAL
    env["session"].commit()


def _send_initial(env) -> None:
    _approve_initial(env)
    _email_service(env).send_outreach(env["outreach"].id)
    env["session"].refresh(env["outreach"])
    env["session"].refresh(env["lead"])


def _get_sequence(env) -> FollowUpSequence:
    return env["session"].scalar(select(FollowUpSequence).limit(1))


def _make_sequence_due(env) -> FollowUpSequence:
    seq = _get_sequence(env)
    seq.next_follow_up_at = utc_now() - timedelta(minutes=1)
    seq.status = FollowUpSequenceStatus.ACTIVE
    env["session"].commit()
    return seq


def _approve_followup(env, approval_id) -> None:
    env["resolver"].approve(
        ResolveApprovalRequest(approval_id=approval_id, resolved_by="owner", note="fu ok")
    )


def test_scheduling_creates_due_followup(fu_env):
    _send_initial(fu_env)
    seq = _get_sequence(fu_env)
    assert seq.status == FollowUpSequenceStatus.ACTIVE
    assert seq.follow_up_count == 0
    assert seq.next_follow_up_at is not None
    assert _aware(seq.next_follow_up_at) > utc_now()

    followups = _followups(fu_env)
    assert followups.process_due(now=utc_now()) == []

    _make_sequence_due(fu_env)
    results = followups.process_due(now=utc_now())
    assert len(results) == 1
    assert results[0].action == "drafted_pending_approval"
    assert results[0].approval_id is not None
    assert results[0].outreach_id is not None

    item = fu_env["session"].get(FollowUpItem, results[0].item_id)
    assert item is not None
    assert item.followup_index == 1
    assert item.status == FollowUpItemStatus.PENDING_APPROVAL
    outreach = fu_env["session"].get(Outreach, item.outreach_id)
    assert outreach is not None
    assert "Acme" in outreach.message
    assert outreach.extra_metadata.get("is_followup") is True


def test_duplicate_prevention(fu_env):
    _send_initial(fu_env)
    _make_sequence_due(fu_env)
    followups = _followups(fu_env)
    first = followups.process_due(now=utc_now())
    assert first[0].action == "drafted_pending_approval"

    seq = _get_sequence(fu_env)
    assert seq.status == FollowUpSequenceStatus.WAITING_APPROVAL
    seq.status = FollowUpSequenceStatus.ACTIVE
    seq.next_follow_up_at = utc_now() - timedelta(minutes=1)
    fu_env["session"].commit()

    second = followups.process_due(now=utc_now())
    assert len(second) == 1
    assert second[0].action == "skipped_duplicate"
    assert second[0].item_id == first[0].item_id
    count = fu_env["session"].scalar(select(FollowUpItem.id))
    assert count is not None
    assert len(list(fu_env["session"].scalars(select(FollowUpItem)))) == 1


def test_reply_stops_sequence(fu_env):
    _send_initial(fu_env)
    _make_sequence_due(fu_env)
    followups = _followups(fu_env)
    followups.record_reply(fu_env["lead"].id, meeting=True)

    seq = _get_sequence(fu_env)
    assert seq.status == FollowUpSequenceStatus.STOPPED
    assert seq.stop_reason == FollowUpStopReason.REPLIED
    assert seq.response_received is True
    assert seq.meetings_generated == 1
    assert seq.next_follow_up_at is None

    assert followups.process_due(now=utc_now()) == []
    metrics = followups.metrics()
    assert metrics.responses == 1
    assert metrics.meetings_generated == 1
    assert metrics.response_rate == 1.0


def test_opt_out_stops_sequence(fu_env):
    _send_initial(fu_env)
    _make_sequence_due(fu_env)
    followups = _followups(fu_env)
    followups.record_opt_out(fu_env["lead"].id)

    seq = _get_sequence(fu_env)
    assert seq.status == FollowUpSequenceStatus.STOPPED
    assert seq.stop_reason == FollowUpStopReason.OPTED_OUT
    assert fu_env["lead"].opted_out is True
    assert followups.process_due(now=utc_now()) == []


def test_max_follow_up_limit(fu_env):
    cfg = fu_env["settings"].model_copy(update={"max_followups": 2})
    fu_env["settings"] = cfg
    provider = _mock_provider_ok()
    followups = _followups(fu_env, provider)
    _send_initial(fu_env)

    for expected_index in (1, 2):
        _make_sequence_due(fu_env)
        results = followups.process_due(now=utc_now())
        assert results[0].action == "drafted_pending_approval"
        _approve_followup(fu_env, results[0].approval_id)
        msg = followups.send_followup(results[0].item_id)
        assert msg.status == OutboundMessageStatus.SENT
        item = fu_env["session"].get(FollowUpItem, results[0].item_id)
        assert item.followup_index == expected_index
        assert item.status == FollowUpItemStatus.SENT

    seq = _get_sequence(fu_env)
    assert seq.follow_up_count == 2
    assert seq.status == FollowUpSequenceStatus.COMPLETED
    assert seq.stop_reason == FollowUpStopReason.MAX_FOLLOWUPS
    assert seq.next_follow_up_at is None

    seq.status = FollowUpSequenceStatus.ACTIVE
    seq.next_follow_up_at = utc_now() - timedelta(minutes=1)
    fu_env["session"].commit()
    again = followups.process_due(now=utc_now())
    # Due query excludes sequences already at max_followups
    assert again == []
    assert len(list(fu_env["session"].scalars(select(FollowUpItem)))) == 2


def test_approval_handling(fu_env):
    _send_initial(fu_env)
    _make_sequence_due(fu_env)
    provider = _mock_provider_ok()
    followups = _followups(fu_env, provider)
    results = followups.process_due(now=utc_now())
    item_id = results[0].item_id

    with pytest.raises(ForbiddenError):
        followups.send_followup(item_id)

    _approve_followup(fu_env, results[0].approval_id)
    msg = followups.send_followup(item_id)
    assert msg.status == OutboundMessageStatus.SENT
    again = followups.send_followup(item_id)
    assert again.id == msg.id
    assert provider.send.call_count == 1

    metrics = followups.metrics()
    assert metrics.initial_sent == 1
    assert metrics.followups_sent == 1


def test_customer_and_blocked_stop(fu_env):
    _send_initial(fu_env)
    followups = _followups(fu_env)
    followups.mark_customer(fu_env["lead"].id)
    seq = _get_sequence(fu_env)
    assert seq.stop_reason == FollowUpStopReason.BECAME_CUSTOMER

    lead2 = Lead(
        company_id=fu_env["company"].id,
        name="Blake",
        email="blake@acme.example",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    fu_env["session"].add(lead2)
    fu_env["session"].flush()
    outreach2 = Outreach(
        company_id=fu_env["company"].id,
        lead_id=lead2.id,
        outreach_version="1.0.0",
        status=OutreachStatus.SENT,
        subject="Quick note",
        message="Hi Blake",
        cta="Call?",
        confidence=Decimal("0.5"),
        recipient_email="blake@acme.example",
        recipient_name="Blake",
        personalization_reasons=[{"reason": "name", "evidence_ids": ["lead.name"]}],
        evidence_used=[],
        evidence_catalog=[],
        input_snapshot={},
        sent_at=utc_now(),
    )
    fu_env["session"].add(outreach2)
    fu_env["session"].commit()
    seq2 = followups.ensure_sequence_started(outreach=outreach2, sent_at=utc_now())
    assert seq2 is not None
    followups.block_lead(lead2.id)
    fu_env["session"].refresh(seq2)
    assert seq2.stop_reason == FollowUpStopReason.BLOCKED
