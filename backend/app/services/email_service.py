"""EmailService — application-facing outbound email over EmailProvider.

Enforces ApprovalService, idempotency, daily rate limits, and follow-up caps.
Never mass-sends. Never bypasses approvals. Business code must not import Resend.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approvals.service import ApprovalService
from app.config import Settings, get_settings
from app.exceptions import ForbiddenError
from app.models import OutboundMessage, Outreach
from app.models.base import utc_now
from app.models.enums import ApprovalStatus, OutboundMessageStatus, OutreachStatus
from app.providers.email.base import EmailProvider
from app.providers.email.exceptions import (
    EmailConfigurationError,
    EmailIdempotencyError,
    EmailRateLimitError,
    EmailValidationError,
)
from app.providers.email.recipient import normalize_and_validate_recipient, normalize_from_address
from app.providers.email.resend_provider import ResendEmailProvider
from app.providers.email.types import EmailAddress, EmailSendRequest, EmailSendResponse

logger = logging.getLogger(__name__)

# Statuses that mean "already in flight or done" — never send again for same key
_BLOCKING_STATUSES = frozenset(
    {
        OutboundMessageStatus.QUEUED,
        OutboundMessageStatus.SENDING,
        OutboundMessageStatus.SENT,
    }
)


class EmailService:
    """High-level email operations with safety, approvals, and idempotency."""

    def __init__(
        self,
        provider: EmailProvider,
        *,
        session: Session,
        settings: Settings,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._provider = provider
        self._session = session
        self._settings = settings
        self._approvals = approval_service or ApprovalService(session, settings)

    @property
    def provider(self) -> EmailProvider:
        return self._provider

    def is_configured(self) -> bool:
        return self._provider.is_configured() and bool(self._settings.email_from)

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        idempotency_key: str,
        approval_id: UUID,
        to_name: str | None = None,
        body_html: str | None = None,
        outreach_id: UUID | None = None,
        lead_id: UUID | None = None,
        company_id: UUID | None = None,
        action_type: str = "sales.send_outreach",
        is_followup: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> OutboundMessage:
        """Send one email after approval, rate limits, and idempotency checks."""
        # 1) Approval gate — never bypass
        gate = self._approvals.evaluate_gate(action_type, approval_id=approval_id)
        if not gate.may_execute:
            raise ForbiddenError(
                "Outbound email blocked by approval gate",
                details={
                    "decision": gate.decision,
                    "reason": gate.reason,
                    "approval_id": str(approval_id),
                    "action_type": action_type,
                },
            )
        approval = self._approvals.get_approval(approval_id)
        if approval.status != ApprovalStatus.APPROVED:
            raise ForbiddenError(
                "Outbound email requires an APPROVED approval",
                details={"status": approval.status.value},
            )

        # 2) Recipient + from validation
        recipient = normalize_and_validate_recipient(to_email, name=to_name)
        from_email = normalize_from_address(self._settings.email_from or "")

        # 3) Idempotency — same key must never send twice
        existing = self._find_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._handle_existing(existing)

        if outreach_id is not None:
            already = self._find_sent_or_inflight_for_outreach(outreach_id)
            if already is not None:
                raise EmailIdempotencyError(
                    "This outreach was already sent or is in flight",
                    details={
                        "outreach_id": str(outreach_id),
                        "outbound_message_id": str(already.id),
                        "status": str(already.status),
                    },
                )

        # 4) Daily rate limit (pilot: initial outreach + total outbound)
        from app.exceptions import LimitReachedError
        from app.pilot.limits import LimitService

        limit_svc = LimitService(self._session, self._settings)
        sent_today = self._count_outbound_today()
        if sent_today >= self._settings.max_outbound_messages_per_day:
            raise EmailRateLimitError(
                "Daily outbound email limit reached",
                details={
                    "sent_today": sent_today,
                    "limit": self._settings.max_outbound_messages_per_day,
                },
            )

        # Determine follow-up vs initial before applying pilot initial-outreach cap
        will_be_followup = False
        if lead_id is not None:
            prior = self._count_sent_for_lead(lead_id)
            will_be_followup = prior > 0

        if not will_be_followup and not is_followup:
            try:
                limit_svc.assert_initial_outreach()
            except LimitReachedError as exc:
                raise EmailRateLimitError(exc.message, details=exc.details) from exc

        # 5) Follow-up cap per lead
        if lead_id is not None:
            prior = self._count_sent_for_lead(lead_id)
            # First message: prior==0. Follow-ups: prior >= 1, allow up to max_followups follow-ups
            if prior == 0:
                is_followup = False
                followup_index = 0
            else:
                is_followup = True
                followup_index = prior  # 1st follow-up when prior==1
                try:
                    limit_svc.assert_followups_for_lead(lead_id)
                except LimitReachedError as exc:
                    raise EmailRateLimitError(exc.message, details=exc.details) from exc
                if followup_index > self._settings.max_followups:
                    raise EmailRateLimitError(
                        "Maximum follow-ups for this lead reached",
                        details={
                            "lead_id": str(lead_id),
                            "prior_sent": prior,
                            "max_followups": self._settings.max_followups,
                        },
                    )
        else:
            followup_index = 1 if is_followup else 0

        if not self.is_configured():
            raise EmailConfigurationError(
                "Email provider or EMAIL_FROM is not configured",
            )

        message = OutboundMessage(
            outreach_id=outreach_id,
            lead_id=lead_id,
            company_id=company_id,
            approval_id=approval_id,
            status=OutboundMessageStatus.APPROVED,
            idempotency_key=idempotency_key,
            to_email=recipient.email,
            to_name=recipient.name,
            from_email=from_email,
            subject=subject.strip(),
            body_text=body_text,
            body_html=body_html,
            provider=self._provider.name,
            is_followup=is_followup,
            followup_index=followup_index,
            max_attempts=self._settings.resend_max_retries + 1,
            extra_metadata=dict(metadata or {}),
        )
        self._session.add(message)
        self._session.flush()

        if outreach_id is not None:
            self._sync_outreach_status(outreach_id, OutreachStatus.APPROVED)

        return self._dispatch(message)

    def send_outreach(self, outreach_id: UUID) -> OutboundMessage:
        """Send a drafted outreach that already has an approved approval_id."""
        outreach = self._session.get(Outreach, outreach_id)
        if outreach is None:
            raise EmailValidationError(
                "Outreach not found",
                details={"outreach_id": str(outreach_id)},
            )
        if not outreach.recipient_email:
            raise EmailValidationError(
                "Outreach has no recipient email",
                details={"outreach_id": str(outreach_id)},
            )
        if outreach.approval_id is None:
            raise ForbiddenError(
                "Outreach has no approval_id — request approval before sending",
                details={"outreach_id": str(outreach_id)},
            )
        if outreach.status in {
            OutreachStatus.SENT,
            OutreachStatus.SENDING,
            OutreachStatus.QUEUED,
        }:
            existing = self._find_sent_or_inflight_for_outreach(outreach_id)
            if existing is not None:
                return self._handle_existing(existing)
            raise EmailIdempotencyError(
                "Outreach already marked as sent/in-flight",
                details={"outreach_id": str(outreach_id), "status": str(outreach.status)},
            )

        body = outreach.message
        if outreach.cta and outreach.cta not in body:
            body = f"{body}\n\n{outreach.cta}"

        return self.send(
            to_email=outreach.recipient_email,
            to_name=outreach.recipient_name,
            subject=outreach.subject,
            body_text=body,
            idempotency_key=f"outreach-send:{outreach.id}",
            approval_id=outreach.approval_id,
            outreach_id=outreach.id,
            lead_id=outreach.lead_id,
            company_id=outreach.company_id,
            action_type="sales.send_outreach",
            metadata={"source": "outreach"},
        )

    def _dispatch(self, message: OutboundMessage) -> OutboundMessage:
        message.status = OutboundMessageStatus.QUEUED
        message.queued_at = utc_now()
        if message.outreach_id:
            self._sync_outreach_status(message.outreach_id, OutreachStatus.QUEUED)
        self._session.flush()

        message.status = OutboundMessageStatus.SENDING
        message.sending_at = utc_now()
        message.attempt_count += 1
        if message.outreach_id:
            self._sync_outreach_status(message.outreach_id, OutreachStatus.SENDING)
        self._session.flush()

        try:
            response = self._provider.send(
                EmailSendRequest(
                    to=EmailAddress(email=message.to_email, name=message.to_name),
                    subject=message.subject,
                    body_text=message.body_text,
                    body_html=message.body_html,
                    from_email=message.from_email,
                    idempotency_key=message.idempotency_key,
                    metadata={"outbound_message_id": str(message.id)},
                )
            )
            self._mark_sent(message, response)
            self._session.commit()
            return message
        except Exception as exc:  # noqa: BLE001
            message.status = OutboundMessageStatus.FAILED
            message.failed_at = utc_now()
            message.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            if message.outreach_id:
                self._sync_outreach_status(message.outreach_id, OutreachStatus.FAILED)
            self._session.commit()
            raise

    def _mark_sent(self, message: OutboundMessage, response: EmailSendResponse) -> None:
        message.status = OutboundMessageStatus.SENT
        message.sent_at = utc_now()
        message.provider_message_id = response.provider_message_id
        message.delivery_status = response.delivery_status
        message.estimated_cost = response.estimated_cost or Decimal("0")
        message.attempt_count = max(message.attempt_count, response.attempts)
        message.extra_metadata = {
            **(message.extra_metadata or {}),
            "provider": response.provider,
            "latency_ms": response.latency_ms,
        }
        if message.outreach_id:
            outreach = self._session.get(Outreach, message.outreach_id)
            if outreach is not None:
                outreach.status = OutreachStatus.SENT
                outreach.sent_at = message.sent_at
                outreach.extra_metadata = {
                    **(outreach.extra_metadata or {}),
                    "send_attempted": True,
                    "resend_connected": True,
                    "outbound_message_id": str(message.id),
                    "provider_message_id": response.provider_message_id,
                }
                if not message.is_followup:
                    from app.services.follow_up_service import FollowUpService

                    FollowUpService(
                        session=self._session,
                        settings=self._settings,
                        approval_service=self._approvals,
                    ).ensure_sequence_started(
                        outreach=outreach,
                        sent_at=message.sent_at,
                        outbound_message=message,
                    )
        logger.info(
            "outbound_email_sent id=%s outreach_id=%s cost=%s",
            message.id,
            message.outreach_id,
            message.estimated_cost,
        )

    def _handle_existing(self, existing: OutboundMessage) -> OutboundMessage:
        status = (
            existing.status
            if isinstance(existing.status, OutboundMessageStatus)
            else OutboundMessageStatus(existing.status)
        )
        if status == OutboundMessageStatus.SENT:
            logger.info(
                "outbound_email_idempotent_replay id=%s key=%s",
                existing.id,
                existing.idempotency_key,
            )
            return existing
        if status in {OutboundMessageStatus.QUEUED, OutboundMessageStatus.SENDING}:
            raise EmailIdempotencyError(
                "Outbound email already in flight for this idempotency key",
                details={
                    "outbound_message_id": str(existing.id),
                    "status": status.value,
                },
            )
        if status == OutboundMessageStatus.FAILED:
            # Do not auto-resend failed with same key — caller must use a new key intentionally
            raise EmailIdempotencyError(
                "Outbound email previously failed for this idempotency key; "
                "refusing automatic resend to prevent duplicates",
                details={
                    "outbound_message_id": str(existing.id),
                    "status": status.value,
                },
            )
        raise EmailIdempotencyError(
            "Outbound email already exists for this idempotency key",
            details={
                "outbound_message_id": str(existing.id),
                "status": status.value,
            },
        )

    def _find_by_idempotency_key(self, key: str) -> OutboundMessage | None:
        return self._session.scalar(
            select(OutboundMessage).where(OutboundMessage.idempotency_key == key)
        )

    def _find_sent_or_inflight_for_outreach(self, outreach_id: UUID) -> OutboundMessage | None:
        return self._session.scalar(
            select(OutboundMessage)
            .where(
                OutboundMessage.outreach_id == outreach_id,
                OutboundMessage.status.in_(
                    [
                        OutboundMessageStatus.QUEUED.value,
                        OutboundMessageStatus.SENDING.value,
                        OutboundMessageStatus.SENT.value,
                    ]
                ),
            )
            .limit(1)
        )

    def _count_outbound_today(self) -> int:
        now = utc_now()
        start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(OutboundMessage)
                .where(
                    OutboundMessage.status.in_(
                        [
                            OutboundMessageStatus.SENT.value,
                            OutboundMessageStatus.SENDING.value,
                            OutboundMessageStatus.QUEUED.value,
                        ]
                    ),
                    OutboundMessage.created_at >= start,
                )
            )
            or 0
        )

    def _count_sent_for_lead(self, lead_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(OutboundMessage)
                .where(
                    OutboundMessage.lead_id == lead_id,
                    OutboundMessage.status == OutboundMessageStatus.SENT.value,
                )
            )
            or 0
        )

    def _sync_outreach_status(self, outreach_id: UUID, status: OutreachStatus) -> None:
        outreach = self._session.get(Outreach, outreach_id)
        if outreach is not None:
            outreach.status = status


def build_email_service(
    session: Session,
    settings: Settings | None = None,
    *,
    provider: EmailProvider | None = None,
    approval_service: ApprovalService | None = None,
) -> EmailService:
    cfg = settings or get_settings()
    return EmailService(
        provider or ResendEmailProvider(cfg),
        session=session,
        settings=cfg,
        approval_service=approval_service,
    )
