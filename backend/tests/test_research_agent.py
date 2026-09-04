"""Research Agent tests — mocked search/browser, real SQLite persistence."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.agents.research import ResearchAgent, ResearchRequest
from app.agents.research.extraction import candidate_from_search_result
from app.config import Settings
from app.models import AgentRun, Company, CompanyEvidence, CompanySource
from app.models.enums import AgentRunStatus
from app.providers.browser.types import BrowserPageSnapshot
from app.providers.search.exceptions import SearchProviderError, SearchTimeoutError
from app.providers.search.types import SearchResponse, SearchResult


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        max_companies_per_run=20,
        research_search_results_per_query=5,
        research_max_search_pages=1,
        research_verify_with_browser=True,
        max_retries=2,
        database_url="sqlite+pysqlite:///:memory:",
    )
    base.update(overrides)
    return Settings(**base)


def _hit(
    *,
    url: str,
    title: str = "Acme GmbH",
    snippet: str = "Acme builds widgets",
    domain: str = "acme.example",
) -> SearchResult:
    return SearchResult(
        title=title,
        url=url,
        normalized_url=url,
        snippet=snippet,
        domain=domain,
        relevance_score=0.9,
        trust_level="untrusted",
    )


def _search_response(results: list[SearchResult], cost: str = "0.01") -> SearchResponse:
    return SearchResponse(
        query="q",
        results=results,
        provider="tavily",
        result_count=len(results),
        estimated_cost=Decimal(cost),
        latency_ms=1.0,
        untrusted_content=True,
    )


@pytest.fixture()
def research_env(db_session, settings):
    cfg = _settings()
    search = MagicMock()
    browser = MagicMock()
    browser.is_available.return_value = True
    agent = ResearchAgent(
        session=db_session,
        search_service=search,
        browser_service=browser,
        settings=cfg,
        sleep_fn=lambda _s: None,
    )
    return agent, search, browser, db_session, cfg


def test_valid_research(research_env):
    agent, search, browser, session, _cfg = research_env
    search.search.return_value = _search_response(
        [_hit(url="https://acme.example/about", title="Acme GmbH | Home")]
    )
    browser.fetch_page.return_value = BrowserPageSnapshot(
        requested_url="https://acme.example/",
        final_url="https://acme.example/",
        title="Acme GmbH",
        visible_text="",
        page_metadata={"description": "Official Acme site"},
        status_code=200,
        domain="acme.example",
        execution_id="exec-1",
        trust_level="untrusted",
        untrusted_content=True,
    )

    result = agent.run(ResearchRequest(query="widget companies berlin", location="Berlin"))

    assert result.status == "succeeded"
    assert result.companies_created == 1
    assert result.estimated_cost == Decimal("0.01")
    company = session.scalar(select(Company).where(Company.website_domain == "acme.example"))
    assert company is not None
    assert company.name == "Acme GmbH"
    assert company.website == "https://acme.example/"
    assert company.source == "research_agent"
    sources = session.scalars(select(CompanySource).where(CompanySource.company_id == company.id)).all()
    assert sources
    evidence = session.scalars(
        select(CompanyEvidence).where(CompanyEvidence.company_id == company.id)
    ).all()
    assert any(e.field_name == "email" and e.verification_status == "unknown" for e in evidence)
    assert any(e.field_name == "phone" and e.field_value is None for e in evidence)
    run = session.get(AgentRun, result.agent_run_id)
    assert run is not None
    assert run.status == AgentRunStatus.SUCCEEDED
    assert run.agent_name == "research"


def test_duplicate_company(research_env):
    agent, search, browser, session, _cfg = research_env
    session.add(
        Company(
            name="Acme GmbH",
            website="https://acme.example/",
            website_domain="acme.example",
            source="seed",
        )
    )
    session.commit()

    search.search.return_value = _search_response(
        [_hit(url="https://acme.example/pricing", title="Acme GmbH Pricing")]
    )
    browser.is_available.return_value = False

    result = agent.run(ResearchRequest(query="acme"))

    assert result.companies_created == 0
    assert result.companies_duplicate == 1
    assert session.scalars(select(Company)).all().__len__() == 1
    sources = session.scalars(select(CompanySource)).all()
    assert len(sources) >= 1


def test_invalid_url_skipped(research_env):
    agent, search, browser, _session, _cfg = research_env
    search.search.return_value = _search_response(
        [
            _hit(url="javascript:alert(1)", title="Nope", domain=""),
            _hit(url="https://validco.example/", title="Valid Co"),
        ]
    )
    browser.is_available.return_value = False

    result = agent.run(ResearchRequest(query="companies"))

    assert result.companies_created == 1
    assert result.candidates_skipped >= 1
    assert any("invalid_url" in log for log in result.logs)


def test_missing_information_skipped(research_env):
    agent, search, browser, _session, _cfg = research_env
    search.search.return_value = _search_response(
        [_hit(url="https://noname.example/", title="", snippet="")]
    )
    browser.is_available.return_value = False

    result = agent.run(ResearchRequest(query="companies"))

    assert result.companies_created == 0
    assert any("missing_name" in log for log in result.logs)


def test_provider_failure(research_env):
    agent, search, _browser, session, _cfg = research_env
    search.search.side_effect = SearchProviderError("boom", details={"retryable": False})

    result = agent.run(ResearchRequest(query="companies"))

    assert result.status == "failed"
    assert result.error_message and "search_failure" in result.error_message
    run = session.get(AgentRun, result.agent_run_id)
    assert run is not None
    assert run.status == AgentRunStatus.FAILED


def test_database_failure_on_create(research_env):
    agent, search, browser, session, _cfg = research_env
    search.search.return_value = _search_response(
        [_hit(url="https://acme.example/", title="Acme")]
    )
    browser.is_available.return_value = False

    original_commit = session.commit

    def fail_commit():
        raise SQLAlchemyError("disk broken")

    # Fail on final commit after processing
    real_flush = session.flush

    def counting_flush(*args, **kwargs):
        return real_flush(*args, **kwargs)

    session.flush = counting_flush  # type: ignore[method-assign]
    session.commit = fail_commit  # type: ignore[method-assign]

    result = agent.run(ResearchRequest(query="companies"))
    assert result.status == "failed"
    assert result.error_message and "database_failure" in result.error_message
    session.commit = original_commit  # type: ignore[method-assign]


def test_retry_on_search_timeout(research_env):
    agent, search, browser, _session, _cfg = research_env
    search.search.side_effect = [
        SearchTimeoutError("timeout"),
        _search_response([_hit(url="https://acme.example/", title="Acme GmbH")]),
    ]
    browser.is_available.return_value = False

    result = agent.run(ResearchRequest(query="companies"))

    assert result.status == "succeeded"
    assert result.companies_created == 1
    assert search.search.call_count == 2
    assert any("search_retry" in log for log in result.logs)


def test_idempotency(research_env):
    agent, search, browser, session, _cfg = research_env
    search.search.return_value = _search_response(
        [_hit(url="https://acme.example/", title="Acme GmbH")]
    )
    browser.is_available.return_value = False

    first = agent.run(ResearchRequest(query="companies", idempotency_key="research-1"))
    second = agent.run(ResearchRequest(query="companies", idempotency_key="research-1"))

    assert first.status == "succeeded"
    assert second.idempotent_replay is True
    assert second.agent_run_id == first.agent_run_id
    assert search.search.call_count == 1
    assert len(session.scalars(select(Company)).all()) == 1


def test_candidate_extraction_never_invents_contact():
    candidate = candidate_from_search_result(
        _hit(url="https://acme.example/", title="Acme", snippet="Call us someday")
    )
    assert candidate is not None
    assert candidate.email.status == "unknown"
    assert candidate.email.value is None
    assert candidate.phone.status == "unknown"
    assert candidate.address.status == "unknown"


def test_max_companies_limit(research_env):
    agent, search, browser, _session, cfg = research_env
    cfg.max_companies_per_run = 2
    agent._settings = cfg
    hits = [
        _hit(url=f"https://co{i}.example/", title=f"Company {i}", domain=f"co{i}.example")
        for i in range(5)
    ]
    search.search.return_value = _search_response(hits)
    browser.is_available.return_value = False

    result = agent.run(ResearchRequest(query="companies", max_companies=2))

    assert result.companies_created == 2
    assert any("max_companies_reached" in log for log in result.logs)
