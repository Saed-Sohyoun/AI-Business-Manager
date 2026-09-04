"""Structured schemas for Sales Agent outreach drafts.

Every personalization claim must cite evidence_ids from the catalog.
Never fabricate observations, website facts, or customer details.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SalesEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=64)
    detail: str = Field(min_length=1, max_length=1000)
    url: str | None = None
    source: str = Field(min_length=1, max_length=64)


class PersonalizationReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def require_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if not cleaned:
            raise ValueError("every personalization reason must cite evidence_ids")
        return cleaned


class OutreachDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=8000)
    cta: str = Field(min_length=1, max_length=500)
    personalization_reasons: list[PersonalizationReason] = Field(min_length=1)
    evidence_used: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class SalesAIEnrichment(BaseModel):
    """Optional AI rewrite — must only use provided evidence and reasons."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=8000)
    cta: str = Field(min_length=1, max_length=500)
    personalization_reasons: list[PersonalizationReason] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)


class SalesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    lead_id: UUID
    company_score_id: UUID | None = None
    company_audit_id: UUID | None = None
    use_ai: bool | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutreachResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outreach_id: UUID
    status: Literal["draft", "failed"]
    subject: str
    message: str
    cta: str
    personalization_reasons: list[PersonalizationReason]
    evidence_used: list[SalesEvidenceItem]
    confidence: float
    recipient_email: str | None = None


class SalesRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    status: Literal["succeeded", "failed", "partial"]
    outreach: OutreachResult | None = None
    estimated_cost: Decimal = Decimal("0")
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
    send_attempted: bool = False
