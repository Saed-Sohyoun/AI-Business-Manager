"""FollowUpService — scheduling-safe follow-up cadence with approvals and stop rules.

Never mass-sends. Never follows up after reply / opt-out / customer / blocked.
Never sends without ApprovalService. Max follow-ups enforced via settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.sales.evidence import build_sales_evidence_catalog
from app.agents.sales.followup_composer import FOLLOWUP_VERSION, compose_followup_draft
from app.agents.sales.validation import validate_outreach_draft
from app.approvals.schemas import ApprovalRequest
from app.approvals.service import ApprovalService
from app.config import Settings, get_settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.models import (
    Company,
    CompanyAudit,
    CompanyScore,
    DailyMetric,
    FollowUpItem,
    FollowUpSequence,
    Lead,
    OutboundMessage,
    Outreach,
)
from app.models.base import utc_now
from app.models.enums import (
    ApprovalStatus,
    FollowUpItemStatus,
    FollowUpSequenceStatus,
    FollowUpStopReason,
    LeadStatus,
    OutreachStatus,
)
from app.services.follow_up_schemas import (
    FollowUpMetricsSnapshot,
    FollowUpProcessResult,
    FollowUpSequenceView,
)

if TYPE_CHECKING:
    from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

ACTION_SEND_FOLLOWUP = "sales.send_followup"


def _ensure_aware(value: datetime) -> datetime:
    """Normalize SQLite-naive datetimes to aware UTC for safe comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class _StopCheck:
    should_stop: bool
    reason: FollowUpStopReason


