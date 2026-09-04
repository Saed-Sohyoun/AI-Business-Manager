"""PilotExperiment service — draft create, niche approval, active lookup."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Company, CompanyAudit, OutboundMessage
from app.models.base import utc_now
from app.models.enums import OutboundMessageStatus
from app.models.pilot_experiment import PilotExperiment
from app.owner.schemas_pilot import (
    PilotExperimentCreate,
    PilotExperimentView,
    PilotObservabilityStatus,
)
from app.security import daily_cost_total

# Hard pilot caps — never raise above Wave 1–4 envelope
_MAX_COMPANIES = 20
_MAX_AUDITS = 10
_MAX_OUTREACH = 5
_MAX_DAILY_BUDGET = Decimal("3.00")

_ACTIVE_STATUSES = frozenset({"active", "approved"})
_SENT = {
    OutboundMessageStatus.SENT.value,
    OutboundMessageStatus.QUEUED.value,
    OutboundMessageStatus.SENDING.value,
}


class PilotExperimentService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def create_draft(self, body: PilotExperimentCreate) -> PilotExperimentView:
        caps = self._clamp_caps(
            company_count_cap=body.company_count_cap,
            audit_cap=body.audit_cap,
            outreach_cap=body.outreach_cap,
            daily_budget=body.daily_budget,
        )
        row = PilotExperiment(
            niche=body.niche.strip(),
            geography=(body.geography or "").strip(),
            language=(body.language or "en").strip()[:32],
            company_count_cap=caps["company_count_cap"],
            qualification_threshold=body.qualification_threshold,
            audit_cap=caps["audit_cap"],
            outreach_cap=caps["outreach_cap"],
            daily_budget=caps["daily_budget"],
            start_at=body.start_at,
            end_at=body.end_at,
            success_criteria=dict(body.success_criteria or {}),
            status="draft",
            owner_approved_niche=False,
            version=1,
            notes=body.notes,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return self._to_view(row)

    def get_active(self) -> PilotExperimentView | None:
        row = self._session.scalar(
            select(PilotExperiment)
            .where(PilotExperiment.status.in_(list(_ACTIVE_STATUSES)))
            .order_by(PilotExperiment.updated_at.desc())
            .limit(1)
        )
        if row is None:
            # Fall back to latest draft for owner visibility
            row = self._session.scalar(
                select(PilotExperiment).order_by(PilotExperiment.updated_at.desc()).limit(1)
            )
        return self._to_view(row) if row else None

    def get_by_id(self, experiment_id: UUID) -> PilotExperiment:
        row = self._session.get(PilotExperiment, experiment_id)
        if row is None:
            raise NotFoundError("Pilot experiment not found")
        return row

    def approve_niche(self, experiment_id: UUID, *, actor: str) -> PilotExperimentView:
        row = self.get_by_id(experiment_id)
        if not (row.niche or "").strip():
            raise ValidationAppError(
                "Niche is required before approval",
                details={"code": "NICHE_REQUIRED"},
            )
        row.owner_approved_niche = True
        # Activation requires owner-approved niche
        if row.status in {"draft", "approved"}:
            row.status = "active"
        row.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(row)
        return self._to_view(row)

    def activate(self, experiment_id: UUID) -> PilotExperimentView:
        """Activate only when niche is owner-approved."""
        row = self.get_by_id(experiment_id)
        if not row.owner_approved_niche:
            raise ForbiddenError(
                "Owner must approve niche before activating experiment",
                details={"code": "NICHE_APPROVAL_REQUIRED"},
            )
        # Deactivate other active experiments
        others = self._session.scalars(
            select(PilotExperiment).where(
                PilotExperiment.status == "active",
                PilotExperiment.id != row.id,
            )
        ).all()
        for other in others:
            other.status = "completed"
        row.status = "active"
        row.updated_at = utc_now()
        self._session.commit()
        self._session.refresh(row)
        return self._to_view(row)

    def observability_status(self) -> PilotObservabilityStatus:
        """Counters from DB only — no invented research results."""
        day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        companies_today = int(
            self._session.scalar(
                select(func.count())
                .select_from(Company)
                .where(Company.created_at >= day_start)
            )
            or 0
        )
        audits_today = int(
            self._session.scalar(
                select(func.count())
                .select_from(CompanyAudit)
                .where(CompanyAudit.created_at >= day_start)
            )
            or 0
        )
        outreach_today = int(
            self._session.scalar(
                select(func.count())
                .select_from(OutboundMessage)
                .where(
                    OutboundMessage.created_at >= day_start,
                    OutboundMessage.status.in_(list(_SENT)),
                )
            )
            or 0
        )
        spent = daily_cost_total(self._session)
        active = self.get_active()
        return PilotObservabilityStatus(
            production_locked=not self._settings.allow_production_mode,
            pilot_mode=self._settings.is_pilot_mode,
            companies_today=companies_today,
            audits_today=audits_today,
            outreach_today=outreach_today,
            spent_today=str(spent),
            daily_budget_limit=str(self._settings.daily_budget_limit),
            max_companies_per_day=min(self._settings.max_companies_per_day, _MAX_COMPANIES),
            max_audits_per_day=min(self._settings.max_audits_per_day, _MAX_AUDITS),
            max_initial_outreach_per_day=min(
                self._settings.max_initial_outreach_per_day, _MAX_OUTREACH
            ),
            active_experiment=active,
        )

    def _clamp_caps(
        self,
        *,
        company_count_cap: int,
        audit_cap: int,
        outreach_cap: int,
        daily_budget: Decimal,
    ) -> dict[str, Any]:
        return {
            "company_count_cap": max(0, min(int(company_count_cap), _MAX_COMPANIES)),
            "audit_cap": max(0, min(int(audit_cap), _MAX_AUDITS)),
            "outreach_cap": max(0, min(int(outreach_cap), _MAX_OUTREACH)),
            "daily_budget": min(Decimal(str(daily_budget)), _MAX_DAILY_BUDGET),
        }

    @staticmethod
    def _to_view(row: PilotExperiment) -> PilotExperimentView:
        return PilotExperimentView(
            id=row.id,
            niche=row.niche,
            geography=row.geography,
            language=row.language,
            company_count_cap=row.company_count_cap,
            qualification_threshold=row.qualification_threshold,
            audit_cap=row.audit_cap,
            outreach_cap=row.outreach_cap,
            daily_budget=row.daily_budget,
            start_at=row.start_at,
            end_at=row.end_at,
            success_criteria=dict(row.success_criteria or {}),
            status=row.status,
            owner_approved_niche=bool(row.owner_approved_niche),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
