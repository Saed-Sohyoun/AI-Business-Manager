"""Sales Agent tests — evidence-backed drafts, no sending."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.agents.sales import SalesAgent, SalesRequest
from app.agents.sales.composer import compose_deterministic_draft
from app.agents.sales.evidence import build_sales_evidence_catalog
from app.agents.sales.schemas import (
    OutreachDraft,
    PersonalizationReason,
    SalesAIEnrichment,
    SalesEvidenceItem,
)
from app.agents.sales.validation import validate_ai_enrichment, validate_outreach_draft
from app.config import Settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.models import Company, CompanyAudit, CompanyScore, Lead, Outreach
from app.models.enums import (
    AuditPriority,
    AuditStatus,
    CompanyStatus,
    LeadScoreCategory,
    LeadStatus,
    OutreachStatus,
    ScoreBand,
)
from app.providers.ai.exceptions import AIProviderError
from app.providers.ai.types import AIResponse


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        sales_use_ai=True,
        max_outreaches_per_run=10,
        approval_authorized_resolvers="owner,admin",
        database_url="sqlite+pysqlite:///:memory:",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def sales_env(db_session):
    cfg = _settings()
    company = Company(
        name="Acme GmbH",
        website="https://acme.example/",
        website_domain="acme.example",
        industry="Plumbing",
        location="Berlin",
        status=CompanyStatus.PROSPECT,
        source="test",
    )
    db_session.add(company)
    db_session.flush()
    lead = Lead(
        company_id=company.id,
        name="Alex Example",
        email="alex@acme.example",
        job_title="Owner",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    score = CompanyScore(
        company_id=company.id,
        total_score=72,
        band=ScoreBand.GOOD,
        website_quality=14,
        online_presence=14,
        lead_capture_process=14,
        automation_potential=15,
        commercial_potential=15,
        reasons=[{"reason": "Has website", "category": "website_quality"}],
        evidence={"website": "https://acme.example/"},
        scoring_version="1.0.0",
    )
    audit = CompanyAudit(
        company_id=company.id,
        audit_version="1.0.0",
        status=AuditStatus.SUCCEEDED,
        priority=AuditPriority.HIGH,
        confidence=Decimal("0.8"),
        summary="Website is live but lead capture is weak.",
        recommended_solution="Add a clear contact form above the fold.",
        website_available=True,
        problems=[
            {
                "title": "No clear contact form",
                "detail": "Primary page lacks an obvious inquiry form.",
                "evidence_ids": ["ev1"],
            }
        ],
        opportunities=[
            {
                "title": "Add booking CTA",
                "detail": "A booking link could recover missed leads.",
                "evidence_ids": ["ev2"],
            }
        ],
        evidence_urls=["https://acme.example/"],
        observations={"has_form_signal": False},
        evidence_catalog=[
            {
                "evidence_id": "ev1",
                "kind": "page_signal",
                "detail": "No form element detected",
                "url": "https://acme.example/",
            }
        ],
    )
    db_session.add_all([lead, score, audit])
    db_session.commit()
    return {
        "session": db_session,
        "settings": cfg,
        "company": company,
        "lead": lead,
        "score": score,
        "audit": audit,
    }


def test_draft_with_full_evidence(sales_env):
    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=None,
    )
    result = agent.run(
        SalesRequest(
            company_id=sales_env["company"].id,
            lead_id=sales_env["lead"].id,
            use_ai=False,
        )
    )
    assert result.status == "succeeded"
    assert result.send_attempted is False
    assert result.outreach is not None
    assert result.outreach.status == "draft"
    assert "Acme" in result.outreach.subject
    assert "Alex" in result.outreach.message
    assert result.outreach.personalization_reasons
    assert result.outreach.evidence_used
    assert result.outreach.confidence > 0

    row = sales_env["session"].get(Outreach, result.outreach.outreach_id)
    assert row is not None
    assert row.status == OutreachStatus.DRAFT
    assert row.sent_at is None
    assert row.extra_metadata.get("resend_connected") is False


def test_sparse_data_no_fabrication(db_session):
    cfg = _settings(sales_use_ai=False)
    company = Company(name="Bare Co", status=CompanyStatus.PROSPECT, source="test")
    db_session.add(company)
    db_session.flush()
    lead = Lead(
        company_id=company.id,
        name="Sam",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    db_session.add(lead)
    db_session.commit()

    agent = SalesAgent(session=db_session, settings=cfg, ai_service=None)
    result = agent.run(SalesRequest(company_id=company.id, lead_id=lead.id, use_ai=False))
    assert result.status == "succeeded"
    assert result.outreach is not None
    msg = result.outreach.message.lower()
    assert "i noticed" not in msg
    assert "your website has" not in msg
    assert "guaranteed" not in msg
    assert "Bare Co" in result.outreach.message


def test_ungrounded_noticed_rejected():
    catalog = [
        SalesEvidenceItem(
            evidence_id="company.name",
            kind="company_name",
            detail="Acme",
            source="company",
        )
    ]
    draft = OutreachDraft(
        subject="Hello",
        message="Hi,\n\nI noticed your website has a broken form.\n\nThanks",
        cta="Call me",
        personalization_reasons=[
            PersonalizationReason(reason="name", evidence_ids=["company.name"])
        ],
        evidence_used=["company.name"],
        confidence=0.5,
    )
    with pytest.raises(ValidationAppError):
        validate_outreach_draft(draft, catalog, website_verified=False)


def test_spam_language_rejected():
    catalog = [
        SalesEvidenceItem(
            evidence_id="company.name",
            kind="company_name",
            detail="Acme",
            source="company",
        )
    ]
    draft = OutreachDraft(
        subject="Guaranteed game-changer!",
        message="Act now for limited time results.",
        cta="Buy now",
        personalization_reasons=[
            PersonalizationReason(reason="name", evidence_ids=["company.name"])
        ],
        evidence_used=["company.name"],
        confidence=0.4,
    )
    with pytest.raises(ValidationAppError):
        validate_outreach_draft(draft, catalog, website_verified=True)


def test_ai_invalid_claims_fall_back(sales_env):
    ai = MagicMock()
    ai.is_configured.return_value = True

    def bad_structured(**kwargs):
        enrichment = SalesAIEnrichment(
            subject="I noticed your website has magic SEO",
            message="I noticed your website has 300% growth potential guaranteed.",
            cta="Act now",
            personalization_reasons=[
                PersonalizationReason(
                    reason="fabricated",
                    evidence_ids=["does-not-exist"],
                )
            ],
            confidence=0.9,
        )
        resp = AIResponse(
            content="{}",
            model="test",
            estimated_cost=Decimal("0.01"),
            latency_ms=1.0,
            request_id="r1",
            provider="test",
        )
        return resp, enrichment

    ai.complete_structured.side_effect = bad_structured
    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=ai,
    )
    result = agent.run(
        SalesRequest(
            company_id=sales_env["company"].id,
            lead_id=sales_env["lead"].id,
            use_ai=True,
        )
    )
    # Deterministic draft still succeeds; AI skipped
    assert result.status == "succeeded"
    assert any("ai_enrichment_skipped" in log for log in result.logs)
    assert "guaranteed" not in result.outreach.message.lower()


def test_ai_provider_failure_falls_back(sales_env):
    ai = MagicMock()
    ai.is_configured.return_value = True
    ai.complete_structured.side_effect = AIProviderError("down")
    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=ai,
    )
    result = agent.run(
        SalesRequest(
            company_id=sales_env["company"].id,
            lead_id=sales_env["lead"].id,
            use_ai=True,
        )
    )
    assert result.status == "succeeded"
    assert any("ai_enrichment_skipped" in log for log in result.logs)


def test_never_sends_without_approval(sales_env):
    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=None,
    )
    result = agent.run(
        SalesRequest(
            company_id=sales_env["company"].id,
            lead_id=sales_env["lead"].id,
            use_ai=False,
        )
    )
    assert result.send_attempted is False
    with pytest.raises(ForbiddenError):
        agent.send_outreach(result.outreach.outreach_id)
    row = sales_env["session"].get(Outreach, result.outreach.outreach_id)
    assert row.status == OutreachStatus.DRAFT
    assert row.sent_at is None


def test_send_requires_approval_request(sales_env):
    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=None,
    )
    result = agent.run(
        SalesRequest(
            company_id=sales_env["company"].id,
            lead_id=sales_env["lead"].id,
            use_ai=False,
        )
    )
    approval_id = agent.request_send_approval(result.outreach.outreach_id)
    row = sales_env["session"].get(Outreach, result.outreach.outreach_id)
    assert row.status == OutreachStatus.PENDING_APPROVAL
    assert row.approval_id == approval_id
    # Pending approval still cannot send
    with pytest.raises(ForbiddenError):
        agent.send_outreach(result.outreach.outreach_id)


def test_missing_company_or_lead(sales_env):
    from uuid import uuid4

    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=None,
    )
    result = agent.run(
        SalesRequest(company_id=uuid4(), lead_id=sales_env["lead"].id, use_ai=False)
    )
    assert result.status == "failed"
    assert result.error_message == "company_or_lead_not_found"


def test_lead_company_mismatch(sales_env, db_session):
    other = Company(name="Other", status=CompanyStatus.PROSPECT, source="test")
    db_session.add(other)
    db_session.flush()
    lead2 = Lead(
        company_id=other.id,
        name="Pat",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    db_session.add(lead2)
    db_session.commit()

    agent = SalesAgent(session=db_session, settings=sales_env["settings"], ai_service=None)
    result = agent.run(
        SalesRequest(
            company_id=sales_env["company"].id,
            lead_id=lead2.id,
            use_ai=False,
        )
    )
    assert result.status == "failed"
    assert result.error_message == "lead_company_mismatch"


def test_idempotency(sales_env):
    agent = SalesAgent(
        session=sales_env["session"],
        settings=sales_env["settings"],
        ai_service=None,
    )
    req = SalesRequest(
        company_id=sales_env["company"].id,
        lead_id=sales_env["lead"].id,
        use_ai=False,
        idempotency_key="sales-draft-1",
    )
    first = agent.run(req)
    second = agent.run(req)
    assert first.outreach.outreach_id == second.outreach.outreach_id
    assert second.idempotent_replay is True


def test_website_claim_requires_verified_audit(db_session):
    company = Company(
        name="Site Co",
        website="https://site.example/",
        status=CompanyStatus.PROSPECT,
        source="test",
    )
    db_session.add(company)
    db_session.flush()
    lead = Lead(
        company_id=company.id,
        name="Jamie",
        status=LeadStatus.NEW,
        score_category=LeadScoreCategory.UNSCORED,
    )
    audit = CompanyAudit(
        company_id=company.id,
        audit_version="1.0.0",
        status=AuditStatus.FAILED,
        priority=AuditPriority.LOW,
        confidence=Decimal("0.2"),
        summary="Website unreachable",
        website_available=False,
        problems=[],
        opportunities=[],
        evidence_urls=[],
        observations={},
        evidence_catalog=[],
    )
    db_session.add_all([lead, audit])
    db_session.commit()

    catalog = build_sales_evidence_catalog(
        company=company, lead=lead, score=None, audit=audit
    )
    draft = compose_deterministic_draft(
        company=company, lead=lead, catalog=catalog, audit=audit
    )
    # Must not claim website content when unavailable
    assert "I reviewed" not in draft.message
    assert "your website has" not in draft.message.lower()
    validated = validate_outreach_draft(draft, catalog, website_verified=False)
    assert validated.personalization_reasons


def test_validate_ai_enrichment_keeps_cited_only():
    catalog = [
        SalesEvidenceItem(
            evidence_id="company.name",
            kind="company_name",
            detail="Acme",
            source="company",
        ),
        SalesEvidenceItem(
            evidence_id="audit.problem.0",
            kind="problem",
            detail="Missing form",
            source="company_audit",
        ),
    ]
    enrichment = SalesAIEnrichment(
        subject="Quick thought on Acme's website",
        message=(
            "Hi,\n\nI reviewed Acme's public website and one clear gap stood out: "
            "Missing form.\n\nIf useful, would you be open to a short call?"
        ),
        cta="If useful, would you be open to a short call?",
        personalization_reasons=[
            PersonalizationReason(reason="company", evidence_ids=["company.name"]),
            PersonalizationReason(reason="bad", evidence_ids=["nope"]),
            PersonalizationReason(reason="problem", evidence_ids=["audit.problem.0"]),
        ],
        confidence=0.7,
    )
    draft = validate_ai_enrichment(enrichment, catalog, website_verified=True)
    ids = {eid for r in draft.personalization_reasons for eid in r.evidence_ids}
    assert "nope" not in ids
    assert "company.name" in ids
    assert "audit.problem.0" in ids