class FollowUpService:
    """Owns follow-up sequences, due processing, stop rules, and metrics."""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        approval_service: ApprovalService | None = None,
        email_service: EmailService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._approvals = approval_service or ApprovalService(session, settings)
        self._email_service = email_service

    def _get_email_service(self):
        if self._email_service is not None:
            return self._email_service
        from app.services.email_service import build_email_service

        return build_email_service(
            self._session,
            self._settings,
            approval_service=self._approvals,
        )

    # ------------------------------------------------------------------ start
    def ensure_sequence_started(
        self,
        *,
        outreach: Outreach,
        sent_at: datetime | None = None,
        outbound_message: OutboundMessage | None = None,
    ) -> FollowUpSequence | None:
        """Idempotently open a follow-up sequence after initial outreach is SENT."""
        if outbound_message is not None and outbound_message.is_followup:
            return None
        if outreach.status != OutreachStatus.SENT and outreach.sent_at is None:
            return None

        when = sent_at or outreach.sent_at or utc_now()
        key = f"followup-seq:outreach:{outreach.id}"
        existing = self._session.scalar(
            select(FollowUpSequence).where(FollowUpSequence.idempotency_key == key)
        )
        if existing is not None:
            return existing
        by_lead = self._session.scalar(
            select(FollowUpSequence).where(FollowUpSequence.lead_id == outreach.lead_id)
        )
        if by_lead is not None:
            return by_lead

        lead = self._session.get(Lead, outreach.lead_id)
        if lead is not None:
            lead.last_contacted_at = when
            if lead.status == LeadStatus.NEW:
                lead.status = LeadStatus.CONTACTED

        delay = self._delay_for_index(1)
        sequence = FollowUpSequence(
            lead_id=outreach.lead_id,
            company_id=outreach.company_id,
            initial_outreach_id=outreach.id,
            idempotency_key=key,
            initial_sent_at=when,
            follow_up_count=0,
            next_follow_up_at=when + delay,
            status=FollowUpSequenceStatus.ACTIVE,
            stop_reason=FollowUpStopReason.NONE,
            extra_metadata={
                "outbound_message_id": str(outbound_message.id) if outbound_message else None,
            },
        )
        try:
            with self._session.begin_nested():
                self._session.add(sequence)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(FollowUpSequence).where(FollowUpSequence.idempotency_key == key)
            )
            return existing

        stop = self._evaluate_stop(lead)
        if stop.should_stop:
            self._stop_sequence(sequence, stop.reason)
            self._session.flush()
            logger.info(
                "followup_sequence_started_stopped id=%s reason=%s",
                sequence.id,
                stop.reason.value,
            )
            return sequence

        logger.info(
            "followup_sequence_started id=%s lead_id=%s next_at=%s",
            sequence.id,
            outreach.lead_id,
            sequence.next_follow_up_at,
        )
        return sequence

    # --------------------------------------------------------------- process due
    def process_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 10,
    ) -> list[FollowUpProcessResult]:
        """Claim and draft due follow-ups one-at-a-time (scheduling-safe, no mass send)."""
        if limit < 1:
            return []
        # Pilot safety: never process more than daily outbound remaining conceptually
        limit = min(limit, max(1, self._settings.max_outbound_messages_per_day))

        clock = now or utc_now()
        results: list[FollowUpProcessResult] = []
        due_ids = list(
            self._session.scalars(
                select(FollowUpSequence.id)
                .where(
                    FollowUpSequence.status == FollowUpSequenceStatus.ACTIVE.value,
                    FollowUpSequence.next_follow_up_at.is_not(None),
                    FollowUpSequence.next_follow_up_at <= clock,
                    FollowUpSequence.follow_up_count < self._settings.max_followups,
                )
                .order_by(FollowUpSequence.next_follow_up_at.asc())
                .limit(limit)
            )
        )

        for sequence_id in due_ids:
            results.append(self._process_one_due(sequence_id, clock=clock))
        if results:
            self._session.commit()
        return results

    def _process_one_due(self, sequence_id: UUID, *, clock: datetime) -> FollowUpProcessResult:
        sequence = self._session.get(FollowUpSequence, sequence_id)
        if sequence is None:
            return FollowUpProcessResult(
                sequence_id=sequence_id,
                action="skipped_not_due",
                logs=["sequence_missing"],
            )

        status = _as_seq_status(sequence.status)
        if status != FollowUpSequenceStatus.ACTIVE:
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                action="skipped_not_due",
                logs=[f"status={status.value}"],
            )
        if sequence.next_follow_up_at is None or _ensure_aware(sequence.next_follow_up_at) > clock:
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                action="skipped_not_due",
                logs=["not_due"],
            )

        next_index = sequence.follow_up_count + 1
        if next_index > self._settings.max_followups:
            self._stop_sequence(sequence, FollowUpStopReason.MAX_FOLLOWUPS)
            sequence.status = FollowUpSequenceStatus.COMPLETED
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                action="max_reached",
                stop_reason=FollowUpStopReason.MAX_FOLLOWUPS.value,
            )

        lead = self._session.get(Lead, sequence.lead_id)
        stop = self._evaluate_stop(lead)
        if stop.should_stop:
            self._stop_sequence(sequence, stop.reason)
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                action="skipped_stopped",
                stop_reason=stop.reason.value,
                logs=["stop_rule"],
            )

        item_key = f"followup-item:{sequence.id}:{next_index}"
        existing_item = self._session.scalar(
            select(FollowUpItem).where(FollowUpItem.idempotency_key == item_key)
        )
        if existing_item is not None:
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                item_id=existing_item.id,
                action="skipped_duplicate",
                stop_reason=FollowUpStopReason.DUPLICATE.value,
                approval_id=existing_item.approval_id,
                outreach_id=existing_item.outreach_id,
                logs=["idempotent_item_exists"],
            )

        scheduled_for = sequence.next_follow_up_at or clock
        item = FollowUpItem(
            sequence_id=sequence.id,
            followup_index=next_index,
            idempotency_key=item_key,
            scheduled_for=scheduled_for,
            status=FollowUpItemStatus.SCHEDULED,
            claimed_at=clock,
            extra_metadata={},
        )
        try:
            with self._session.begin_nested():
                self._session.add(item)
                self._session.flush()
        except IntegrityError:
            dup = self._session.scalar(
                select(FollowUpItem).where(FollowUpItem.idempotency_key == item_key)
            )
            return FollowUpProcessResult(
                sequence_id=sequence_id,
                item_id=dup.id if dup else None,
                action="skipped_duplicate",
                stop_reason=FollowUpStopReason.DUPLICATE.value,
                logs=["unique_constraint_claim"],
            )

        # Re-check stop after claim (lead may have replied concurrently)
        lead = self._session.get(Lead, sequence.lead_id)
        stop = self._evaluate_stop(lead)
        if stop.should_stop:
            item.status = FollowUpItemStatus.SKIPPED
            item.skip_reason = stop.reason
            self._stop_sequence(sequence, stop.reason)
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                item_id=item.id,
                action="skipped_stopped",
                stop_reason=stop.reason.value,
                logs=["stop_after_claim"],
            )

        outreach = self._draft_followup_outreach(sequence, item)
        item.outreach_id = outreach.id
        item.status = FollowUpItemStatus.DRAFT_READY
        self._session.flush()

        try:
            approval_id = self._request_send_approval(item, outreach)
        except ForbiddenError as exc:
            item.status = FollowUpItemStatus.SKIPPED
            item.skip_reason = FollowUpStopReason.APPROVAL_MISSING
            item.error_message = exc.message[:2000]
            self._stop_sequence(sequence, FollowUpStopReason.APPROVAL_MISSING)
            return FollowUpProcessResult(
                sequence_id=sequence.id,
                item_id=item.id,
                action="approval_missing_stopped",
                stop_reason=FollowUpStopReason.APPROVAL_MISSING.value,
                outreach_id=outreach.id,
                logs=["approval_request_failed"],
            )

        item.approval_id = approval_id
        item.status = FollowUpItemStatus.PENDING_APPROVAL
        outreach.status = OutreachStatus.PENDING_APPROVAL
        outreach.approval_id = approval_id
        sequence.status = FollowUpSequenceStatus.WAITING_APPROVAL
        sequence.next_follow_up_at = None  # pause until send or stop
        self._session.flush()

        logger.info(
            "followup_drafted_pending_approval item=%s index=%s approval=%s",
            item.id,
            next_index,
            approval_id,
        )
        return FollowUpProcessResult(
            sequence_id=sequence.id,
            item_id=item.id,
            action="drafted_pending_approval",
            approval_id=approval_id,
            outreach_id=outreach.id,
            logs=["drafted", "approval_requested"],
        )

    # --------------------------------------------------------------- send
    def send_followup(self, item_id: UUID) -> OutboundMessage:
        """Send an approved follow-up via EmailService. Never bypasses approvals."""
        item = self._session.get(FollowUpItem, item_id)
        if item is None:
            raise ValidationAppError(
                "Follow-up item not found",
                details={"item_id": str(item_id)},
            )
        if (
            _as_item_status(item.status) == FollowUpItemStatus.SENT
            and item.outbound_message_id is not None
        ):
            existing = self._session.get(OutboundMessage, item.outbound_message_id)
            if existing is not None:
                return existing

        sequence = self._session.get(FollowUpSequence, item.sequence_id)
        if sequence is None:
            raise ValidationAppError(
                "Follow-up sequence not found",
                details={"sequence_id": str(item.sequence_id)},
            )

        lead = self._session.get(Lead, sequence.lead_id)
        stop = self._evaluate_stop(lead)
        if stop.should_stop:
            item.status = FollowUpItemStatus.SKIPPED
            item.skip_reason = stop.reason
            self._stop_sequence(sequence, stop.reason)
            self._session.commit()
            raise ForbiddenError(
                "Follow-up blocked by stop rule",
                details={"reason": stop.reason.value},
            )

        if item.approval_id is None:
            item.skip_reason = FollowUpStopReason.APPROVAL_MISSING
            item.status = FollowUpItemStatus.SKIPPED
            self._stop_sequence(sequence, FollowUpStopReason.APPROVAL_MISSING)
            self._session.commit()
            raise ForbiddenError(
                "Follow-up missing approval",
                details={"item_id": str(item_id)},
            )

        if item.outreach_id is None:
            raise ValidationAppError(
                "Follow-up has no outreach draft",
                details={"item_id": str(item_id)},
            )
        outreach = self._session.get(Outreach, item.outreach_id)
        if outreach is None:
            raise ValidationAppError(
                "Follow-up outreach draft missing",
                details={"outreach_id": str(item.outreach_id)},
            )

        from app.approvals.fingerprint import build_outbound_email_payload
        from app.services.outreach_body import compose_outreach_body

        body = compose_outreach_body(outreach)
        live_payload = build_outbound_email_payload(
            action_type=ACTION_SEND_FOLLOWUP,
            recipient_email=outreach.recipient_email or "",
            subject=outreach.subject,
            body_text=body,
            outreach_id=outreach.id,
            lead_id=sequence.lead_id,
            company_id=sequence.company_id,
            sender_from=(self._settings.email_from or "").strip(),
        )
        gate = self._approvals.evaluate_gate(
            ACTION_SEND_FOLLOWUP,
            approval_id=item.approval_id,
            action_payload=live_payload,
        )
        if not gate.may_execute:
            raise ForbiddenError(
                "Follow-up blocked by approval gate",
                details={
                    "decision": gate.decision,
                    "reason": gate.reason,
                    "approval_id": str(item.approval_id),
                },
            )
        approval = self._approvals.get_approval(item.approval_id)
        if approval.status != ApprovalStatus.APPROVED:
            raise ForbiddenError(
                "Follow-up requires an APPROVED approval",
                details={"status": approval.status.value},
            )

        # Cap: never exceed max follow-ups
        if sequence.follow_up_count >= self._settings.max_followups:
            self._stop_sequence(sequence, FollowUpStopReason.MAX_FOLLOWUPS)
            sequence.status = FollowUpSequenceStatus.COMPLETED
            item.status = FollowUpItemStatus.SKIPPED
            item.skip_reason = FollowUpStopReason.MAX_FOLLOWUPS
            self._session.commit()
            raise ForbiddenError(
                "Maximum follow-ups reached",
                details={"max_followups": self._settings.max_followups},
            )

        service = self._get_email_service()

        item.status = FollowUpItemStatus.SENDING
        self._session.flush()

        message = service.send(
            to_email=outreach.recipient_email or "",
            to_name=outreach.recipient_name,
            subject=outreach.subject,
            body_text=body,
            idempotency_key=item.idempotency_key,
            approval_id=item.approval_id,
            outreach_id=outreach.id,
            lead_id=sequence.lead_id,
            company_id=sequence.company_id,
            action_type=ACTION_SEND_FOLLOWUP,
            is_followup=True,
            metadata={
                "source": "follow_up",
                "followup_index": item.followup_index,
                "sequence_id": str(sequence.id),
                "item_id": str(item.id),
            },
        )

        item.outbound_message_id = message.id
        item.sent_at = message.sent_at or utc_now()
        item.status = FollowUpItemStatus.SENT
        sequence.follow_up_count = item.followup_index
        if lead is not None:
            lead.last_contacted_at = item.sent_at

        if sequence.follow_up_count >= self._settings.max_followups:
            sequence.status = FollowUpSequenceStatus.COMPLETED
            sequence.stop_reason = FollowUpStopReason.MAX_FOLLOWUPS
            sequence.next_follow_up_at = None
        else:
            sequence.status = FollowUpSequenceStatus.ACTIVE
            sequence.stop_reason = FollowUpStopReason.NONE
            sequence.next_follow_up_at = (item.sent_at or utc_now()) + self._delay_for_index(
                sequence.follow_up_count + 1
            )

        self._bump_daily_outreach_sent()
        self._session.commit()
        logger.info(
            "followup_sent item=%s index=%s cost=%s",
            item.id,
            item.followup_index,
            message.estimated_cost,
        )
        return message

    # --------------------------------------------------------------- events
    def record_reply(
        self,
        lead_id: UUID,
        *,
        meeting: bool = False,
        at: datetime | None = None,
    ) -> FollowUpSequence | None:
        """Stop the sequence when a lead replies; optionally count a meeting."""
        when = at or utc_now()
        lead = self._session.get(Lead, lead_id)
        if lead is None:
            raise ValidationAppError("Lead not found", details={"lead_id": str(lead_id)})
        lead.replied_at = when
        if lead.status not in {LeadStatus.CONVERTED, LeadStatus.DISQUALIFIED}:
            lead.status = LeadStatus.QUALIFIED

        sequence = self._session.scalar(
            select(FollowUpSequence).where(FollowUpSequence.lead_id == lead_id)
        )
        if sequence is None:
            self._session.commit()
            return None

        if not sequence.response_received:
            sequence.response_received = True
            sequence.response_at = when
            sequence.response_to_followup_index = sequence.follow_up_count
            self._bump_daily_replies()
        if meeting:
            sequence.meetings_generated += 1
            self._bump_daily_meetings(1)

        self._stop_sequence(sequence, FollowUpStopReason.REPLIED)
        self._cancel_open_items(sequence, FollowUpStopReason.REPLIED)
        self._session.commit()
        return sequence

    def record_opt_out(self, lead_id: UUID) -> FollowUpSequence | None:
        lead = self._session.get(Lead, lead_id)
        if lead is None:
            raise ValidationAppError("Lead not found", details={"lead_id": str(lead_id)})
        lead.opted_out = True
        sequence = self._stop_lead_sequence(lead_id, FollowUpStopReason.OPTED_OUT)
        self._session.commit()
        return sequence

    def block_lead(self, lead_id: UUID) -> FollowUpSequence | None:
        lead = self._session.get(Lead, lead_id)
        if lead is None:
            raise ValidationAppError("Lead not found", details={"lead_id": str(lead_id)})
        lead.blocked = True
        sequence = self._stop_lead_sequence(lead_id, FollowUpStopReason.BLOCKED)
        self._session.commit()
        return sequence

    def mark_customer(self, lead_id: UUID) -> FollowUpSequence | None:
        lead = self._session.get(Lead, lead_id)
        if lead is None:
            raise ValidationAppError("Lead not found", details={"lead_id": str(lead_id)})
        lead.status = LeadStatus.CONVERTED
        sequence = self._stop_lead_sequence(lead_id, FollowUpStopReason.BECAME_CUSTOMER)
        self._session.commit()
        return sequence

    # --------------------------------------------------------------- metrics
    def metrics(self) -> FollowUpMetricsSnapshot:
        initial_sent = int(
            self._session.scalar(select(func.count()).select_from(FollowUpSequence)) or 0
        )
        responses = int(
            self._session.scalar(
                select(func.count())
                .select_from(FollowUpSequence)
                .where(FollowUpSequence.response_received.is_(True))
            )
            or 0
        )
        followups_sent = int(
            self._session.scalar(
                select(func.count())
                .select_from(FollowUpItem)
                .where(FollowUpItem.status == FollowUpItemStatus.SENT.value)
            )
            or 0
        )
        followup_responses = int(
            self._session.scalar(
                select(func.count())
                .select_from(FollowUpSequence)
                .where(
                    FollowUpSequence.response_received.is_(True),
                    FollowUpSequence.response_to_followup_index.is_not(None),
                    FollowUpSequence.response_to_followup_index >= 1,
                )
            )
            or 0
        )
        meetings = int(
            self._session.scalar(
                select(func.coalesce(func.sum(FollowUpSequence.meetings_generated), 0))
            )
            or 0
        )
        return FollowUpMetricsSnapshot(
            initial_sent=initial_sent,
            responses=responses,
            response_rate=(responses / initial_sent) if initial_sent else 0.0,
            followups_sent=followups_sent,
            followup_responses=followup_responses,
            follow_up_response_rate=(followup_responses / followups_sent) if followups_sent else 0.0,
            meetings_generated=meetings,
        )

    def get_sequence(self, sequence_id: UUID) -> FollowUpSequenceView | None:
        seq = self._session.get(FollowUpSequence, sequence_id)
        if seq is None:
            return None
        return FollowUpSequenceView(
            id=seq.id,
            lead_id=seq.lead_id,
            company_id=seq.company_id,
            initial_outreach_id=seq.initial_outreach_id,
            initial_sent_at=seq.initial_sent_at,
            follow_up_count=seq.follow_up_count,
            next_follow_up_at=seq.next_follow_up_at,
            status=str(seq.status.value if isinstance(seq.status, FollowUpSequenceStatus) else seq.status),
            stop_reason=str(
                seq.stop_reason.value
                if isinstance(seq.stop_reason, FollowUpStopReason)
                else seq.stop_reason
            ),
            response_received=bool(seq.response_received),
            response_at=seq.response_at,
            meetings_generated=seq.meetings_generated,
            metadata=dict(seq.extra_metadata or {}),
        )

    # --------------------------------------------------------------- internals
    def _draft_followup_outreach(
        self,
        sequence: FollowUpSequence,
        item: FollowUpItem,
    ) -> Outreach:
        company = self._session.get(Company, sequence.company_id)
        lead = self._session.get(Lead, sequence.lead_id)
        initial = self._session.get(Outreach, sequence.initial_outreach_id)
        if company is None or lead is None or initial is None:
            raise ValidationAppError("Missing company, lead, or initial outreach for follow-up")

        score = self._session.scalar(
            select(CompanyScore)
            .where(CompanyScore.company_id == company.id)
            .order_by(CompanyScore.scored_at.desc())
            .limit(1)
        )
        audit = self._session.scalar(
            select(CompanyAudit)
            .where(CompanyAudit.company_id == company.id)
            .order_by(CompanyAudit.audited_at.desc())
            .limit(1)
        )
        catalog = build_sales_evidence_catalog(
            company=company, lead=lead, score=score, audit=audit
        )
        draft = compose_followup_draft(
            company=company,
            lead=lead,
            catalog=catalog,
            initial_outreach=initial,
            followup_index=item.followup_index,
        )
        website_verified = bool(audit and audit.website_available)
        draft = validate_outreach_draft(draft, catalog, website_verified=website_verified)

        outreach = Outreach(
            company_id=company.id,
            lead_id=lead.id,
            company_score_id=score.id if score else None,
            company_audit_id=audit.id if audit else None,
            status=OutreachStatus.DRAFT,
            outreach_version=FOLLOWUP_VERSION,
            subject=draft.subject,
            message=draft.message,
            cta=draft.cta,
            confidence=Decimal(str(draft.confidence)),
            recipient_email=lead.email or initial.recipient_email,
            recipient_name=lead.name,
            personalization_reasons=[r.model_dump() for r in draft.personalization_reasons],
            evidence_used=[
                item_e.model_dump()
                for item_e in catalog
                if item_e.evidence_id in set(draft.evidence_used)
            ],
            evidence_catalog=[c.model_dump() for c in catalog],
            input_snapshot={
                "followup_index": item.followup_index,
                "initial_outreach_id": str(initial.id),
                "sequence_id": str(sequence.id),
            },
            drafted_at=utc_now(),
            extra_metadata={
                "is_followup": True,
                "followup_index": item.followup_index,
                "send_attempted": False,
            },
        )
        self._session.add(outreach)
        self._session.flush()
        return outreach

    def _request_send_approval(self, item: FollowUpItem, outreach: Outreach) -> UUID:
        gate = self._approvals.evaluate_gate(ACTION_SEND_FOLLOWUP)
        if gate.decision != "require_approval":
            raise ForbiddenError(
                "Follow-up send path misconfigured — expected YELLOW require_approval",
                details={"decision": gate.decision},
            )
        from app.approvals.fingerprint import build_outbound_email_payload
        from app.services.outreach_body import compose_outreach_body

        body = compose_outreach_body(outreach)
        payload = build_outbound_email_payload(
            action_type=ACTION_SEND_FOLLOWUP,
            recipient_email=outreach.recipient_email or "",
            subject=outreach.subject,
            body_text=body,
            outreach_id=outreach.id,
            lead_id=outreach.lead_id,
            company_id=outreach.company_id,
            sender_from=(self._settings.email_from or "").strip(),
        )
        view = self._approvals.request_approval(
            ApprovalRequest(
                action_type=ACTION_SEND_FOLLOWUP,
                description=(
                    f"Approve follow-up #{item.followup_index} for outreach {outreach.id}"
                ),
                requested_by="follow_up",
                action_payload=payload,
                metadata={
                    "followup_item_id": str(item.id),
                    "sequence_id": str(item.sequence_id),
                },
            )
        )
        return view.id

    def _evaluate_stop(self, lead: Lead | None) -> _StopCheck:
        if lead is None:
            return _StopCheck(True, FollowUpStopReason.BLOCKED)
        if lead.opted_out:
            return _StopCheck(True, FollowUpStopReason.OPTED_OUT)
        if lead.blocked:
            return _StopCheck(True, FollowUpStopReason.BLOCKED)
        if lead.replied_at is not None:
            return _StopCheck(True, FollowUpStopReason.REPLIED)
        status = lead.status if isinstance(lead.status, LeadStatus) else LeadStatus(lead.status)
        if status == LeadStatus.CONVERTED:
            return _StopCheck(True, FollowUpStopReason.BECAME_CUSTOMER)
        return _StopCheck(False, FollowUpStopReason.NONE)

    def _stop_sequence(self, sequence: FollowUpSequence, reason: FollowUpStopReason) -> None:
        sequence.status = FollowUpSequenceStatus.STOPPED
        sequence.stop_reason = reason
        sequence.next_follow_up_at = None

    def _stop_lead_sequence(
        self,
        lead_id: UUID,
        reason: FollowUpStopReason,
    ) -> FollowUpSequence | None:
        sequence = self._session.scalar(
            select(FollowUpSequence).where(FollowUpSequence.lead_id == lead_id)
        )
        if sequence is None:
            return None
        self._stop_sequence(sequence, reason)
        self._cancel_open_items(sequence, reason)
        return sequence

    def _cancel_open_items(
        self,
        sequence: FollowUpSequence,
        reason: FollowUpStopReason,
    ) -> None:
        open_statuses = {
            FollowUpItemStatus.SCHEDULED.value,
            FollowUpItemStatus.DRAFT_READY.value,
            FollowUpItemStatus.PENDING_APPROVAL.value,
            FollowUpItemStatus.APPROVED.value,
        }
        items = self._session.scalars(
            select(FollowUpItem).where(
                FollowUpItem.sequence_id == sequence.id,
                FollowUpItem.status.in_(list(open_statuses)),
            )
        )
        for item in items:
            item.status = FollowUpItemStatus.CANCELLED
            item.skip_reason = reason

    def _delay_for_index(self, followup_index: int) -> timedelta:
        if followup_index <= 1:
            days = self._settings.followup_delay_days_first
        else:
            days = self._settings.followup_delay_days_second
        # Non-aggressive: at least 1 day between touches
        return timedelta(days=max(1, days))

    def _today_metric(self) -> DailyMetric:
        today = utc_now().date()
        row = self._session.scalar(
            select(DailyMetric).where(DailyMetric.metric_date == today)
        )
        if row is None:
            row = DailyMetric(metric_date=today)
            self._session.add(row)
            self._session.flush()
        return row

    def _bump_daily_outreach_sent(self) -> None:
        metric = self._today_metric()
        metric.outreach_sent = int(metric.outreach_sent or 0) + 1

    def _bump_daily_replies(self) -> None:
        metric = self._today_metric()
        metric.replies = int(metric.replies or 0) + 1

    def _bump_daily_meetings(self, n: int) -> None:
        metric = self._today_metric()
        metric.meetings = int(metric.meetings or 0) + n


def _as_seq_status(value: FollowUpSequenceStatus | str) -> FollowUpSequenceStatus:
    if isinstance(value, FollowUpSequenceStatus):
        return value
    return FollowUpSequenceStatus(value)


def _as_item_status(value: FollowUpItemStatus | str) -> FollowUpItemStatus:
    if isinstance(value, FollowUpItemStatus):
        return value
    return FollowUpItemStatus(value)


def build_follow_up_service(
    session: Session,
    settings: Settings | None = None,
    *,
    approval_service: ApprovalService | None = None,
    email_service: EmailService | None = None,
) -> FollowUpService:
    return FollowUpService(
        session=session,
        settings=settings or get_settings(),
        approval_service=approval_service,
        email_service=email_service,
    )
