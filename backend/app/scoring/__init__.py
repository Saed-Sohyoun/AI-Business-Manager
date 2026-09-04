"""Lead scoring package — deterministic, explainable company scoring."""

from app.scoring.bands import band_for_total
from app.scoring.engine import SCORING_VERSION, score_company_facts
from app.scoring.facts import build_scoring_facts
from app.scoring.schemas import CompanyScoringFacts, LeadScoreResult

__all__ = [
    "SCORING_VERSION",
    "CompanyScoringFacts",
    "LeadScoreResult",
    "band_for_total",
    "build_scoring_facts",
    "score_company_facts",
]
