"""Business-state inspection for Manager planning and cycle evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.manager.schemas import BusinessStateSnapshot
from app.models import (
    Approval,
    Company,
    CompanyAudit,
    CompanyScore,
    CostEntry,
    Customer,
    DeliveryProject,
    FollowUpSequence,
    Lead,
    Outreach,
    RevenueEntry,
)
from app.models.enums import (
    ApprovalStatus,
    CustomerStatus,
    FollowUpSequenceStatus,
    LeadStatus,
    OutreachStatus,
    ScoreBand,
)


QUALIFIED_BANDS = {ScoreBand.GOOD, ScoreBand.HIGH}


def _month_start(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def inspect_business_state(session: Session, *, unscored_limit: int = 50) -> BusinessStateSnapshot:
    companies_total = session.scalar(select(func.count()).select_from(Company)) or 0
    companies_with_website = (
        session.scalar(
            select(func.count()).select_from(Company).where(Company.website.is_not(None))
        )
        or 0
    )
    scores_total = session.scalar(select(func.count()).select_from(CompanyScore)) or 0
    audits_total = session.scalar(select(func.count()).select_from(CompanyAudit)) or 0

    qualified_company_ids = set(
        session.scalars(
            select(CompanyScore.company_id).where(
                CompanyScore.band.in_([ScoreBand.GOOD.value, ScoreBand.HIGH.value])
            )
        ).all()
    )
    scored_company_ids = set(session.scalars(select(CompanyScore.company_id)).all())
    all_company_ids = list(session.scalars(select(Company.id)).all())
    unscored = [str(cid) for cid in all_company_ids if cid not in scored_company_ids][:unscored_limit]

    audited_ids = set(session.scalars(select(CompanyAudit.company_id)).all())
    unaudited = [str(cid) for cid in all_company_ids if cid not in audited_ids][:unscored_limit]
    qualified_unaudited = [cid for cid in qualified_company_ids if cid not in audited_ids]

    # Draftable: qualified company + lead with email + no outreach yet
    outreached_lead_ids = set(session.scalars(select(Outreach.lead_id)).all())
    draftable: list[dict[str, str]] = []
    leads = session.scalars(
        select(Lead).where(
            Lead.email.is_not(None),
            Lead.opted_out.is_(False),
            Lead.blocked.is_(False),
            Lead.status.in_(
                [
                    LeadStatus.NEW.value,
                    LeadStatus.CONTACTED.value,
                    LeadStatus.QUALIFIED.value,
                ]
            ),
        )
    ).all()
    for lead in leads:
        if lead.id in outreached_lead_ids:
            continue
        if lead.company_id not in qualified_company_ids:
            continue
        draftable.append(
            {
                "lead_id": str(lead.id),
                "company_id": str(lead.company_id),
            }
        )
        if len(draftable) >= unscored_limit:
            break

    draft_ids = list(
        session.scalars(
            select(Outreach.id).where(Outreach.status == OutreachStatus.DRAFT.value).limit(20)
        )
    )
    approved_ids = list(
        session.scalars(
            select(Outreach.id)
            .where(Outreach.status == OutreachStatus.APPROVED.value)
            .limit(20)
        )
    )

    pending_approvals = (
        session.scalar(
            select(func.count()).select_from(Approval).where(Approval.status == ApprovalStatus.PENDING.value)
        )
        or 0
    )

    now = datetime.now(timezone.utc)
    follow_ups_due = (
        session.scalar(
            select(func.count())
            .select_from(FollowUpSequence)
            .where(
                FollowUpSequence.status == FollowUpSequenceStatus.ACTIVE.value,
                FollowUpSequence.next_follow_up_at.is_not(None),
                FollowUpSequence.next_follow_up_at <= now,
            )
        )
        or 0
    )

    customers_active = (
        session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.status == CustomerStatus.ACTIVE.value)
        )
        or 0
    )

    customers_with_projects = set(session.scalars(select(DeliveryProject.customer_id)).all())
    customer_lead_ids = set(
        session.scalars(select(Customer.lead_id).where(Customer.lead_id.is_not(None))).all()
    )
    delivery_ready = list(
        session.scalars(
            select(Lead.id)
            .where(
                Lead.email.is_not(None),
                Lead.opted_out.is_(False),
                Lead.blocked.is_(False),
                Lead.status.in_(
                    [
                        LeadStatus.QUALIFIED.value,
                        LeadStatus.CONTACTED.value,
                    ]
                ),
            )
            .limit(50)
        )
    )
    converted_without = [str(lid) for lid in delivery_ready if lid not in customer_lead_ids][:20]

    # Customers that exist but have no delivery project yet (lead already converted).
    for customer in session.scalars(select(Customer).limit(50)).all():
        if customer.id in customers_with_projects:
            continue
        if customer.lead_id is None:
            continue
        sid = str(customer.lead_id)
        if sid not in converted_without:
            converted_without.append(sid)
    converted_without = converted_without[:20]

    active_projects = session.scalar(select(func.count()).select_from(DeliveryProject)) or 0

    month_start = _month_start(now)
    revenue_mtd = session.scalar(
        select(func.coalesce(func.sum(RevenueEntry.amount), 0)).where(
            RevenueEntry.occurred_at >= month_start
        )
    )
    costs_mtd = session.scalar(
        select(func.coalesce(func.sum(CostEntry.amount), 0)).where(
            CostEntry.occurred_at >= month_start
        )
    )
    mrr = session.scalar(
        select(func.coalesce(func.sum(RevenueEntry.amount), 0)).where(
            RevenueEntry.is_recurring.is_(True),
            RevenueEntry.occurred_at >= month_start,
        )
    )
    revenue_dec = Decimal(str(revenue_mtd or 0))
    costs_dec = Decimal(str(costs_mtd or 0))
    mrr_dec = Decimal(str(mrr or 0))

    responses = (
        session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.status.in_([LeadStatus.QUALIFIED.value, LeadStatus.CONVERTED.value]))
        )
        or 0
    )

    return BusinessStateSnapshot(
        companies_total=int(companies_total),
        companies_with_website=int(companies_with_website),
        scores_total=int(scores_total),
        qualified_leads=len(qualified_company_ids),
        audits_total=int(audits_total),
        unscored_company_ids=unscored,
        unaudited_company_ids=unaudited,
        qualified_unaudited_count=len(qualified_unaudited),
        draftable_leads=draftable,
        draftable_leads_count=len(draftable),
        pending_outreach_drafts=len(draft_ids),
        draft_outreach_ids=[str(i) for i in draft_ids],
        approved_outreach_ids=[str(i) for i in approved_ids],
        pending_approvals=int(pending_approvals),
        follow_ups_due=int(follow_ups_due),
        customers_active=int(customers_active),
        converted_leads_without_project=len(converted_without),
        converted_lead_ids=converted_without,
        active_projects=int(active_projects),
        mrr=mrr_dec,
        operating_costs_mtd=costs_dec,
        revenue_mtd=revenue_dec,
        profit_mtd=revenue_dec - costs_dec,
        responses_recorded=int(responses),
    )
