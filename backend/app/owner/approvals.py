"""Owner approval resolution with row locking and security events."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.resolver import ApprovalResolver
from app.approvals.schemas import ResolveApprovalRequest
from app.approvals.service import ApprovalService, _as_status
from app.config import Settings
from app.exceptions import ConflictError, ValidationAppError
from app.models import Approval
from app.models.enums import ApprovalStatus
from app.owner.presentation import present_approval
from app.owner.schemas import ApprovalDecisionView
from app.security.events import APPROVAL_APPROVED, APPROVAL_REJECTED, record_security_event

logger = logging.getLogger(__name__)


class OwnerApprovalService:
    """Owner-facing approval read/resolve with concurrency-safe terminal writes."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._service = ApprovalService(session, settings)
        self._resolver = ApprovalResolver(session, settings, self._service)

    def list_approvals(self, *, limit: int = 50, status: str | None = None) -> list[ApprovalDecisionView]:
        self._service.expire_due_approvals()
        capped = max(1, min(limit, 200))
        stmt = select(Approval).order_by(Approval.requested_at.desc()).limit(capped)
        if status:
            stmt = (
                select(Approval)
                .where(Approval.status == status)
                .order_by(Approval.requested_at.desc())
                .limit(capped)
            )
        rows = self._session.scalars(stmt).all()
        return [present_approval(self._service._to_view(row)) for row in rows]

    def get_approval(self, approval_id: UUID) -> ApprovalDecisionView:
        view = self._service.get_approval(approval_id)
        return present_approval(view)

    def approve(
        self,
        approval_id: UUID,
        *,
        owner_id: str,
        note: str | None = None,
        request_id: str | None = None,
    ) -> ApprovalDecisionView:
        approval = self._lock_approval(approval_id)
        self._service.expire_if_due(approval)
        status = _as_status(approval.status)
        if status == ApprovalStatus.EXPIRED:
            raise ValidationAppError(
                "Cannot approve an expired approval",
                details={"approval_id": str(approval_id)},
            )
        if status == ApprovalStatus.CANCELLED:
            raise ConflictError(
                "Cannot approve a cancelled approval",
                details={"approval_id": str(approval_id), "status": status.value},
            )
        if status == ApprovalStatus.REJECTED:
            raise ConflictError(
                "Cannot approve an already-rejected approval",
                details={"approval_id": str(approval_id)},
            )
        if status == ApprovalStatus.APPROVED:
            # Idempotent — same terminal outcome
            return present_approval(self._service._to_view(approval))
        if status != ApprovalStatus.PENDING:
            raise ConflictError(
                "Approval is not pending",
                details={"approval_id": str(approval_id), "status": status.value},
            )

        self._service._set_terminal(
            approval,
            status=ApprovalStatus.APPROVED,
            resolved_by=owner_id,
            note=note or "Approved by owner",
            event_type="approved",
        )
        record_security_event(
            self._session,
            event_type=APPROVAL_APPROVED,
            reason=note or "approved",
            correlation_id=request_id,
            details={"actor": owner_id, "approval_id": str(approval_id)},
        )
        self._session.commit()
        return present_approval(self._service._to_view(approval))

    def reject(
        self,
        approval_id: UUID,
        *,
        owner_id: str,
        note: str | None = None,
        request_id: str | None = None,
    ) -> ApprovalDecisionView:
        approval = self._lock_approval(approval_id)
        self._service.expire_if_due(approval)
        status = _as_status(approval.status)
        if status == ApprovalStatus.EXPIRED:
            raise ValidationAppError(
                "Cannot reject an expired approval",
                details={"approval_id": str(approval_id)},
            )
        if status == ApprovalStatus.REJECTED:
            return present_approval(self._service._to_view(approval))
        if status == ApprovalStatus.APPROVED:
            raise ConflictError(
                "Cannot reject an already-approved approval",
                details={"approval_id": str(approval_id)},
            )
        if status in (ApprovalStatus.CANCELLED,):
            raise ConflictError(
                "Cannot reject a cancelled approval",
                details={"approval_id": str(approval_id)},
            )
        if status != ApprovalStatus.PENDING:
            raise ConflictError(
                "Approval is not pending",
                details={"approval_id": str(approval_id), "status": str(status)},
            )

        self._service._set_terminal(
            approval,
            status=ApprovalStatus.REJECTED,
            resolved_by=owner_id,
            note=note or "Rejected by owner",
            event_type="rejected",
        )
        record_security_event(
            self._session,
            event_type=APPROVAL_REJECTED,
            reason=note or "rejected",
            correlation_id=request_id,
            details={"actor": owner_id, "approval_id": str(approval_id)},
        )
        self._session.commit()
        return present_approval(self._service._to_view(approval))

    def cancel(
        self,
        approval_id: UUID,
        *,
        owner_id: str,
        note: str | None = None,
    ) -> ApprovalDecisionView:
        request = ResolveApprovalRequest(
            approval_id=approval_id,
            resolved_by=owner_id,
            note=note or "Cancelled by owner",
        )
        # Use lock path for cancel too
        approval = self._lock_approval(approval_id)
        status = _as_status(approval.status)
        if status == ApprovalStatus.CANCELLED:
            return present_approval(self._service._to_view(approval))
        if status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED):
            raise ConflictError(
                "Cannot cancel a resolved approval",
                details={"approval_id": str(approval_id), "status": status.value},
            )
        self._service._set_terminal(
            approval,
            status=ApprovalStatus.CANCELLED,
            resolved_by=owner_id,
            note=note or "Cancelled by owner",
            event_type="cancelled",
        )
        self._session.commit()
        return present_approval(self._service._to_view(approval))

    def _lock_approval(self, approval_id: UUID) -> Approval:
        """Load approval with row lock when the dialect supports it."""
        stmt = select(Approval).where(Approval.id == approval_id)
        try:
            stmt = stmt.with_for_update()
        except Exception:  # noqa: BLE001
            pass
        approval = self._session.scalar(stmt)
        if approval is None:
            from app.exceptions import NotFoundError

            raise NotFoundError("Approval not found", details={"approval_id": str(approval_id)})
        return approval
