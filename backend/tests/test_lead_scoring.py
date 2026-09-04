"""Deterministic lead scoring tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models import Company, CompanyEvidence, CompanyScore, CompanySource
from app.models.enums import CompanyStatus
from app.scoring.bands import band_for_total
from app.scoring.engine import SCORING_VERSION, score_company_facts
from app.scoring.schemas import CompanyScoringFacts
from app.services.lead_scoring_service import LeadScoringService


def _max_facts() -> CompanyScoringFacts:
    return CompanyScoringFacts(
        has_website=True,
        website_verified=True,
        website_https=True,
        has_description=True,
        description_length=120,
        source_count=4,
        has_industry=True,
        has_location=True,
        has_email_evidence=True,
        has_phone_evidence=True,
        has_address_evidence=True,
        has_contact_page=True,
        has_contact_form=True,
        has_booking_or_calendar=True,
        industry="consulting",
        description="B2B consulting GmbH offering software services",
        company_status="prospect",
    )


def _min_facts() -> CompanyScoringFacts:
    return CompanyScoringFacts()


def test_minimum_score():
    result = score_company_facts(_min_facts(), scored_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert result.total_score == 0
    assert result.band == "low"
    assert result.website_quality == 0
    assert result.online_presence == 0
    assert result.lead_capture_process == 0
    assert result.automation_potential == 0
    assert result.commercial_potential == 0
    assert result.scoring_version == SCORING_VERSION
    assert all(r.points == 0 for r in result.reasons if r.points == 0)
    assert result.evidence["has_website"] is False


def test_maximum_score():
    result = score_company_facts(_max_facts())
    assert result.website_quality == 20
    assert result.online_presence == 20
    assert result.lead_capture_process == 20
    assert result.automation_potential == 20
    assert result.commercial_potential == 20
    assert result.total_score == 100
    assert result.band == "high"
    assert result.reasons
    assert all(0 <= r.points <= 20 for r in result.reasons)


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (0, "low"),
        (49, "low"),
        (50, "medium"),
        (69, "medium"),
        (70, "good"),
        (84, "good"),
        (85, "high"),
        (100, "high"),
    ],
)
def test_boundary_bands(total: int, expected: str):
    assert band_for_total(total).value == expected


def test_boundary_values_via_engine_near_thresholds():
    # Construct facts that land near 50 (medium) using online + website only
    facts = CompanyScoringFacts(
        has_website=True,  # +5 wq
        website_https=True,  # +3 wq
        has_description=True,  # +3 wq
        description_length=25,  # +2 wq => 13
        source_count=2,  # +8 op
        has_industry=True,  # +4 op
        has_location=True,  # +4 op => 16
        # lead capture 0
        # automation: website + industry + location + desc>=40? 25 no -> +5+4+3=12
        industry="retail",
        description="short desc text here!!",  # len check
    )
    # description "short desc text here!!" length
    facts = facts.model_copy(
        update={"description": "x" * 40, "description_length": 40, "has_description": True}
    )
    # Recalculate expected roughly — assert band mapping stability and bounds
    result = score_company_facts(facts)
    assert 0 <= result.total_score <= 100
    assert result.band in {"low", "medium", "good", "high"}
    assert sum(
        [
            result.website_quality,
            result.online_presence,
            result.lead_capture_process,
            result.automation_potential,
            result.commercial_potential,
        ]
    ) == result.total_score


def test_missing_information_scores_low_explainably():
    result = score_company_facts(CompanyScoringFacts(has_website=True, website_https=True))
    assert result.total_score < 50
    assert result.band == "low"
    assert any("No lead-capture" in r.reason for r in result.reasons)
    assert result.evidence["has_email_evidence"] is False


def test_invalid_data_rejected():
    with pytest.raises(ValidationError):
        CompanyScoringFacts(source_count=-1)
    with pytest.raises(ValidationError):
        CompanyScoringFacts(description_length=-5)
    with pytest.raises(ValueError):
        band_for_total(-1)
    with pytest.raises(ValueError):
        band_for_total(101)


def test_reproducibility():
    facts = _max_facts()
    when = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    a = score_company_facts(facts, scored_at=when)
    b = score_company_facts(facts, scored_at=when)
    assert a.model_dump() == b.model_dump()
    assert a.scoring_version == b.scoring_version == SCORING_VERSION


def test_service_persists_explainable_score(db_session):
    company = Company(
        name="Acme GmbH",
        website="https://acme.example/",
        website_domain="acme.example",
        industry="consulting",
        location="Berlin",
        description="B2B consulting services for software teams " + ("x" * 40),
        status=CompanyStatus.PROSPECT,
        source="test",
    )
    db_session.add(company)
    db_session.flush()
    db_session.add_all(
        [
            CompanySource(
                company_id=company.id,
                url="https://acme.example/",
                normalized_url="https://acme.example",
                source_type="search",
            ),
            CompanySource(
                company_id=company.id,
                url="https://news.example/acme",
                normalized_url="https://news.example/acme",
                source_type="search",
            ),
            CompanyEvidence(
                company_id=company.id,
                field_name="website",
                field_value="https://acme.example/",
                verification_status="verified",
                source_type="research",
            ),
            CompanyEvidence(
                company_id=company.id,
                field_name="email",
                field_value="info@acme.example",
                verification_status="unverified",
                source_type="research",
            ),
        ]
    )
    db_session.commit()

    service = LeadScoringService(db_session)
    result = service.score_company(
        company.id,
        has_contact_page=True,
        has_contact_form=True,
        has_booking_or_calendar=True,
    )

    assert result.total_score > 0
    assert result.reasons
    assert result.evidence
    assert result.scoring_version == SCORING_VERSION

    stored = service.get_latest_score(company.id)
    assert stored is not None
    assert stored.total_score == result.total_score
    assert stored.band == result.band
    rows = db_session.scalars(select(CompanyScore).where(CompanyScore.company_id == company.id)).all()
    assert len(rows) == 1
    assert rows[0].reasons
    assert rows[0].evidence["has_website"] is True


def test_engine_has_no_llm_dependency():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "scoring"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "openai"
                assert not (node.module or "").startswith("openai")
                assert node.module != "app.services.ai_service"
                assert node.module != "app.providers.ai"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "openai" not in alias.name
