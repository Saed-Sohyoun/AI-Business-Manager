"""LeadScoringService — load company memory, score deterministically, persist."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import NotFoundError, ValidationAppError
from app.models import Company, CompanyScore
from app.models.enums import ScoreBand
from app.scoring.engine import SCORING_VERSION, score_company_facts
from app.scoring.facts import build_scoring_facts
from app.scoring.schemas import CompanyScoringFacts, LeadScoreResult, StoredLeadScore

logger = logging.getLogger(__name__)


class LeadScoringService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def score_facts(self, facts: CompanyScoringFacts) -> LeadScoreResult:
        """Pure scoring entrypoint — no persistence, no LLM."""
        return score_company_facts(facts)

    def score_company(
        self,
        company_id: UUID,
        *,
        has_contact_page: bool = False,
        has_contact_form: bool = False,
        has_booking_or_calendar: bool = False,
        persist: bool = True,
    ) -> LeadScoreResult:
        company = self._session.scalar(
            select(Company)
            .where(Company.id == company_id)
            .options(
                selectinload(Company.sources),
                selectinload(Company.evidence),
            )
        )
        if company is None:
            raise NotFoundError("Company not found", details={"company_id": str(company_id)})

        facts = build_scoring_facts(
            company,
            has_contact_page=has_contact_page,
            has_contact_form=has_contact_form,
            has_booking_or_calendar=has_booking_or_calendar,
        )
        result = score_company_facts(facts)

        if persist:
            self._persist(company_id, result)
            self._session.commit()
            logger.info(
                "Company scored company_id=%s total=%s band=%s version=%s",
                company_id,
                result.total_score,
                result.band,
                result.scoring_version,
            )
        return result

    def get_latest_score(self, company_id: UUID) -> StoredLeadScore | None:
        row = self._session.scalar(
            select(CompanyScore)
            .where(CompanyScore.company_id == company_id)
            .order_by(CompanyScore.scored_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        return StoredLeadScore(
            id=row.id,
            company_id=row.company_id,
            total_score=row.total_score,
            band=row.band.value if isinstance(row.band, ScoreBand) else str(row.band),  # type: ignore[arg-type]
            website_quality=row.website_quality,
            online_presence=row.online_presence,
            lead_capture_process=row.lead_capture_process,
            automation_potential=row.automation_potential,
            commercial_potential=row.commercial_potential,
            reasons=list(row.reasons or []),
            evidence=dict(row.evidence or {}),
            scoring_version=row.scoring_version,
            scored_at=row.scored_at,
        )

    def _persist(self, company_id: UUID, result: LeadScoreResult) -> CompanyScore:
        if result.scoring_version != SCORING_VERSION:
            raise ValidationAppError(
                "Unexpected scoring version",
                details={"expected": SCORING_VERSION, "got": result.scoring_version},
            )
        for name, value in (
            ("website_quality", result.website_quality),
            ("online_presence", result.online_presence),
            ("lead_capture_process", result.lead_capture_process),
            ("automation_potential", result.automation_potential),
            ("commercial_potential", result.commercial_potential),
            ("total_score", result.total_score),
        ):
            if not isinstance(value, int):
                raise ValidationAppError(f"Invalid {name}", details={"value": value})

        row = CompanyScore(
            company_id=company_id,
            total_score=result.total_score,
            band=ScoreBand(result.band),
            website_quality=result.website_quality,
            online_presence=result.online_presence,
            lead_capture_process=result.lead_capture_process,
            automation_potential=result.automation_potential,
            commercial_potential=result.commercial_potential,
            reasons=[r.model_dump() for r in result.reasons],
            evidence=result.evidence,
            scoring_version=result.scoring_version,
            scored_at=result.scored_at,
        )
        self._session.add(row)
        self._session.flush()
        return row
