"""ApprovalResolver — authorize humans to approve/reject; never agents."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.approvals.schemas import ApprovalView, ResolveApprovalRequest
from app.approvals.service import ApprovalService, _as_status
from app.config import Settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.models.enums import ApprovalStatus

logger = logging.getLogger(__name__)

# Agents / automation identities may request approvals but never resolve them.
# Agents / automation identities may request approvals but never resolve them.
BLOCKED_RESOLVER_IDENTITIES = frozenset(
    {
        "system",
        "manager",
        "research",
        "audit",
        "scoring",
        "sales",
        "delivery",
        "finance",
        "report",
        "agent",
        "automation",
        "follow_up",
    }
)


class ApprovalResolver:
    """Human-only resolution path. Protects against unauthorized / agent bypass."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        service: ApprovalService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._service = service or ApprovalService(session, settings)

    def approve(self, request: ResolveApprovalRequest) -> ApprovalView:
        self._assert_authorized_resolver(request.resolved_by)
        approval = self._service._get_or_raise(request.approval_id)
        self._service.expire_if_due(approval)
        if _as_status(approval.status) == ApprovalStatus.EXPIRED:
            raise ValidationAppError(
                "Cannot approve an expired approval",
                details={"approval_id": str(approval.id)},
            )
        self._service._set_terminal(
            approval,
            status=ApprovalStatus.APPROVED,
            resolved_by=request.resolved_by.strip(),
            note=request.note or "Approved",
            event_type="approved",
        )
        self._session.commit()
        logger.info("Approval approved id=%s by=%s", approval.id, request.resolved_by)
        return self._service._to_view(approval)

    def reject(self, request: ResolveApprovalRequest) -> ApprovalView:
        self._assert_authorized_resolver(request.resolved_by)
        approval = self._service._get_or_raise(request.approval_id)
        self._service.expire_if_due(approval)
        if _as_status(approval.status) == ApprovalStatus.EXPIRED:
            raise ValidationAppError(
                "Cannot reject an expired approval",
                details={"approval_id": str(approval.id)},
            )
        self._service._set_terminal(
            approval,
            status=ApprovalStatus.REJECTED,
            resolved_by=request.resolved_by.strip(),
            note=request.note or "Rejected",
            event_type="rejected",
        )
        self._session.commit()
        logger.info("Approval rejected id=%s by=%s", approval.id, request.resolved_by)
        return self._service._to_view(approval)

    def cancel(self, request: ResolveApprovalRequest) -> ApprovalView:
        self._assert_authorized_resolver(request.resolved_by)
        approval = self._service._get_or_raise(request.approval_id)
        self._service._set_terminal(
            approval,
            status=ApprovalStatus.CANCELLED,
            resolved_by=request.resolved_by.strip(),
            note=request.note or "Cancelled",
            event_type="cancelled",
        )
        self._session.commit()
        return self._service._to_view(approval)

    def _assert_authorized_resolver(self, resolved_by: str) -> None:
        identity = resolved_by.strip().lower()
        if not identity:
            raise ForbiddenError("Resolver identity required")
        if identity in BLOCKED_RESOLVER_IDENTITIES:
            raise ForbiddenError(
                "Agents and system identities cannot resolve approvals",
                details={"resolved_by": resolved_by},
            )
        allowed = {
            name.strip().lower()
            for name in self._settings.approval_authorized_resolvers.split(",")
            if name.strip()
        }
        if identity not in allowed:
            raise ForbiddenError(
                "Unauthorized approval resolver",
                details={"resolved_by": resolved_by},
            )
