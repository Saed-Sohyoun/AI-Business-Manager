"""Structured schemas for Research Agent I/O.

The agent must never invent companies, websites, emails, phones, addresses,
or other facts. Missing values use status=unknown with value=None.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


VerificationStatus = Literal["verified", "unverified", "unknown"]


class ResearchField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    status: VerificationStatus = "unknown"
    source_url: str | None = None


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    industry: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    max_companies: int | None = Field(default=None, ge=1, le=100)
    verify_with_browser: bool | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict = Field(default_factory=dict)


class ResearchCandidate(BaseModel):
    """Intermediate candidate extracted only from provider evidence."""

    model_config = ConfigDict(extra="forbid")

    name: ResearchField
    website: ResearchField
    website_domain: str | None = None
    industry: ResearchField = Field(default_factory=ResearchField)
    location: ResearchField = Field(default_factory=ResearchField)
    description: ResearchField = Field(default_factory=ResearchField)
    # Explicitly never invented in Phase 5 — always unknown unless future verified extraction
    email: ResearchField = Field(default_factory=lambda: ResearchField(status="unknown"))
    phone: ResearchField = Field(default_factory=lambda: ResearchField(status="unknown"))
    address: ResearchField = Field(default_factory=lambda: ResearchField(status="unknown"))
    source_urls: list[str] = Field(default_factory=list)
    skipped_reason: str | None = None


class StoredCompanySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    name: str
    website: str | None
    website_domain: str | None
    created: bool
    duplicate: bool = False


class ResearchRunResult(BaseModel):
    """Canonical research output (contract name: ResearchResult)."""

    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    status: Literal["succeeded", "failed", "partial", "escalated"]
    query: str
    companies_created: int = 0
    companies_duplicate: int = 0
    candidates_seen: int = 0
    candidates_skipped: int = 0
    stored: list[StoredCompanySummary] = Field(default_factory=list)
    estimated_cost: Decimal = Decimal("0")
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
    escalation: dict | None = None


# Contract output alias — machine-readable name from AgentContract.output_schema
ResearchResult = ResearchRunResult
