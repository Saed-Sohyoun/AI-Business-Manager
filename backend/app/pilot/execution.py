"""ExecutionGuard — compose approvals + pilot limits + budget before acting."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.approvals.service import ApprovalService
from app.config import Settings
from app.exceptions import ForbiddenError, LimitReachedError
from app.pilot.budget import BudgetGuard, utc_day_key
from app.pilot.config import PilotModeConfig, pilot_mode_from_settings
from app.pilot.limits import LimitService
from app.pilot.schemas import GuardDecision, PilotStatus
from app.services.notification_service import NotificationService


# Pilot-required approval actions (policy still authoritative for risk level)
_PILOT_APPROVAL_ACTIONS = frozenset(
    {
        "sales.first_outreach",
        "sales.send_outreach",
        "commerce.purchase",
        "commerce.discount",
        "legal.contract",
        "strategy.major_change",
    }
)


class ExecutionGuard:
    """Fail closed when pilot limits, budget, or approvals block an action."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        approvals: ApprovalService | None = None,
        limits: LimitService | None = None,
        budget: BudgetGuard | None = None,
        notifications: NotificationService | None = None,
        pilot: PilotModeConfig | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._pilot = pilot or pilot_mode_from_settings(settings)
        self._notifications = notifications
        self._approvals = approvals or ApprovalService(session, settings)
        self._limits = limits or LimitService(session, settings, pilot=self._pilot)
        self._budget = budget or BudgetGuard(
            session,
            settings,
            pilot=self._pilot,
            notifications=notifications,
        )

    @property
    def limits(self) -> LimitService:
        return self._limits

    @property
    def budget(self) -> BudgetGuard:
        return self._budget

    @property
    def config(self) -> PilotModeConfig:
        return self._pilot

    def status(self) -> PilotStatus:
        budget = self._budget.status()
        usage = self._limits.usage_snapshot()
        return PilotStatus(
            pilot_mode=self._pilot.enabled,
            operating_mode=self._pilot.operating_mode,
            currency=self._pilot.currency,
            limits={
                "max_companies_per_day": self._pilot.max_companies_per_day,
                "max_audits_per_day": self._pilot.max_audits_per_day,
                "max_initial_outreach_per_day": self._pilot.max_initial_outreach_per_day,
                "max_followups_per_lead": self._pilot.max_followups_per_lead,
                "max_daily_spending": str(self._pilot.max_daily_spending),
                "max_single_expense": str(self._pilot.max_single_expense),
            },
            usage={k: (str(v) if isinstance(v, Decimal) else v) for k, v in usage.items()},
            budget=budget,
            approval_required_actions=list(self._pilot.approval_required_actions),
            production_unlock_required=not self._settings.allow_production_mode,
        )

    def evaluate(
        self,
        action_type: str,
        *,
        approval_id: UUID | None = None,
        amount: Decimal | None = None,
        lead_id: UUID | None = None,
        is_followup: bool = False,
    ) -> GuardDecision:
        """Non-raising decision for Manager stop checks / UI."""
        action = action_type.strip()

        if amount is not None:
            single = self._budget.check_single_expense(amount)
            if not single.allowed:
                return GuardDecision(
                    allowed=False,
                    action_type=action,
                    reason=single.reason,
                    limit_name=single.limit_name,
                    details=single.model_dump(mode="json"),
                )
            daily = self._budget.check_daily_spend(additional=amount)
            if not daily.allowed:
                return GuardDecision(
                    allowed=False,
                    action_type=action,
                    reason=daily.reason,
                    limit_name=daily.limit_name,
                    details=daily.model_dump(mode="json"),
                )

        if action in {"research.discover_companies", "research.create_company"}:
            check = self._limits.check_companies()
            if not check.allowed:
                return GuardDecision(
                    allowed=False,
                    action_type=action,
                    reason=check.reason,
                    limit_name=check.limit_name,
                    details=check.model_dump(mode="json"),
                )

        if action in {"audit.audit_digital_presence", "audit.create"}:
            check = self._limits.check_audits()
            if not check.allowed:
                return GuardDecision(
                    allowed=False,
                    action_type=action,
                    reason=check.reason,
                    limit_name=check.limit_name,
                    details=check.model_dump(mode="json"),
                )

        if action in {"sales.first_outreach", "sales.send_outreach"} and not is_followup:
            check = self._limits.check_initial_outreach()
            if not check.allowed:
                return GuardDecision(
                    allowed=False,
                    action_type=action,
                    reason=check.reason,
                    limit_name=check.limit_name,
                    details=check.model_dump(mode="json"),
                )

        if action == "sales.send_followup" and lead_id is not None:
            check = self._limits.check_followups_for_lead(lead_id)
            if not check.allowed:
                return GuardDecision(
                    allowed=False,
                    action_type=action,
                    reason=check.reason,
                    limit_name=check.limit_name,
                    details=check.model_dump(mode="json"),
                )

        gate = self._approvals.evaluate_gate(action, approval_id=approval_id)
        requires_approval = action in _PILOT_APPROVAL_ACTIONS or gate.decision in {
            "require_approval",
            "human_only",
            "deny",
        }
        if not gate.may_execute:
            return GuardDecision(
                allowed=False,
                action_type=action,
                reason=gate.reason or gate.decision,
                requires_approval=requires_approval,
                details={"gate": gate.decision, "risk_level": str(gate.risk_level)},
            )

        return GuardDecision(
            allowed=True,
            action_type=action,
            requires_approval=False,
            details={"gate": gate.decision},
        )

    def assert_may_execute(
        self,
        action_type: str,
        *,
        approval_id: UUID | None = None,
        amount: Decimal | None = None,
        lead_id: UUID | None = None,
        is_followup: bool = False,
    ) -> GuardDecision:
        decision = self.evaluate(
            action_type,
            approval_id=approval_id,
            amount=amount,
            lead_id=lead_id,
            is_followup=is_followup,
        )
        if decision.allowed:
            if amount is not None:
                self._budget.assert_expense_allowed(amount)
            return decision

        if decision.limit_name is not None:
            self._notify_daily_limit(decision)
            raise LimitReachedError(
                decision.reason or "Pilot limit reached",
                details=decision.details,
            )

        if decision.requires_approval:
            self._notify_approval_required(action_type, decision)
            raise ForbiddenError(
                decision.reason or "Approval required",
                details=decision.details,
            )

        raise ForbiddenError(
            decision.reason or "Action not permitted",
            details=decision.details,
        )

    def notify_critical_failure(self, *, task: str, detail: str) -> None:
        if self._notifications is None:
            return
        self._notifications.notify_critical_failure(
            source=task,
            message=detail,
            reference=f"pilot-critical-{task}-{utc_day_key()}",
        )

    def _notify_daily_limit(self, decision: GuardDecision) -> None:
        if self._notifications is None:
            return
        from app.models.enums import NotificationCategory, NotificationPriority

        limit = decision.limit_name or "limit"
        self._notifications.try_notify(
            title="Daily pilot limit reached",
            body=(
                f"Action `{decision.action_type}` stopped safely.\n"
                f"Limit: {limit}\n"
                f"Reason: {decision.reason}"
            ),
            priority=NotificationPriority.URGENT,
            category=NotificationCategory.DAILY_LIMIT,
            idempotency_key=f"notify:daily-limit:{limit}:{utc_day_key()}",
        )

    def _notify_approval_required(self, action_type: str, decision: GuardDecision) -> None:
        if self._notifications is None:
            return
        from uuid import uuid4

        self._notifications.notify_approval_request(
            approval_id=uuid4(),
            action_type=action_type,
            risk_level="yellow",
            description=decision.reason or "Pilot Mode requires owner approval",
        )


def build_execution_guard(
    session: Session,
    settings: Settings,
    *,
    notifications: NotificationService | None = None,
) -> ExecutionGuard:
    return ExecutionGuard(session, settings, notifications=notifications)
