"""Audit Agent tests — mocked browser/search/AI, real SQLite persistence."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.agents.audit import AuditAgent, AuditRequest
from app.agents.audit.observations import AUDIT_VERSION
from app.agents.audit.schemas import AuditAIEnrichment, AuditFinding
from app.agents.audit.validation import validate_ai_enrichment, validate_findings
from app.config import Settings
from app.exceptions import ValidationAppError
from app.models import AgentRun, Company, CompanyAudit
from app.models.enums import AgentRunStatus, CompanyStatus
from app.providers.ai.exceptions import AIProviderError
from app.providers.browser.exceptions import BrowserNavigationError
from app.providers.browser.types import BrowserLink, BrowserPageSnapshot
from app.providers.search.types import SearchResponse, SearchResult


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        max_audits_per_run=10,
        audit_use_ai=True,
        audit_search_results=3,
        database_url="sqlite+pysqlite:///:memory:",
    )
    base.update(overrides)
    return Settings(**base)


def _snapshot(**overrides) -> BrowserPageSnapshot:
    base = dict(
        requested_url="https://acme.example/",
        final_url="https://acme.example/",
        title="Acme GmbH",
        visible_text=(
            "Welcome to Acme. Contact us today. Submit your inquiry through our form. "
            "Get started with a free consultation. Book an appointment online."
        ),
        links=[
            BrowserLink(url="https://acme.example/contact", text="Contact"),
            BrowserLink(url="mailto:info@acme.example", text="Email"),
            BrowserLink(url="tel:+491234", text="Call"),
            BrowserLink(url="https://acme.example/book", text="Book now"),
        ],
        page_metadata={"viewport": "width=device-width, initial-scale=1"},
        status_code=200,
        domain="acme.example",
        execution_id="exec-1",
        trust_level="untrusted",
        untrusted_content=True,
    )
    base.update(overrides)
    return BrowserPageSnapshot(**base)


@pytest.fixture()
def audit_env(db_session):
    cfg = _settings()
    company = Company(
        name="Acme GmbH",
        website="https://acme.example/",
        website_domain="acme.example",
        status=CompanyStatus.PROSPECT,
        source="test",
    )
    db_session.add(company)
    db_session.commit()

    browser = MagicMock()
    browser.is_available.return_value = True
    search = MagicMock()
    search.search.return_value = SearchResponse(
        query="Acme",
        results=[
            SearchResult(
                title="Acme",
                url="https://acme.example/",
                normalized_url="https://acme.example",
                snippet="Acme services",
                domain="acme.example",
                trust_level="untrusted",
            )
        ],
        result_count=1,
        estimated_cost=Decimal("0.01"),
        latency_ms=1.0,
        untrusted_content=True,
    )
    ai = MagicMock()
    ai.is_configured.return_value = False

    agent = AuditAgent(
        session=db_session,
        browser_service=browser,
        search_service=search,
        ai_service=ai,
        settings=cfg,
    )
    return agent, browser, search, ai, db_session, company, cfg


def test_website_available(audit_env):
    agent, browser, _search, _ai, session, company, _cfg = audit_env
    browser.fetch_page.return_value = _snapshot()

    result = agent.run(AuditRequest(company_ids=[company.id], use_ai=False))

    assert result.status == "succeeded"
    assert result.audits_completed == 1
    assert result.results[0].website_available is True
    assert result.results[0].audit_version == AUDIT_VERSION
    assert result.results[0].evidence_catalog
    assert all(f.evidence_ids for f in result.results[0].problems + result.results[0].opportunities)
    row = session.scalar(select(CompanyAudit).where(CompanyAudit.company_id == company.id))
    assert row is not None
    assert row.evidence_urls
    assert row.audit_version == AUDIT_VERSION
    run = session.get(AgentRun, result.agent_run_id)
    assert run is not None
    assert run.agent_name == "audit"
    assert run.status == AgentRunStatus.SUCCEEDED


def test_website_unavailable(audit_env):
    agent, browser, _search, _ai, session, company, _cfg = audit_env
    browser.fetch_page.side_effect = BrowserNavigationError("down")

    result = agent.run(AuditRequest(company_ids=[company.id], use_ai=False))

    audit = result.results[0]
    assert audit.website_available is False
    assert any(p.title == "Website unavailable" for p in audit.problems)
    assert audit.priority == "critical"
    assert any(e.kind == "browser_failure" for e in audit.evidence_catalog)
    row = session.scalar(select(CompanyAudit))
    assert row is not None
    assert row.website_available is False


def test_incomplete_website(audit_env):
    agent, browser, _search, _ai, _session, company, _cfg = audit_env
    browser.fetch_page.return_value = _snapshot(
        visible_text="Hi",
        links=[],
        page_metadata={},
        title="X",
    )

    result = agent.run(AuditRequest(company_ids=[company.id], use_ai=False))
    audit = result.results[0]
    assert audit.status == "partial"
    assert any("Incomplete" in p.title for p in audit.problems)
    assert any(e.kind == "incomplete_site" for e in audit.evidence_catalog)


def test_ai_failure_falls_back(audit_env):
    agent, browser, _search, ai, _session, company, _cfg = audit_env
    browser.fetch_page.return_value = _snapshot()
    ai.is_configured.return_value = True
    ai.complete_structured.side_effect = AIProviderError("ai down")

    result = agent.run(AuditRequest(company_ids=[company.id], use_ai=True))
    assert result.audits_completed == 1
    assert result.results[0].ai_used is False
    assert any("ai_failed" in log for log in result.results[0].logs)
    assert result.results[0].summary  # deterministic summary still present


def test_browser_failure_still_tracked(audit_env):
    agent, browser, _search, _ai, session, company, _cfg = audit_env
    browser.is_available.return_value = False

    result = agent.run(AuditRequest(company_ids=[company.id], use_ai=False))
    assert result.results[0].website_available is False
    assert any("browser_unavailable" in log for log in result.results[0].logs)
    assert session.scalar(select(CompanyAudit)) is not None


def test_invalid_ai_output_rejected(audit_env):
    from app.agents.audit.schemas import AuditEvidenceItem

    catalog = [
        AuditEvidenceItem(evidence_id="E001", kind="page_fetch", url="https://acme.example/", detail="ok")
    ]
    bad = AuditAIEnrichment(
        summary="Invented issues",
        findings=[
            AuditFinding(
                finding_type="problem",
                title="Fake issue",
                detail="Not real",
                evidence_ids=["E999"],
                confidence=0.9,
            )
        ],
    )
    with pytest.raises(ValidationAppError):
        validate_ai_enrichment(bad, catalog)

    dropped = validate_findings(bad.findings, catalog)
    assert dropped == []


def test_evidence_validation_keeps_only_cited(audit_env):
    from app.agents.audit.schemas import AuditEvidenceItem

    catalog = [
        AuditEvidenceItem(evidence_id="E001", kind="page_fetch", detail="ok"),
        AuditEvidenceItem(evidence_id="E002", kind="cta", detail="cta"),
    ]
    findings = [
        AuditFinding(
            finding_type="opportunity",
            title="Good",
            detail="Supported",
            evidence_ids=["E002"],
            confidence=0.6,
        ),
        AuditFinding(
            finding_type="problem",
            title="Bad",
            detail="Unsupported",
            evidence_ids=["MISSING"],
            confidence=0.6,
        ),
    ]
    valid = validate_findings(findings, catalog)
    assert len(valid) == 1
    assert valid[0].title == "Good"


def test_max_audits_per_run(db_session):
    cfg = _settings(max_audits_per_run=2)
    companies = [
        Company(name=f"Co {i}", website=f"https://co{i}.example/", website_domain=f"co{i}.example")
        for i in range(5)
    ]
    db_session.add_all(companies)
    db_session.commit()

    browser = MagicMock()
    browser.is_available.return_value = True
    browser.fetch_page.return_value = _snapshot()
    agent = AuditAgent(
        session=db_session,
        browser_service=browser,
        search_service=None,
        ai_service=None,
        settings=cfg,
    )
    result = agent.run(AuditRequest(max_audits=2, use_ai=False))
    assert result.audits_completed == 2
    assert browser.fetch_page.call_count == 2
