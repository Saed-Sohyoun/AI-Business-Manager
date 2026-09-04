"""Post-process Phase 23 report with contactability and verification findings."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = ROOT / "experiments" / "phase23" / "experiment_report.json"
REPORT_MD = ROOT / "experiments" / "phase23" / "CEO_EXPERIMENT_REPORT.md"


def main() -> None:
    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    companies = data["companies"]
    failed = [c for c in companies if not c["verified"]]
    verified = [c for c in companies if c["verified"]]
    no_email = sum(1 for c in verified if not c.get("public_email"))
    no_phone = sum(1 for c in verified if not c.get("public_phone"))
    booking = sum(1 for c in verified if c.get("has_booking"))
    form = sum(1 for c in verified if c.get("has_contact_form"))
    with_email = sum(1 for c in verified if c.get("public_email"))

    problems = [
        f"Website verification failed for {len(failed)}/20 seeds (DNS/navigation/timeout)",
        f"No public email extracted from homepage for {no_email}/17 verified practices",
        f"No public phone extracted from homepage for {no_phone}/17 verified practices",
        "Deterministic audits flagged conversion gaps more often than severity-labeled problems",
    ]
    for company in failed:
        err = (company.get("verification_error") or "")[:120]
        problems.append(f"Verify fail — {company['name']}: {err}")

    data["ceo_report"]["major_problems_discovered"] = problems
    data["analysis"]["most_common_problems"] = [
        "Missing/hard-to-find public email on primary page",
        "Lead capture form not observed",
        "Weak CTA presence",
        "Verification failures (DNS / navigation / timeout)",
    ]
    data["analysis"]["contactability"] = {
        "verified_with_public_email": with_email,
        "verified_with_public_phone": sum(1 for c in verified if c.get("public_phone")),
        "verified_with_booking_signal": booking,
        "verified_with_contact_form_signal": form,
    }
    data["analysis"]["strongest_niche_signal"] = (
        "Among one tested niche only: Berlin independent dental practices. "
        "Signal strength is provisional — 17/20 sites verified, high booking-signal density "
        f"({booking}/17), but email contactability is uneven ({with_email}/17). "
        "Not compared to other niches; not proof of revenue."
    )
    data["analysis"]["most_valuable_offer_hypothesis"] = (
        "Hypothesis to test next (unproven): conversion/CTA cleanup + clearer lead capture "
        "for practices that already have Termin/Doctolib but weak forms/CTAs. "
        "Booking automation may be less differentiated where Doctolib is already present."
    )

    REPORT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    ceo = data["ceo_report"]
    analysis = data["analysis"]
    lines: list[str] = [
        "# Phase 23 — CEO Experiment Report",
        "",
        f"**Niche:** {data['niche']['label']}  ",
        "**Mode:** Pilot (no auto-send)  ",
        f"**Started:** {data['started_at']}  ",
        f"**Finished:** {data['finished_at']}  ",
        "",
        "> This is an experiment, not a guarantee. No commercial success is claimed. No outreach was sent.",
        "",
        "## Results summary",
        "",
        f"- Companies researched: **{ceo['companies_researched']}**",
        f"- Companies verified: **{ceo['companies_verified']}**",
        f"- Qualified leads (score ≥ 55): **{ceo['qualified_leads']}**",
        f"- Average score (verified): **{ceo['average_score']}**",
        f"- Audits completed: **{ceo['audits_completed']}** (pilot daily cap)",
        f"- Outreach drafts: **{ceo['outreach_drafts']}**",
        f"- Approvals queued (not sent): **{ceo['approvals_queued']}**",
        f"- Estimated opportunity value (conservative EUR sum): **{ceo['estimated_opportunity_value_eur']['sum_conservative']}**",
        f"  - Note: {ceo['estimated_opportunity_value_eur']['note']}",
        f"- Actual ledger costs (EUR): **{ceo['actual_costs_eur']}**",
        "",
        "## Major problems discovered",
        "",
    ]
    for item in ceo["major_problems_discovered"]:
        lines.append(f"- {item}")
    lines += ["", "## Common opportunities", ""]
    for item in ceo["common_opportunities"]:
        lines.append(f"- {item}")
    c = analysis["contactability"]
    lines += [
        "",
        "## Contactability (verified only)",
        "",
        f"- Public email on fetched page: **{c['verified_with_public_email']}/17**",
        f"- Public phone on fetched page: **{c['verified_with_public_phone']}/17**",
        f"- Booking signal (Termin/Doctolib/etc.): **{c['verified_with_booking_signal']}/17**",
        f"- Contact-form signal: **{c['verified_with_contact_form_signal']}/17**",
        "",
        "## Expected vs actual costs",
        "",
        "### Expected",
        "",
    ]
    for key, value in ceo["expected_costs"].items():
        lines.append(f"- {key}: {value}")
    lines += ["", f"### Actual: {ceo['actual_costs_eur']} EUR", "", "## Risks", ""]
    for risk in ceo["risks"]:
        lines.append(f"- {risk}")
    lines += ["", "## Recommendations", ""]
    for rec in ceo["recommendations"]:
        lines.append(f"- {rec}")
    lines += [
        "",
        "## Experiment analysis",
        "",
        f"**Strongest niche signal (single niche tested):** {analysis['strongest_niche_signal']}",
        "",
        "**Most common problems:**",
        "",
    ]
    for item in analysis["most_common_problems"]:
        lines.append(f"- {item}")
    lines += [
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
        "| Company | Verified | Score | Fit | Audited | Draft | Approval | Email |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in companies:
        email = row.get("public_email") or "—"
        score = row["score"] if row["score"] is not None else "-"
        lines.append(
            f"| {row['name']} | {row['verified']} | {score} | {row['good_fit']} | "
            f"{row['audited']} | {bool(row.get('outreach_id'))} | "
            f"{bool(row.get('approval_id'))} | {email} |"
        )
    lines += [
        "",
        "## Outreach drafts (subjects only — bodies stored as DRAFT / PENDING_APPROVAL)",
        "",
    ]
    for row in companies:
        if row.get("outreach_subject"):
            lines.append(
                f"- **{row['name']}:** {row['outreach_subject']} "
                f"(approval_id={row.get('approval_id')})"
            )
    lines += [
        "",
        "---",
        "",
        "**STOP.** Phase 23 experiment complete. Pilot limits unchanged. No emails sent.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("updated", REPORT_MD)


if __name__ == "__main__":
    main()
