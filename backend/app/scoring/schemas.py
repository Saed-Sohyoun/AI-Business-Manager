"""Lead scoring schemas — facts in, explainable score out.

Final scores are produced by validated deterministic rules, never by an LLM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ScoreBandLiteral = Literal["low", "medium", "good", "high"]
CategoryName = Literal[
    "website_quality",
    "online_presence",
    "lead_capture_process",
    "automation_potential",
    "commercial_potential",
]


class CompanyScoringFacts(BaseModel):
    """Observed facts used for scoring. Missing data must be explicit False/None/0."""

    model_config = ConfigDict(extra="forbid")

    has_website: bool = False
    website_verified: bool = False
    website_https: bool = False
    has_description: bool = False
    description_length: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    has_industry: bool = False
    has_location: bool = False
    has_email_evidence: bool = False
    has_phone_evidence: bool = False
    has_address_evidence: bool = False
    # Optional structured signals (e.g. from future browser audit). Default false.
    has_contact_page: bool = False
    has_contact_form: bool = False
    has_booking_or_calendar: bool = False
    industry: str | None = None
    description: str | None = None
    company_status: str | None = None

    @field_validator("description_length", "source_count")
    @classmethod
    def non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be >= 0")
        return value


class ScoreReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: CategoryName
    points: int = Field(ge=0, le=20)
    reason: str
    evidence_keys: list[str] = Field(default_factory=list)


class CategoryScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CategoryName
    score: int = Field(ge=0, le=20)
    max_score: int = 20
    reasons: list[ScoreReason] = Field(default_factory=list)


class LeadScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=100)
    band: ScoreBandLiteral
    website_quality: int = Field(ge=0, le=20)
    online_presence: int = Field(ge=0, le=20)
    lead_capture_process: int = Field(ge=0, le=20)
    automation_potential: int = Field(ge=0, le=20)
    commercial_potential: int = Field(ge=0, le=20)
    reasons: list[ScoreReason]
    evidence: dict[str, Any]
    scoring_version: str
    scored_at: datetime
    categories: list[CategoryScore]


class StoredLeadScore(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    company_id: UUID
    total_score: int
    band: ScoreBandLiteral
    website_quality: int
    online_presence: int
    lead_capture_process: int
    automation_potential: int
    commercial_potential: int
    reasons: list[dict[str, Any]]
    evidence: dict[str, Any]
    scoring_version: str
    scored_at: datetime
