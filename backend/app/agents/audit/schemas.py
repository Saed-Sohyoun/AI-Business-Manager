"""Structured schemas for Audit Agent.

Every important claim must cite an evidence_id from the observation catalog.
Never fabricate observations or URLs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


PriorityLiteral = Literal["low", "medium", "high", "critical"]
FindingType = Literal["problem", "opportunity"]


class AuditEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=64)
    url: str | None = None
    excerpt: str | None = Field(default=None, max_length=500)
    detail: str = Field(min_length=1, max_length=1000)


class AuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_type: FindingType
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=2000)
    priority: PriorityLiteral = "medium"
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    recommended_solution: str | None = Field(default=None, max_length=2000)
    estimated_business_value: Decimal | None = None
    estimated_business_value_currency: str | None = Field(default=None, max_length=8)
    estimated_business_value_rationale: str | None = Field(default=None, max_length=1000)

    @field_validator("evidence_ids")
    @classmethod
    def require_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if not cleaned:
            raise ValueError("every finding must cite at least one evidence_id")
        return cleaned


class AuditAIEnrichment(BaseModel):
    """Optional AI enrichment — must only reference provided evidence_ids."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4000)
    findings: list[AuditFinding] = Field(default_factory=list)
    recommended_solution: str | None = Field(default=None, max_length=4000)
    overall_priority: PriorityLiteral = "medium"
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)


class SiteObservations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    website_available: bool = False
    website_url: str | None = None
    final_url: str | None = None
    status_code: int | None = None
    title: str | None = None
    text_length: int = 0
    has_viewport_meta: bool = False
    has_mailto: bool = False
    has_tel: bool = False
    has_contact_link: bool = False
    has_booking_link: bool = False
    has_form_signal: bool = False
    has_cta_signal: bool = False
    link_count: int = 0
    search_result_count: int = 0
    browser_error: str | None = None
    search_error: str | None = None
    incomplete_site: bool = False


class CompanyAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    audit_version: str
    status: Literal["succeeded", "partial", "failed"]
    priority: PriorityLiteral
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    recommended_solution: str | None = None
    website_available: bool
    problems: list[AuditFinding] = Field(default_factory=list)
    opportunities: list[AuditFinding] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    evidence_catalog: list[AuditEvidenceItem] = Field(default_factory=list)
    observations: SiteObservations
    estimated_business_value: Decimal | None = None
    estimated_business_value_currency: str | None = None
    estimated_business_value_rationale: str | None = None
    ai_used: bool = False
    logs: list[str] = Field(default_factory=list)


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_ids: list[UUID] = Field(default_factory=list)
    max_audits: int | None = Field(default=None, ge=1, le=50)
    use_ai: bool | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict = Field(default_factory=dict)


class AuditRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    status: Literal["succeeded", "partial", "failed"]
    audits_completed: int = 0
    audits_failed: int = 0
    results: list[CompanyAuditResult] = Field(default_factory=list)
    estimated_cost: Decimal = Decimal("0")
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
