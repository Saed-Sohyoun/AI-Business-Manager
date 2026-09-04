"""Research Agent — discover real businesses from public web evidence.

Uses SearchProvider + BrowserService + Database.
Never invents companies, websites, emails, phones, addresses, or facts.
Never contacts companies or sends email.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.research.extraction import (
    apply_browser_verification,
    candidate_from_search_result,
    normalized_source,
)
from app.agents.research.schemas import (
    ResearchCandidate,
    ResearchRequest,
    ResearchRunResult,
    StoredCompanySummary,
)
from app.config import Settings
from app.models import AgentRun, Company, CompanyEvidence, CompanySource
from app.models.base import utc_now
from app.models.enums import AgentRunStatus, CompanyStatus
from app.providers.search.exceptions import (
    SearchError,
    SearchRateLimitError,
    SearchTimeoutError,
)
from app.services.browser_service import BrowserService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

AGENT_NAME = "research"
TASK_TYPE = "discover_companies"


class ResearchAgent:
    """Deterministic research worker — evidence in, memory out."""

    def __init__(
        self,
        *,
        session: Session,
        search_service: SearchService,
        browser_service: BrowserService | None,
        settings: Settings,
        sleep_fn: Any | None = None,
    ) -> None:
        self._session = session
        self._search = search_service
        self._browser = browser_service
        self._settings = settings
        self._sleep = sleep_fn or time.sleep

    def run(self, request: ResearchRequest) -> ResearchRunResult:
        logs: list[str] = []
        max_companies = min(
            request.max_companies or self._settings.max_companies_per_run,
            self._settings.max_companies_per_run,
        )
        from app.pilot.limits import LimitService

        daily_remaining = LimitService(self._session, self._settings).remaining_companies_capacity()
        max_companies = min(max_companies, daily_remaining)
        if max_companies <= 0:
            logs.append("pilot_limit:companies_per_day")
            return ResearchRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                query=request.query,
                error_message="limit_reached:max_companies_per_day",
                logs=logs,
            )
        verify = (
            self._settings.research_verify_with_browser
            if request.verify_with_browser is None
            else request.verify_with_browser
        )

        if request.idempotency_key:
            existing = self._find_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                logs.append("idempotent_replay")
                return self._result_from_existing_run(existing, request, logs=logs)

        agent_run = AgentRun(
            agent_name=AGENT_NAME,
            task_type=TASK_TYPE,
            status=AgentRunStatus.RUNNING,
            input_summary=f"query={request.query!r} max_companies={max_companies}",
            idempotency_key=request.idempotency_key,
            estimated_cost=Decimal("0"),
            extra_metadata={
                "industry": request.industry,
                "location": request.location,
                "verify_with_browser": verify,
                **(request.metadata or {}),
            },
        )
        try:
            self._session.add(agent_run)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.exception("Failed to create AgentRun")
            return ResearchRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                query=request.query,
                error_message=f"database_failure: {type(exc).__name__}",
                logs=["database_failure_on_run_create"],
            )

        estimated_cost = Decimal("0")
        stored: list[StoredCompanySummary] = []
        created = 0
        duplicates = 0
        skipped = 0
        candidates_seen = 0
        seen_domains: set[str] = set()

        try:
            search_hits, search_cost, search_logs = self._search_with_retry(request)
            logs.extend(search_logs)
            estimated_cost += search_cost

            for result in search_hits:
                if created + duplicates >= max_companies:
                    logs.append("max_companies_reached")
                    break

                candidates_seen += 1
                candidate = candidate_from_search_result(result)
                if candidate.skipped_reason:
                    skipped += 1
                    logs.append(f"skipped:{candidate.skipped_reason}:{result.url}")
                    continue
                if not candidate.website_domain:
                    skipped += 1
                    logs.append(f"skipped:missing_domain:{result.url}")
                    continue
                if candidate.website_domain in seen_domains:
                    skipped += 1
                    logs.append(f"skipped:in_run_duplicate:{candidate.website_domain}")
                    continue

                if verify and self._browser is not None and self._browser.is_available():
                    candidate, browser_cost, blog = self._verify_candidate(candidate)
                    estimated_cost += browser_cost
                    logs.extend(blog)

                if not candidate.name.value:
                    # Require an observed name — do not invent
                    skipped += 1
                    logs.append(f"skipped:missing_name:{candidate.website_domain}")
                    continue

                summary, clog = self._persist_candidate(candidate, agent_run_id=agent_run.id)
                logs.extend(clog)
                if summary is None:
                    skipped += 1
                    continue

                seen_domains.add(candidate.website_domain)
                stored.append(summary)
                if summary.duplicate:
                    duplicates += 1
                else:
                    created += 1

            status = AgentRunStatus.SUCCEEDED
            result_status: str = "succeeded"
            if created == 0 and duplicates == 0 and candidates_seen > 0:
                result_status = "partial"
            agent_run.status = status
            agent_run.estimated_cost = estimated_cost
            agent_run.output_summary = (
                f"created={created} duplicates={duplicates} "
                f"skipped={skipped} seen={candidates_seen}"
            )
            agent_run.completed_at = utc_now()
            agent_run.extra_metadata = {
                **(agent_run.extra_metadata or {}),
                "logs": logs[-50:],
            }
            self._session.commit()

            return ResearchRunResult(
                agent_run_id=agent_run.id,
                status=result_status,  # type: ignore[arg-type]
                query=request.query,
                companies_created=created,
                companies_duplicate=duplicates,
                candidates_seen=candidates_seen,
                candidates_skipped=skipped,
                stored=stored,
                estimated_cost=estimated_cost,
                logs=logs,
            )
        except SearchError as exc:
            return self._fail_run(agent_run, request, logs, estimated_cost, f"search_failure: {exc.code}")
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.exception("Research database failure")
            # Best-effort mark failed in a fresh transaction state
            try:
                agent_run = self._session.merge(agent_run)
                agent_run.status = AgentRunStatus.FAILED
                agent_run.error_message = f"database_failure: {type(exc).__name__}"
                agent_run.completed_at = utc_now()
                agent_run.estimated_cost = estimated_cost
                self._session.commit()
            except SQLAlchemyError:
                self._session.rollback()
            return ResearchRunResult(
                agent_run_id=agent_run.id,
                status="failed",
                query=request.query,
                estimated_cost=estimated_cost,
                error_message=f"database_failure: {type(exc).__name__}",
                logs=[*logs, "database_failure"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Research agent unexpected failure")
            return self._fail_run(
                agent_run,
                request,
                logs,
                estimated_cost,
                f"unexpected_failure: {type(exc).__name__}",
            )

    def _fail_run(
        self,
        agent_run: AgentRun,
        request: ResearchRequest,
        logs: list[str],
        estimated_cost: Decimal,
        message: str,
    ) -> ResearchRunResult:
        try:
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = message
            agent_run.completed_at = utc_now()
            agent_run.estimated_cost = estimated_cost
            agent_run.extra_metadata = {**(agent_run.extra_metadata or {}), "logs": logs[-50:]}
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
        return ResearchRunResult(
            agent_run_id=agent_run.id,
            status="failed",
            query=request.query,
            estimated_cost=estimated_cost,
            error_message=message,
            logs=[*logs, message],
        )

    def _find_by_idempotency_key(self, key: str) -> AgentRun | None:
        stmt = select(AgentRun).where(
            AgentRun.idempotency_key == key,
            AgentRun.agent_name == AGENT_NAME,
        )
        return self._session.scalar(stmt)

    def _result_from_existing_run(
        self,
        run: AgentRun,
        request: ResearchRequest,
        *,
        logs: list[str],
    ) -> ResearchRunResult:
        status = "succeeded" if run.status == AgentRunStatus.SUCCEEDED else "failed"
        if run.status == AgentRunStatus.FAILED:
            status = "failed"
        return ResearchRunResult(
            agent_run_id=run.id,
            status=status,  # type: ignore[arg-type]
            query=request.query,
            estimated_cost=run.estimated_cost or Decimal("0"),
            idempotent_replay=True,
            error_message=run.error_message,
            logs=logs,
        )

    def _search_with_retry(
        self,
        request: ResearchRequest,
    ) -> tuple[list, Decimal, list[str]]:
        logs: list[str] = []
        cost = Decimal("0")
        results: list = []
        pages = self._settings.research_max_search_pages
        per_page = self._settings.research_search_results_per_query
        max_retries = self._settings.max_retries

        for page in range(pages):
            # Simple pagination via query suffix — no fabricated businesses
            query = request.query if page == 0 else f"{request.query} page {page + 1}"
            if request.location and page == 0:
                query = f"{request.query} {request.location}".strip()
            if request.industry and page == 0:
                query = f"{query} {request.industry}".strip()

            attempt = 0
            while True:
                attempt += 1
                try:
                    response = self._search.search(
                        query,
                        max_results=per_page,
                        metadata={"agent": AGENT_NAME, "page": page},
                    )
                    cost += response.estimated_cost
                    results.extend(response.results)
                    logs.append(
                        f"search_ok:page={page}:results={len(response.results)}:cost={response.estimated_cost}"
                    )
                    break
                except (SearchTimeoutError, SearchRateLimitError) as exc:
                    logs.append(f"search_retry:{exc.code}:attempt={attempt}")
                    if attempt > max_retries:
                        raise
                    self._sleep(min(2**attempt, 5))
                except SearchError:
                    raise

            if len(results) >= self._settings.max_companies_per_run * 2:
                break

        return results, cost, logs

    def _verify_candidate(
        self,
        candidate: ResearchCandidate,
    ) -> tuple[ResearchCandidate, Decimal, list[str]]:
        logs: list[str] = []
        if not candidate.website or not candidate.website.value:
            return candidate, Decimal("0"), ["browser_skip:no_website"]
        assert self._browser is not None
        try:
            snapshot = self._browser.fetch_page(
                candidate.website.value,
                include_links=False,
                include_metadata=True,
                include_text=False,
                metadata={"agent": AGENT_NAME},
            )
            meta_desc = snapshot.page_metadata.get("description") or snapshot.page_metadata.get(
                "og:description"
            )
            updated = apply_browser_verification(
                candidate,
                final_url=snapshot.final_url,
                page_title=snapshot.title,
                meta_description=meta_desc,
                page_source_url=snapshot.final_url,
            )
            logs.append(f"browser_ok:{candidate.website_domain}")
            # Browser has no billed cost field yet — track as zero
            return updated, Decimal("0"), logs
        except Exception as exc:  # noqa: BLE001 — per-candidate soft failure
            logs.append(f"browser_failed:{candidate.website_domain}:{type(exc).__name__}")
            return candidate, Decimal("0"), logs

    def _persist_candidate(
        self,
        candidate: ResearchCandidate,
        *,
        agent_run_id: UUID,
    ) -> tuple[StoredCompanySummary | None, list[str]]:
        logs: list[str] = []
        domain = candidate.website_domain
        if not domain or not candidate.name.value:
            return None, ["persist_skip:incomplete"]

        existing = self._session.scalar(
            select(Company).where(Company.website_domain == domain)
        )
        if existing is not None:
            self._add_sources_and_evidence(existing, candidate, agent_run_id)
            logs.append(f"duplicate:{domain}")
            return (
                StoredCompanySummary(
                    company_id=existing.id,
                    name=existing.name,
                    website=existing.website,
                    website_domain=existing.website_domain,
                    created=False,
                    duplicate=True,
                ),
                logs,
            )

        company = Company(
            name=candidate.name.value[:255],
            website=candidate.website.value,
            website_domain=domain,
            industry=candidate.industry.value,
            location=candidate.location.value,
            description=candidate.description.value,
            source="research_agent",
            status=CompanyStatus.PROSPECT,
        )
        self._session.add(company)
        self._session.flush()
        self._add_sources_and_evidence(company, candidate, agent_run_id)
        logs.append(f"created:{domain}")
        return (
            StoredCompanySummary(
                company_id=company.id,
                name=company.name,
                website=company.website,
                website_domain=company.website_domain,
                created=True,
                duplicate=False,
            ),
            logs,
        )

    def _add_sources_and_evidence(
        self,
        company: Company,
        candidate: ResearchCandidate,
        agent_run_id: UUID,
    ) -> None:
        existing_urls = {
            s.normalized_url
            for s in self._session.scalars(
                select(CompanySource).where(CompanySource.company_id == company.id)
            ).all()
        }
        for url in candidate.source_urls:
            norm = normalized_source(url)
            if not norm or norm in existing_urls:
                continue
            self._session.add(
                CompanySource(
                    company_id=company.id,
                    agent_run_id=agent_run_id,
                    url=url,
                    normalized_url=norm,
                    title=None,
                    source_type="search",
                )
            )
            existing_urls.add(norm)

        fields = {
            "name": candidate.name,
            "website": candidate.website,
            "industry": candidate.industry,
            "location": candidate.location,
            "description": candidate.description,
            "email": candidate.email,
            "phone": candidate.phone,
            "address": candidate.address,
        }
        for field_name, field in fields.items():
            self._session.add(
                CompanyEvidence(
                    company_id=company.id,
                    agent_run_id=agent_run_id,
                    field_name=field_name,
                    field_value=field.value,
                    verification_status=field.status,
                    source_url=field.source_url,
                    excerpt=(field.value[:500] if field.value else None),
                    source_type="research",
                )
            )
