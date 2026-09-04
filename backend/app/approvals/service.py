"""ApprovalService — request, gate, and enforce approvals. No bypass."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.policy import ApprovalPolicy, normalize_action_type
from app.approvals.schemas import (
    ApprovalEventView,
    ApprovalRequest,
    ApprovalView,
    GateDecision,
)
from app.config import Settings
from app.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models import Approval, ApprovalEvent
from app.models.approval import TERMINAL_APPROVAL_STATUSES
from app.models.base import utc_now
from app.models.enums import ApprovalStatus, RiskLevel

logger = logging.getLogger(__name__)


def _as_status(value: ApprovalStatus | str) -> ApprovalStatus:
    return value if isinstance(value, ApprovalStatus) else ApprovalStatus(value)


def _as_risk(value: RiskLevel | str) -> RiskLevel:
    return value if isinstance(value, RiskLevel) else RiskLevel(value)


def compute_fingerprint(
    *,
    action_type: str,
    action_payload: dict[str, Any],
    manager_task_id: UUID | None = None,
) -> str:
    payload = json.dumps(action_payload, sort_keys=True, default=str)
    task = str(manager_task_id) if manager_task_id else ""
    raw = f"{normalize_action_type(action_type)}|{task}|{payload}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ApprovalService:
    """Persistent, auditable approval gate. Agents cannot bypass this service."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        policy: ApprovalPolicy | None = None,
        *,
        clock: Any | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._policy = policy or ApprovalPolicy()
        self._clock = clock or utc_now

    @property
    def policy(self) -> ApprovalPolicy:
        return self._policy

    def evaluate_gate(
        self,
        action_type: str,
        *,
        approval_id: UUID | None = None,
    ) -> GateDecision:
        """Decide whether an action may proceed. Always consults live DB state."""
        action = normalize_action_type(action_type)
        entry = self._policy.get_entry(action)
        risk = entry.risk_level

        if risk == RiskLevel.GREEN:
            return GateDecision(
                decision="allow_auto",
                action_type=action,
                risk_level=risk,
                reason="GREEN actions execute automatically",
                may_execute=True,
            )

        if risk == RiskLevel.RED:
            # Human-only: agents never execute, even with an approved record.
            return GateDecision(
                decision="human_only",
                action_type=action,
                risk_level=risk,
                reason="RED actions are human-only; agents cannot execute",
                approval_id=approval_id,
                may_execute=False,
            )

        # YELLOW
        if approval_id is None:
            return GateDecision(
                decision="require_approval",
                action_type=action,
                risk_level=risk,
                reason="YELLOW actions require an approved Approval record",
                may_execute=False,
            )

        approval = self._get_or_raise(approval_id)
        self.expire_if_due(approval)
        status = _as_status(approval.status)

        if status == ApprovalStatus.APPROVED:
            if normalize_action_type(approval.action_type) != action:
                return GateDecision(
                    decision="deny",
                    action_type=action,
                    risk_level=risk,
                    reason="approval action_type mismatch — bypass blocked",
                    approval_id=approval_id,
                    may_execute=False,
                )
            return GateDecision(
                decision="allow_auto",
                action_type=action,
                risk_level=risk,
                reason="YELLOW action approved",
                approval_id=approval_id,
                may_execute=True,
            )

        if status == ApprovalStatus.PENDING:
            return GateDecision(
                decision="require_approval",
                action_type=action,
                risk_level=risk,
                reason="approval still pending",
                approval_id=approval_id,
                may_execute=False,
            )

        return GateDecision(
            decision="deny",
            action_type=action,
            risk_level=risk,
            reason=f"approval status={status.value} blocks execution",
            approval_id=approval_id,
            may_execute=False,
        )

    def assert_executable(self, action_type: str, *, approval_id: UUID | None = None) -> GateDecision:
        """Hard gate — raises ForbiddenError if execution would bypass approvals."""
        decision = self.evaluate_gate(action_type, approval_id=approval_id)
        if not decision.may_execute:
            raise ForbiddenError(
                "Action blocked by approval gate",
                details={
                    "action_type": decision.action_type,
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "approval_id": str(approval_id) if approval_id else None,
                },
            )
        return decision

    def request_approval(self, request: ApprovalRequest) -> ApprovalView:
        action = normalize_action_type(request.action_type)
        policy_entry = self._policy.get_entry(action)
        risk = request.risk_level or policy_entry.risk_level
        if request.risk_level is not None and _as_risk(request.risk_level) != policy_entry.risk_level:
            # Callers cannot under-classify risk to bypass policy
            raise ForbiddenError(
                "Cannot override policy risk level downward or mismatch",
                details={
                    "requested": str(request.risk_level),
                    "policy": policy_entry.risk_level.value,
                },
            )

        if risk == RiskLevel.GREEN:
            raise ValidationAppError(
                "GREEN actions do not create approval requests",
                details={"action_type": action},
            )

        fingerprint = request.fingerprint or compute_fingerprint(
            action_type=action,
            action_payload=request.action_payload,
            manager_task_id=request.manager_task_id,
        )

        existing = self._find_pending_by_fingerprint(fingerprint)
        if existing is not None:
            self.expire_if_due(existing)
            if _as_status(existing.status) == ApprovalStatus.PENDING:
                self._append_event(
                    existing,
                    event_type="duplicate_request",
                    actor=request.requested_by,
                    detail="Duplicate approval request ignored; returning existing pending approval",
                    metadata={"requested_action": action},
                )
                self._session.flush()
                raise ConflictError(
                    "Duplicate pending approval exists",
                    details={
                        "approval_id": str(existing.id),
                        "fingerprint": fingerprint,
                    },
                )

        ttl = request.expires_in_seconds or self._settings.approval_default_ttl_seconds
        now = self._now()
        approval = Approval(
            action_type=action,
            description=request.description,
            risk_level=risk,
            status=ApprovalStatus.PENDING,
            fingerprint=fingerprint,
            action_payload=dict(request.action_payload or {}),
            requested_by=request.requested_by,
            requested_at=now,
            expires_at=now + timedelta(seconds=ttl),
            manager_run_id=request.manager_run_id,
            manager_task_id=request.manager_task_id,
            agent_run_id=request.agent_run_id,
            extra_metadata=dict(request.metadata or {}),
        )
        self._session.add(approval)
        self._session.flush()
        self._append_event(
            approval,
            event_type="requested",
            actor=request.requested_by,
            detail=f"Approval requested for {action} ({risk.value})",
            metadata={"fingerprint": fingerprint},
        )
        self._session.flush()
        logger.info(
            "Approval requested id=%s action=%s risk=%s by=%s",
            approval.id,
            action,
            risk.value,
            request.requested_by,
        )
        # Best-effort owner alert — never blocks approval creation; no-op if Telegram unset.
        try:
            from app.services.notification_service import build_notification_service

            build_notification_service(self._session, self._settings).notify_approval_request(
                approval_id=approval.id,
                action_type=action,
                risk_level=risk.value,
                description=request.description,
            )
        except Exception:  # noqa: BLE001
            logger.debug("approval_notification_skipped", exc_info=True)
        return self._to_view(approval)

    def get_approval(self, approval_id: UUID) -> ApprovalView:
        approval = self._get_or_raise(approval_id)
        self.expire_if_due(approval)
        return self._to_view(approval)

    def list_pending(self, *, limit: int = 50) -> list[ApprovalView]:
        """List pending approvals after expiring due ones. Never auto-approves."""
        self.expire_due_approvals()
        capped = max(1, min(limit, 200))
        rows = self._session.scalars(
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING.value)
            .order_by(Approval.requested_at.asc())
            .limit(capped)
        ).all()
        return [self._to_view(row) for row in rows]

    def list_events(self, approval_id: UUID) -> list[ApprovalEventView]:
        self._get_or_raise(approval_id)
        rows = self._session.scalars(
            select(ApprovalEvent)
            .where(ApprovalEvent.approval_id == approval_id)
            .order_by(ApprovalEvent.created_at.asc())
        ).all()
        return [
            ApprovalEventView(
                id=e.id,
                approval_id=e.approval_id,
                event_type=e.event_type,
                actor=e.actor,
                detail=e.detail,
                created_at=e.created_at,
                metadata=e.extra_metadata or {},
            )
            for e in rows
        ]

    def expire_if_due(self, approval: Approval) -> bool:
        status = _as_status(approval.status)
        if status != ApprovalStatus.PENDING:
            return False
        if approval.expires_at is None:
            return False
        if self._now() < _ensure_aware(approval.expires_at):
            return False
        self._set_terminal(
            approval,
            status=ApprovalStatus.EXPIRED,
            resolved_by="system",
            note="Approval expired",
            event_type="expired",
        )
        return True

    def expire_due_approvals(self) -> int:
        pending = self._session.scalars(
            select(Approval).where(Approval.status == ApprovalStatus.PENDING.value)
        ).all()
        count = 0
        for approval in pending:
            if self.expire_if_due(approval):
                count += 1
        return count

    def guard_mutation(self, approval: Approval) -> None:
        """Block mutation of terminal approvals (immutability)."""
        if _as_status(approval.status) in TERMINAL_APPROVAL_STATUSES and approval.resolved_at:
            raise ConflictError(
                "Resolved approvals are immutable",
                details={"approval_id": str(approval.id), "status": str(approval.status)},
            )

    # --- internals used by resolver --------------------------------------

    def _set_terminal(
        self,
        approval: Approval,
        *,
        status: ApprovalStatus,
        resolved_by: str,
        note: str | None,
        event_type: str,
    ) -> Approval:
        current = _as_status(approval.status)
        if current in TERMINAL_APPROVAL_STATUSES:
            raise ConflictError(
                "Approval already resolved and is immutable",
                details={"approval_id": str(approval.id), "status": current.value},
            )
        approval.status = status
        approval.resolved_by = resolved_by
        approval.resolved_at = self._now()
        approval.resolution_note = note
        self._append_event(
            approval,
            event_type=event_type,
            actor=resolved_by,
            detail=note or event_type,
            metadata={"status": status.value},
        )
        self._session.flush()
        return approval

    def _append_event(
        self,
        approval: Approval,
        *,
        event_type: str,
        actor: str,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalEvent:
        event = ApprovalEvent(
            approval_id=approval.id,
            event_type=event_type,
            actor=actor,
            detail=detail[:4000],
            extra_metadata=metadata or {},
        )
        self._session.add(event)
        return event

    def _get_or_raise(self, approval_id: UUID) -> Approval:
        approval = self._session.get(Approval, approval_id)
        if approval is None:
            raise NotFoundError("Approval not found", details={"approval_id": str(approval_id)})
        return approval

    def _find_pending_by_fingerprint(self, fingerprint: str) -> Approval | None:
        return self._session.scalar(
            select(Approval).where(
                Approval.fingerprint == fingerprint,
                Approval.status == ApprovalStatus.PENDING.value,
            )
        )

    def _now(self) -> datetime:
        value = self._clock()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return utc_now()

    def _to_view(self, approval: Approval) -> ApprovalView:
        return ApprovalView(
            id=approval.id,
            action_type=approval.action_type,
            description=approval.description,
            risk_level=_as_risk(approval.risk_level),
            status=_as_status(approval.status),
            fingerprint=approval.fingerprint,
            requested_by=approval.requested_by,
            requested_at=approval.requested_at,
            resolved_by=approval.resolved_by,
            resolved_at=approval.resolved_at,
            resolution_note=approval.resolution_note,
            expires_at=approval.expires_at,
            action_payload=approval.action_payload or {},
            manager_run_id=approval.manager_run_id,
            manager_task_id=approval.manager_task_id,
            agent_run_id=approval.agent_run_id,
            metadata=approval.extra_metadata or {},
        )
