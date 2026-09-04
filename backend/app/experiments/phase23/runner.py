"""Phase 23 experiment runner — controlled real-world pilot, no auto-send."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.audit import AuditAgent, AuditRequest
from app.agents.sales import SalesAgent, SalesRequest
from app.approvals import ApprovalService
from app.config import Settings
from app.experiments.phase23.niche import (
    INDUSTRY,
    LOCATION,
    NICHE_ID,
    NICHE_LABEL,
    SEED_COMPANIES,
)
from app.models import (
    AgentRun,
    Approval,
    Company,
    CompanyAudit,
    CompanyEvidence,
    CompanyScore,
    CompanySource,
    CostEntry,
    Lead,
    Outreach,
)
from app.models.base import utc_now
from app.models.enums import (
    AgentRunStatus,
    CompanyStatus,
    LeadScoreCategory,
    LeadStatus,
    OutreachStatus,
)
from app.pilot.budget import BudgetGuard
from app.pilot.limits import LimitService
from app.services.browser_service import build_browser_service
from app.services.lead_scoring_service import LeadScoringService

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?:\+49|0)\s*\d[\d\s\-/\(\)]{6,}\d")
_MAILTO_RE = re.compile(r"mailto:([^\"'\s>]+)", re.I)
_TEL_RE = re.compile(r"tel:([^\"'\s>]+)", re.I)

# Conservative fit threshold for pilot (0–100 scale from scoring engine)
QUALIFIED_SCORE_MIN = 55


@dataclass
class CompanyExperimentRecord:
    name: str
    website: str
    district: str
    company_id: str | None = None
    verified: bool = False
    verification_error: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    has_contact_page: bool = False
    has_booking: bool = False
    has_contact_form: bool = False
    score: float | None = None
    score_band: str | None = None
    good_fit: bool = False
    audited: bool = False
    audit_id: str | None = None
    problems: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    estimated_value_eur: float | None = None
    outreach_id: str | None = None
    outreach_subject: str | None = None
    approval_id: str | None = None
    notes: list[str] = field(default_factory=list)


class Phase23ExperimentRunner:
    """Execute the Phase 23 pilot experiment under Pilot Mode limits."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        output_dir: Path,
        max_companies: int = 20,
    ) -> None:
        self._session = session
        self._settings = settings
        self._output_dir = output_dir
        self._max_companies = min(max_companies, settings.max_companies_per_day, 20)
        self._limits = LimitService(session, settings)
        self._budget = BudgetGuard(session, settings)
        self._browser = build_browser_service(settings)
        self._scoring = LeadScoringService(session)
        self._approvals = ApprovalService(session, settings)
        self._audit = AuditAgent(
            session=session,
            browser_service=self._browser,
            search_service=None,
            ai_service=None,
            settings=settings,
        )
        self._sales = SalesAgent(
            session=session,
            settings=settings,
            ai_service=None,
            approval_service=self._approvals,
        )
        self._started = utc_now()
        self._agent_run = AgentRun(
            agent_name="phase23_experiment",
            task_type="controlled_pilot_experiment",
            status=AgentRunStatus.RUNNING,
            input_summary=f"niche={NICHE_ID} max={self._max_companies}",
            estimated_cost=Decimal("0"),
            extra_metadata={
                "phase": 23,
                "niche": NICHE_ID,
                "auto_send": False,
                "discovery": "public_web_seed_list_tavily_unavailable",
            },
        )

    def run(self) -> dict[str, Any]:
        self._session.add(self._agent_run)
        self._session.flush()

        records: list[CompanyExperimentRecord] = []
        seeds = SEED_COMPANIES[: self._max_companies]

        for seed in seeds:
            if self._limits.remaining_companies_capacity() <= 0:
                break
            rec = self._process_company(seed)
            records.append(rec)
            self._session.commit()

        # Audit up to pilot daily audit cap among verified companies (prefer higher scores)
        audited_targets = sorted(
            [r for r in records if r.verified and r.company_id],
            key=lambda r: r.score or 0,
            reverse=True,
        )
        audit_cap = min(
            self._settings.max_audits_per_day,
            self._limits.remaining_audits_capacity(),
            len(audited_targets),
        )
        to_audit = audited_targets[:audit_cap]
        if to_audit:
            self._run_audits(to_audit)
            self._session.commit()

        # Draft + queue approval for good-fit audited companies only (never send)
        for rec in records:
            if rec.good_fit and rec.audited and rec.company_id:
                self._draft_and_queue(rec)
                self._session.commit()

        report = self._build_report(records)
        self._write_outputs(report, records)

        self._agent_run.status = AgentRunStatus.SUCCEEDED
        self._agent_run.completed_at = utc_now()
        self._agent_run.output_summary = (
            f"researched={len(records)} verified={sum(1 for r in records if r.verified)} "
            f"qualified={sum(1 for r in records if r.good_fit)} "
            f"audits={sum(1 for r in records if r.audited)} "
            f"drafts={sum(1 for r in records if r.outreach_id)}"
        )
        self._session.commit()
        return report

    # ------------------------------------------------------------------ steps
    def _process_company(self, seed: dict[str, str]) -> CompanyExperimentRecord:
        rec = CompanyExperimentRecord(
            name=seed["name"],
            website=seed["website"],
            district=seed.get("district", "Berlin"),
        )
        domain = (urlsplit(seed["website"]).hostname or "").lower().removeprefix("www.")
        existing = self._session.scalar(select(Company).where(Company.website_domain == domain))
        if existing is not None:
            company = existing
            rec.notes.append("existing_company_reused")
        else:
            company = Company(
                name=seed["name"][:255],
                website=seed["website"],
                website_domain=domain or None,
                industry=INDUSTRY,
                location=f"{seed.get('district', 'Berlin')}, {LOCATION}",
                description=f"Independent dental practice candidate for Phase 23 niche experiment ({NICHE_ID}).",
                source="phase23_public_web_seed",
                status=CompanyStatus.PROSPECT,
            )
            self._session.add(company)
            self._session.flush()

        rec.company_id = str(company.id)
        self._session.add(
            CompanySource(
                company_id=company.id,
                url=seed["website"],
                normalized_url=seed["website"].rstrip("/").lower(),
                title=seed["name"],
                source_type="website",
                agent_run_id=self._agent_run.id,
            )
        )

        snapshot = None
        try:
            if not self._browser.is_available():
                raise RuntimeError("browser_unavailable")
            snapshot = self._browser.fetch_page(
                seed["website"],
                include_links=True,
                include_metadata=True,
                include_text=True,
                metadata={"phase": 23, "niche": NICHE_ID},
            )
            rec.verified = True
            company.website = snapshot.final_url or company.website
            self._add_evidence(
                company,
                field_name="website",
                value=snapshot.final_url or seed["website"],
                status="verified",
                source_url=snapshot.final_url or seed["website"],
            )
        except Exception as exc:  # noqa: BLE001 — per-company soft fail
            rec.verified = False
            rec.verification_error = f"{type(exc).__name__}: {exc}"[:300]
            self._add_evidence(
                company,
                field_name="website",
                value=seed["website"],
                status="unverified",
                source_url=seed["website"],
            )
            rec.notes.append(f"verify_failed:{type(exc).__name__}")
            return rec

        text = snapshot.visible_text or ""
        link_blob = " ".join(f"{lnk.url} {lnk.text}" for lnk in (snapshot.links or []))
        blob = f"{text}\n{link_blob}"
        emails = self._extract_emails(blob)
        phones = self._extract_phones(blob)
        rec.public_email = emails[0] if emails else None
        rec.public_phone = phones[0] if phones else None
        rec.has_contact_page = bool(re.search(r"kontakt|contact", blob, re.I))
        rec.has_booking = bool(re.search(r"termin|doctolib|book|calendar", blob, re.I))
        rec.has_contact_form = bool(re.search(r"formular|contact form|nachricht senden", blob, re.I))

        if rec.public_email:
            self._add_evidence(
                company,
                field_name="email",
                value=rec.public_email,
                status="verified",
                source_url=snapshot.final_url,
            )
        if rec.public_phone:
            self._add_evidence(
                company,
                field_name="phone",
                value=rec.public_phone,
                status="verified",
                source_url=snapshot.final_url,
            )
        if seed.get("district"):
            self._add_evidence(
                company,
                field_name="address",
                value=f"{seed['district']}, Berlin",
                status="unverified",
                source_url=snapshot.final_url,
            )

        self._session.flush()
        score_result = self._scoring.score_company(
            company.id,
            has_contact_page=rec.has_contact_page,
            has_contact_form=rec.has_contact_form,
            has_booking_or_calendar=rec.has_booking,
            persist=True,
        )
        rec.score = float(score_result.total_score)
        rec.score_band = str(score_result.band)
        rec.good_fit = rec.score >= QUALIFIED_SCORE_MIN and rec.verified
        rec.notes.append(f"score={rec.score:.1f}")
        return rec

    def _run_audits(self, targets: list[CompanyExperimentRecord]) -> None:
        ids = [UUID(r.company_id) for r in targets if r.company_id]
        if not ids:
            return
        result = self._audit.run(
            AuditRequest(
                company_ids=ids,
                max_audits=len(ids),
                use_ai=False,
                idempotency_key=f"phase23-audit-{self._agent_run.id}",
                metadata={"phase": 23, "niche": NICHE_ID},
            )
        )
        by_company = {str(item.company_id): item for item in result.results}
        for rec in targets:
            item = by_company.get(rec.company_id or "")
            if item is None:
                continue
            rec.audited = item.status != "failed"
            audit_row = self._session.scalar(
                select(CompanyAudit)
                .where(CompanyAudit.company_id == UUID(rec.company_id))
                .order_by(CompanyAudit.created_at.desc())
            )
            rec.audit_id = str(audit_row.id) if audit_row else None
            rec.problems = [f.title for f in item.problems][:8]
            rec.opportunities = [f.title for f in item.opportunities][:8]
            values = [
                float(f.estimated_business_value)
                for f in list(item.problems) + list(item.opportunities)
                if f.estimated_business_value is not None
            ]
            if item.estimated_business_value is not None:
                values.append(float(item.estimated_business_value))
            if values:
                positive = [v for v in values if v > 0]
                rec.estimated_value_eur = min(positive) if positive else 0.0
            elif rec.good_fit:
                rec.estimated_value_eur = 250.0
                rec.notes.append("value_estimate_conservative_placeholder_eur_250")

    def _draft_and_queue(self, rec: CompanyExperimentRecord) -> None:
        assert rec.company_id
        company_id = UUID(rec.company_id)
        lead = self._session.scalar(select(Lead).where(Lead.company_id == company_id))
        if lead is None:
            lead = Lead(
                company_id=company_id,
                name=f"Practice contact — {rec.name}"[:255],
                email=rec.public_email,
                phone=rec.public_phone,
                job_title="Practice owner / management",
                source="phase23_experiment",
                status=LeadStatus.NEW,
                score_category=LeadScoreCategory.UNSCORED,
            )
            self._session.add(lead)
            self._session.flush()

        score = self._session.scalar(
            select(CompanyScore)
            .where(CompanyScore.company_id == company_id)
            .order_by(CompanyScore.scored_at.desc())
        )
        audit = None
        if rec.audit_id:
            audit = self._session.get(CompanyAudit, UUID(rec.audit_id))

        sales_result = self._sales.run(
            SalesRequest(
                company_id=company_id,
                lead_id=lead.id,
                company_score_id=score.id if score else None,
                company_audit_id=audit.id if audit else None,
                use_ai=False,
                idempotency_key=f"phase23-draft-{company_id}",
                metadata={"phase": 23, "auto_send": False},
            )
        )
        if sales_result.status != "succeeded" or sales_result.outreach is None:
            rec.notes.append(f"draft_failed:{sales_result.error_message}")
            return

        outreach_id = sales_result.outreach.outreach_id
        rec.outreach_id = str(outreach_id)
        rec.outreach_subject = sales_result.outreach.subject
        # Queue for owner approval — NEVER send
        approval_id = self._sales.request_send_approval(
            outreach_id, requested_by="phase23_experiment"
        )
        rec.approval_id = str(approval_id)
        rec.notes.append("queued_for_approval_not_sent")

    # ---------------------------------------------------------------- helpers
    def _add_evidence(
        self,
        company: Company,
        *,
        field_name: str,
        value: str,
        status: str,
        source_url: str | None,
    ) -> None:
        self._session.add(
            CompanyEvidence(
                company_id=company.id,
                field_name=field_name,
                field_value=value[:2000],
                verification_status=status,
                source_url=source_url,
                agent_run_id=self._agent_run.id,
                source_type="browser",
            )
        )

    @staticmethod
    def _extract_emails(text: str) -> list[str]:
        found: list[str] = []
        for match in _MAILTO_RE.findall(text):
            email = match.strip().split("?")[0]
            if email and email not in found and "example" not in email.lower():
                found.append(email)
        for match in _EMAIL_RE.findall(text):
            email = match.strip()
            if (
                email
                and email not in found
                and "example" not in email.lower()
                and not email.lower().endswith((".png", ".jpg", ".webp", ".svg"))
            ):
                found.append(email)
        return found[:5]

    @staticmethod
    def _extract_phones(text: str) -> list[str]:
        found: list[str] = []
        for match in _TEL_RE.findall(text):
            phone = re.sub(r"\s+", " ", match.strip())
            if phone and phone not in found:
                found.append(phone)
        for match in _PHONE_RE.findall(text):
            phone = re.sub(r"\s+", " ", match.strip())
            if phone and phone not in found and len(re.sub(r"\D", "", phone)) >= 8:
                found.append(phone)
        return found[:5]

    def _build_report(self, records: list[CompanyExperimentRecord]) -> dict[str, Any]:
        verified = [r for r in records if r.verified]
        qualified = [r for r in records if r.good_fit]
        audited = [r for r in records if r.audited]
        drafts = [r for r in records if r.outreach_id]
        scores = [r.score for r in verified if r.score is not None]
        problem_counter: Counter[str] = Counter()
        opportunity_counter: Counter[str] = Counter()
        for r in audited:
            problem_counter.update(r.problems)
            opportunity_counter.update(r.opportunities)

        verify_fails = [r for r in records if not r.verified]
        verified_no_email = sum(1 for r in verified if not r.public_email)
        major_problems = [p for p, _ in problem_counter.most_common(10)]
        if verify_fails:
            major_problems.insert(
                0,
                f"Website verification failed for {len(verify_fails)}/{len(records)} seeds",
            )
        if verified and verified_no_email:
            major_problems.insert(
                0,
                f"No public email on primary page for {verified_no_email}/{len(verified)} verified",
            )
        if not major_problems:
            major_problems = [
                "Deterministic audits flagged opportunities more than severity-labeled problems"
            ]

        opportunity_values = [r.estimated_value_eur for r in audited if r.estimated_value_eur]
        spent = self._budget.status().spent_today

        # Expected costs: browser free; no paid search/AI in this run
        expected_costs = {
            "search_api": "0.00 (Tavily not configured — public seed list used)",
            "ai_enrichment": "0.00 (disabled for experiment)",
            "browser": "0.00 (local Playwright)",
            "email_send": "0.00 (no sends — approval queue only)",
            "conservative_total_eur": "0.00–0.50 if providers later enabled for re-run",
        }

        analysis = {
            "strongest_niche_signal": (
                f"{NICHE_LABEL} shows dense local competition and frequent online booking "
                "hooks (Doctolib / Termin). Fit depends on website quality and contactability — "
                "not guaranteed revenue."
            ),
            "most_common_problems": [p for p, _ in problem_counter.most_common(5)],
            "most_common_opportunities": [o for o, _ in opportunity_counter.most_common(5)],
            "most_valuable_offer_hypothesis": (
                "Conservative hypothesis to test (not proven): website conversion cleanup + "
                "online booking / reminder automation for practices with weak digital funnels."
            ),
            "outreach_strategy_to_test": (
                "Short, evidence-grounded German/English bilingual draft citing one verified "
                "website observation; CTA = 15-minute diagnostic call. Owner approval required "
                "before any send. Sample size should stay tiny (≤5 approved sends) if testing."
            ),
            "what_not_to_do": [
                "Do not mass-email the seed list",
                "Do not auto-send first outreach",
                "Do not raise pilot limits for this experiment",
                "Do not claim product-market fit from this single niche run",
                "Do not invent contact emails when none are public",
            ],
            "limitations": [
                "Tavily/OpenAI not configured — discovery used a curated public seed list",
                "Value estimates are conservative heuristics when audits lack numeric EUR values",
                "No outreach was sent; conversion is unknown",
                "Single niche only — cannot compare niches empirically yet",
            ],
            "success_claims": "NONE — experiment completed; commercial success is not demonstrated.",
        }

        return {
            "phase": 23,
            "experiment": "controlled_real_world_pilot",
            "niche": {"id": NICHE_ID, "label": NICHE_LABEL, "location": LOCATION},
            "pilot_mode": True,
            "auto_send": False,
            "started_at": self._started.isoformat(),
            "finished_at": utc_now().isoformat(),
            "agent_run_id": str(self._agent_run.id),
            "ceo_report": {
                "companies_researched": len(records),
                "companies_verified": len(verified),
                "qualified_leads": len(qualified),
                "average_score": round(sum(scores) / len(scores), 2) if scores else None,
                "audits_completed": len(audited),
                "major_problems_discovered": major_problems,
                "common_opportunities": [o for o, _ in opportunity_counter.most_common(10)],
                "outreach_drafts": len(drafts),
                "approvals_queued": sum(1 for r in drafts if r.approval_id),
                "estimated_opportunity_value_eur": {
                    "sum_conservative": round(sum(opportunity_values), 2) if opportunity_values else 0,
                    "count_with_estimate": len(opportunity_values),
                    "note": "Not revenue. Conservative audit/heuristic estimates only.",
                },
                "expected_costs": expected_costs,
                "actual_costs_eur": str(spent),
                "risks": [
                    "Cold outreach may harm brand if unapproved or poorly personalized",
                    "Public emails may be generic inboxes with low reply rates",
                    "Website verification can fail (blocking, geo, JS-heavy sites)",
                    "Pilot budget is only 3 EUR/day — paid APIs must stay off or tiny",
                ],
                "recommendations": [
                    "Keep Pilot Mode on",
                    "Owner reviews queued approvals one-by-one",
                    "If testing sends, approve ≤5 and measure replies before any scale talk",
                    "Configure Tavily for broader discovery only after this baseline review",
                ],
            },
            "analysis": analysis,
            "companies": [r.__dict__ for r in records],
        }

    def _write_outputs(self, report: dict[str, Any], records: list[CompanyExperimentRecord]) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self._output_dir / "experiment_report.json"
        md_path = self._output_dir / "CEO_EXPERIMENT_REPORT.md"
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        md_path.write_text(self._render_markdown(report, records), encoding="utf-8")
        logger.info("Phase 23 report written to %s", md_path)

    def _render_markdown(self, report: dict[str, Any], records: list[CompanyExperimentRecord]) -> str:
        ceo = report["ceo_report"]
        analysis = report["analysis"]
        lines = [
            "# Phase 23 — CEO Experiment Report",
            "",
            f"**Niche:** {NICHE_LABEL}  ",
            f"**Mode:** Pilot (no auto-send)  ",
            f"**Started:** {report['started_at']}  ",
            f"**Finished:** {report['finished_at']}  ",
            "",
            "> This is an experiment, not a guarantee. No commercial success is claimed.",
            "",
            "## Results summary",
            "",
            f"- Companies researched: **{ceo['companies_researched']}**",
            f"- Companies verified: **{ceo['companies_verified']}**",
            f"- Qualified leads (score ≥ {QUALIFIED_SCORE_MIN}): **{ceo['qualified_leads']}**",
            f"- Average score (verified): **{ceo['average_score']}**",
            f"- Audits completed: **{ceo['audits_completed']}**",
            f"- Outreach drafts: **{ceo['outreach_drafts']}**",
            f"- Approvals queued (not sent): **{ceo['approvals_queued']}**",
            f"- Estimated opportunity value (conservative EUR sum): **{ceo['estimated_opportunity_value_eur']['sum_conservative']}**",
            f"- Actual ledger costs (EUR): **{ceo['actual_costs_eur']}**",
            "",
            "## Major problems discovered",
            "",
        ]
        for p in ceo["major_problems_discovered"] or ["(none recorded from audits)"]:
            lines.append(f"- {p}")
        lines += ["", "## Common opportunities", ""]
        for o in ceo["common_opportunities"] or ["(none recorded from audits)"]:
            lines.append(f"- {o}")
        lines += ["", "## Expected vs actual costs", "", "### Expected", ""]
        for k, v in ceo["expected_costs"].items():
            lines.append(f"- {k}: {v}")
        lines += ["", f"### Actual: {ceo['actual_costs_eur']} EUR", "", "## Risks", ""]
        for r in ceo["risks"]:
            lines.append(f"- {r}")
        lines += ["", "## Recommendations", ""]
        for r in ceo["recommendations"]:
            lines.append(f"- {r}")
        lines += [
            "",
            "## Experiment analysis",
            "",
            f"**Strongest niche signal:** {analysis['strongest_niche_signal']}",
            "",
            f"**Most valuable offer hypothesis:** {analysis['most_valuable_offer_hypothesis']}",
            "",
            f"**Outreach strategy to test:** {analysis['outreach_strategy_to_test']}",
            "",
            "### What NOT to do",
            "",
        ]
        for item in analysis["what_not_to_do"]:
            lines.append(f"- {item}")
        lines += ["", "### Limitations", ""]
        for item in analysis["limitations"]:
            lines.append(f"- {item}")
        lines += [
            "",
            f"**Success claims:** {analysis['success_claims']}",
            "",
            "## Company detail",
            "",
            "| Company | Verified | Score | Fit | Audited | Draft | Approval |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in records:
            lines.append(
                f"| {r.name} | {r.verified} | {r.score if r.score is not None else '-'} | "
                f"{r.good_fit} | {r.audited} | {bool(r.outreach_id)} | {bool(r.approval_id)} |"
            )
        lines += [
            "",
            "## Outreach drafts (subjects only)",
            "",
        ]
        for r in records:
            if r.outreach_subject:
                lines.append(f"- **{r.name}:** {r.outreach_subject}")
        if not any(r.outreach_subject for r in records):
            lines.append("- (no drafts created)")
        lines.append("")
        return "\n".join(lines)


def run_phase23_experiment(
    session: Session,
    settings: Settings,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    runner = Phase23ExperimentRunner(session, settings, output_dir=output_dir)
    return runner.run()
