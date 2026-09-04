"""LimitService — UTC-day counters for Pilot Mode operational caps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import LimitReachedError
from app.models import Company, CompanyAudit, OutboundMessage
from app.models.base import utc_now
from app.models.enums import OutboundMessageStatus
from app.pilot.config import PilotModeConfig, pilot_mode_from_settings
from app.pilot.schemas import LimitCheckResult


_SENT_STATUSES = {
    OutboundMessageStatus.SENT,
    OutboundMessageStatus.QUEUED,
    OutboundMessageStatus.SENDING,
}


def _day_bounds(as_of: datetime | None = None) -> tuple[datetime, datetime]:
    now = as_of or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


class LimitService:
    """Count usage and fail closed when pilot daily / per-lead caps are hit."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        pilot: PilotModeConfig | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._pilot = pilot or pilot_mode_from_settings(settings)

    @property
    def config(self) -> PilotModeConfig:
        return self._pilot

    def usage_snapshot(self, *, as_of: datetime | None = None) -> dict[str, int | Decimal]:
        return {
            "companies_today": self.count_companies_today(as_of=as_of),
            "audits_today": self.count_audits_today(as_of=as_of),
            "initial_outreach_today": self.count_initial_outreach_today(as_of=as_of),
            "max_companies_per_day": self._pilot.max_companies_per_day,
            "max_audits_per_day": self._pilot.max_audits_per_day,
            "max_initial_outreach_per_day": self._pilot.max_initial_outreach_per_day,
            "max_followups_per_lead": self._pilot.max_followups_per_lead,
        }

    def count_companies_today(self, *, as_of: datetime | None = None) -> int:
        start, end = _day_bounds(as_of)
        return int(
            self._session.scalar(
                select(func.count()).select_from(Company).where(
                    Company.created_at >= start,
                    Company.created_at < end,
                )
            )
            or 0
        )

    def count_audits_today(self, *, as_of: datetime | None = None) -> int:
        start, end = _day_bounds(as_of)
        return int(
            self._session.scalar(
                select(func.count()).select_from(CompanyAudit).where(
                    CompanyAudit.created_at >= start,
                    CompanyAudit.created_at < end,
                )
            )
            or 0
        )

    def count_initial_outreach_today(self, *, as_of: datetime | None = None) -> int:
        start, end = _day_bounds(as_of)
        return int(
            self._session.scalar(
                select(func.count()).select_from(OutboundMessage).where(
                    OutboundMessage.is_followup.is_(False),
                    OutboundMessage.status.in_([s.value for s in _SENT_STATUSES]),
                    func.coalesce(OutboundMessage.sent_at, OutboundMessage.created_at) >= start,
                    func.coalesce(OutboundMessage.sent_at, OutboundMessage.created_at) < end,
                )
            )
            or 0
        )

    def count_followups_for_lead(self, lead_id: UUID) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(OutboundMessage).where(
                    OutboundMessage.lead_id == lead_id,
                    OutboundMessage.is_followup.is_(True),
                    OutboundMessage.status.in_([s.value for s in _SENT_STATUSES]),
                )
            )
            or 0
        )

    def check_companies(self, *, additional: int = 1) -> LimitCheckResult:
        used = self.count_companies_today()
        limit = self._pilot.max_companies_per_day
        projected = used + additional
        allowed = projected <= limit
        return LimitCheckResult(
            allowed=allowed,
            limit_name="companies_per_day",
            used=used,
            limit=limit,
            remaining=max(0, limit - used),
            reason=None if allowed else "max_companies_per_day",
        )

    def check_audits(self, *, additional: int = 1) -> LimitCheckResult:
        used = self.count_audits_today()
        limit = self._pilot.max_audits_per_day
        projected = used + additional
        allowed = projected <= limit
        return LimitCheckResult(
            allowed=allowed,
            limit_name="audits_per_day",
            used=used,
            limit=limit,
            remaining=max(0, limit - used),
            reason=None if allowed else "max_audits_per_day",
        )

    def check_initial_outreach(self, *, additional: int = 1) -> LimitCheckResult:
        used = self.count_initial_outreach_today()
        limit = self._pilot.max_initial_outreach_per_day
        projected = used + additional
        allowed = projected <= limit
        return LimitCheckResult(
            allowed=allowed,
            limit_name="initial_outreach_per_day",
            used=used,
            limit=limit,
            remaining=max(0, limit - used),
            reason=None if allowed else "max_initial_outreach_per_day",
        )

    def check_followups_for_lead(self, lead_id: UUID, *, additional: int = 1) -> LimitCheckResult:
        used = self.count_followups_for_lead(lead_id)
        limit = self._pilot.max_followups_per_lead
        projected = used + additional
        allowed = projected <= limit
        return LimitCheckResult(
            allowed=allowed,
            limit_name="followups_per_lead",
            used=used,
            limit=limit,
            remaining=max(0, limit - used),
            reason=None if allowed else "max_followups_per_lead",
            details={"lead_id": str(lead_id)},
        )

    def remaining_companies_capacity(self) -> int:
        return int(self.check_companies(additional=0).remaining)

    def remaining_audits_capacity(self) -> int:
        return int(self.check_audits(additional=0).remaining)

    def assert_companies(self, *, additional: int = 1) -> LimitCheckResult:
        result = self.check_companies(additional=additional)
        if not result.allowed:
            raise LimitReachedError(
                "Daily company discovery limit reached",
                details=result.model_dump(mode="json"),
            )
        return result

    def assert_audits(self, *, additional: int = 1) -> LimitCheckResult:
        result = self.check_audits(additional=additional)
        if not result.allowed:
            raise LimitReachedError(
                "Daily audit limit reached",
                details=result.model_dump(mode="json"),
            )
        return result

    def assert_initial_outreach(self, *, additional: int = 1) -> LimitCheckResult:
        result = self.check_initial_outreach(additional=additional)
        if not result.allowed:
            raise LimitReachedError(
                "Daily initial outreach limit reached",
                details=result.model_dump(mode="json"),
            )
        return result

    def assert_followups_for_lead(self, lead_id: UUID, *, additional: int = 1) -> LimitCheckResult:
        result = self.check_followups_for_lead(lead_id, additional=additional)
        if not result.allowed:
            raise LimitReachedError(
                "Per-lead follow-up limit reached",
                details=result.model_dump(mode="json"),
            )
        return result

    def any_daily_limit_reached(self) -> LimitCheckResult | None:
        for check in (
            self.check_companies(additional=1),
            self.check_audits(additional=1),
            self.check_initial_outreach(additional=1),
        ):
            if not check.allowed:
                return check
        return None
