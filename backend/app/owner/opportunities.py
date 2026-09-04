"""Owner-facing opportunity projection — Company ⨝ Score ⨝ Audit ⨝ Outreach."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import NotFoundError
from app.models import Company, CompanyAudit, CompanyScore, Customer, Lead, Outreach
from app.models.enums import LeadStatus, OutreachStatus, ScoreBand
from app.owner.opportunity_lifecycle import derive_lifecycle_state


class OpportunityListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    company_name: str
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    score: int | None = None
    score_band: str | None = None
    category: str
    strongest_problem: str
    estimated_potential: str
    audit_status: str
    outreach_status: str
    lifecycle_state: str
    next_recommendation: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OpportunityDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    overview: dict[str, Any]
    company: dict[str, Any]
    score: dict[str, Any]
    why_this_matters: str
    findings: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    recommended_solution: str
    estimated_value: dict[str, Any]
    outreach: dict[str, Any]
    history: list[dict[str, Any]]
    next_action: str
    lifecycle_state: str


class OpportunityListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OpportunityListItem]
    total: int
    limit: int
    offset: int


_UNKNOWN = "unknown"
_NOT_AVAILABLE = "not available"
_NOT_YET = "not yet analyzed"


class OpportunityCatalogService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_opportunities(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        lifecycle: str | None = None,
    ) -> OpportunityListView:
        capped = max(1, min(limit, 100))
        off = max(0, offset)

        stmt = select(Company).options(
            selectinload(Company.scores),
            selectinload(Company.audits),
            selectinload(Company.leads),
        )
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Company.name.ilike(like),
                    Company.industry.ilike(like),
                    Company.location.ilike(like),
                    Company.website_domain.ilike(like),
                )
            )
        total = int(
            self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        companies = self._session.scalars(
            stmt.order_by(Company.updated_at.desc()).offset(off).limit(capped)
        ).all()

        items: list[OpportunityListItem] = []
        for company in companies:
            item = self._to_list_item(company)
            if min_score is not None and (item.score is None or item.score < min_score):
                continue
            if max_score is not None and (item.score is None or item.score > max_score):
                continue
            if lifecycle and item.lifecycle_state != lifecycle:
                continue
            items.append(item)

        # When filters applied after load, recompute total approximately
        if min_score is not None or max_score is not None or lifecycle:
            total = len(items)

        return OpportunityListView(items=items, total=total, limit=capped, offset=off)

    def get_opportunity(self, opportunity_id: UUID) -> OpportunityDetailView:
        company = self._session.scalar(
            select(Company)
            .where(Company.id == opportunity_id)
            .options(
                selectinload(Company.scores),
                selectinload(Company.audits),
                selectinload(Company.leads),
                selectinload(Company.evidence),
                selectinload(Company.sources),
            )
        )
        if company is None:
            raise NotFoundError(
                "Opportunity not found",
                details={"opportunity_id": str(opportunity_id)},
            )
        return self._to_detail(company)

    def _latest_score(self, company: Company) -> CompanyScore | None:
        if not company.scores:
            return None
        return max(company.scores, key=lambda s: s.scored_at)

    def _latest_audit(self, company: Company) -> CompanyAudit | None:
        if not company.audits:
            return None
        return max(company.audits, key=lambda a: a.audited_at)

    def _latest_outreach(self, company: Company) -> Outreach | None:
        row = self._session.scalar(
            select(Outreach)
            .where(Outreach.company_id == company.id)
            .order_by(Outreach.created_at.desc())
            .limit(1)
        )
        return row

    def _has_customer(self, company: Company) -> bool:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == company.id)
            )
            or 0
        ) > 0

    def _to_list_item(self, company: Company) -> OpportunityListItem:
        score = self._latest_score(company)
        audit = self._latest_audit(company)
        outreach = self._latest_outreach(company)
        lead = company.leads[0] if company.leads else None
        lifecycle = derive_lifecycle_state(
            company=company,
            score=score,
            audit=audit,
            outreach=outreach,
            lead=lead,
            is_customer=self._has_customer(company),
        )
        problem = _NOT_YET
        if audit and audit.problems:
            first = audit.problems[0]
            if isinstance(first, dict):
                problem = str(first.get("description") or first.get("title") or problem)
            else:
                problem = str(first)
        elif score and score.reasons:
            first = score.reasons[0]
            if isinstance(first, dict):
                problem = str(first.get("text") or first.get("reason") or problem)

        potential = _NOT_AVAILABLE
        if audit and audit.estimated_business_value is not None:
            cur = audit.estimated_business_value_currency or "EUR"
            potential = f"{audit.estimated_business_value} {cur}"
        elif score:
            potential = score.band.value if hasattr(score.band, "value") else str(score.band)

        category = "Prospect"
        if score:
            band = score.band.value if hasattr(score.band, "value") else str(score.band)
            if band in {ScoreBand.HIGH.value, ScoreBand.GOOD.value, "high", "good"}:
                category = "Strong opportunity"
            else:
                category = f"Scored ({band})"

        next_rec = self._next_recommendation(lifecycle, score, audit, outreach)

        return OpportunityListItem(
            id=company.id,
            company_name=company.name,
            website=company.website,
            industry=company.industry,
            location=company.location,
            score=score.total_score if score else None,
            score_band=(
                score.band.value if score and hasattr(score.band, "value") else (str(score.band) if score else None)
            ),
            category=category,
            strongest_problem=problem,
            estimated_potential=potential,
            audit_status=(
                audit.status.value
                if audit and hasattr(audit.status, "value")
                else (str(audit.status) if audit else _NOT_YET)
            ),
            outreach_status=(
                outreach.status.value
                if outreach and hasattr(outreach.status, "value")
                else (str(outreach.status) if outreach else "not started")
            ),
            lifecycle_state=lifecycle,
            next_recommendation=next_rec,
            created_at=getattr(company, "created_at", None),
            updated_at=getattr(company, "updated_at", None),
        )

    def _next_recommendation(
        self,
        lifecycle: str,
        score: CompanyScore | None,
        audit: CompanyAudit | None,
        outreach: Outreach | None,
    ) -> str:
        mapping = {
            "discovered": "Verify company sources",
            "verified": "Score this company",
            "scored": "Run a digital audit" if not audit else "Review audit findings",
            "audited": "Qualify for outreach",
            "qualified": "Draft outreach",
            "outreach_drafted": "Review outreach draft",
            "pending_approval": "Approve or reject outreach",
            "contacted": "Monitor for response",
            "responded": "Follow up with customer conversation",
            "customer": "Review open delivery work",
            "lost": "No further action",
            "disqualified": "No further action",
            "blocked": "Investigate block reason",
        }
        return mapping.get(lifecycle, "Review opportunity")

    def _to_detail(self, company: Company) -> OpportunityDetailView:
        item = self._to_list_item(company)
        score = self._latest_score(company)
        audit = self._latest_audit(company)
        outreach = self._latest_outreach(company)

        findings: list[dict[str, Any]] = []
        if audit and audit.problems:
            for p in audit.problems:
                if isinstance(p, dict):
                    findings.append(p)
                else:
                    findings.append({"description": str(p)})
        if not findings:
            findings.append({"description": _NOT_YET})

        evidence: list[dict[str, Any]] = []
        if audit and audit.evidence_catalog:
            evidence.extend([e for e in audit.evidence_catalog if isinstance(e, dict)])
        for ev in getattr(company, "evidence", []) or []:
            evidence.append(
                {
                    "type": getattr(ev, "evidence_type", _UNKNOWN),
                    "source_url": getattr(ev, "source_url", None) or _NOT_AVAILABLE,
                    "snippet": getattr(ev, "snippet", None) or _NOT_AVAILABLE,
                }
            )
        if not evidence:
            evidence.append({"description": _NOT_AVAILABLE, "provenance": _UNKNOWN})

        why = item.strongest_problem
        if why in {_NOT_YET, _NOT_AVAILABLE}:
            why = "This company is in the pipeline but has not been fully analyzed yet."

        recommended = (
            audit.recommended_solution
            if audit and audit.recommended_solution
            else _NOT_YET
        )

        estimated_value: dict[str, Any] = {
            "amount": str(audit.estimated_business_value)
            if audit and audit.estimated_business_value is not None
            else _NOT_AVAILABLE,
            "currency": (audit.estimated_business_value_currency if audit else None)
            or _NOT_AVAILABLE,
            "rationale": (audit.estimated_business_value_rationale if audit else None)
            or _NOT_YET,
        }

        history: list[dict[str, Any]] = [
            {"event": "discovered", "at": str(getattr(company, "created_at", _UNKNOWN))}
        ]
        if score:
            history.append({"event": "scored", "at": str(score.scored_at), "score": score.total_score})
        if audit:
            history.append({"event": "audited", "at": str(audit.audited_at)})
        if outreach:
            history.append(
                {
                    "event": "outreach",
                    "at": str(outreach.created_at),
                    "status": outreach.status.value
                    if hasattr(outreach.status, "value")
                    else str(outreach.status),
                }
            )

        return OpportunityDetailView(
            id=company.id,
            overview={
                "title": company.name,
                "category": item.category,
                "lifecycle_state": item.lifecycle_state,
                "score": item.score,
            },
            company={
                "name": company.name,
                "website": company.website or _NOT_AVAILABLE,
                "industry": company.industry or _UNKNOWN,
                "location": company.location or _UNKNOWN,
                "status": company.status.value
                if hasattr(company.status, "value")
                else str(company.status),
            },
            score={
                "total": score.total_score if score else None,
                "band": item.score_band or _NOT_YET,
                "reasons": score.reasons if score else [],
                "available": score is not None,
            },
            why_this_matters=why,
            findings=findings,
            evidence=evidence,
            recommended_solution=recommended,
            estimated_value=estimated_value,
            outreach={
                "status": item.outreach_status,
                "available": outreach is not None,
            },
            history=history,
            next_action=item.next_recommendation,
            lifecycle_state=item.lifecycle_state,
        )
