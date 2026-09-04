"""Manager Agent schemas — goals, plans, tasks, run results."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ManagerStatusLiteral = Literal[
    "succeeded",
    "failed",
    "stopped",
    "awaiting_approval",
    "cancelled",
]


class PlannedTaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1, max_length=128)
    task_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=1000)


class ManagerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=2000)
    target_qualified_leads: int | None = Field(default=None, ge=1, le=500)
    target_mrr: Decimal | None = Field(default=None, ge=0)
    max_monthly_operating_cost: Decimal | None = Field(default=None, ge=0)
    full_cycle: bool | None = Field(
        default=None,
        description="When true, plan the full business funnel. Auto-detected from goal when omitted.",
    )
    industry: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    query: str | None = Field(default=None, max_length=500)
    force_tasks: list[PlannedTaskSpec] | None = Field(
        default=None,
        description="When set, use these tasks instead of the deterministic planner output.",
    )
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    companies_total: int = 0
    companies_with_website: int = 0
    scores_total: int = 0
    qualified_leads: int = 0  # good + high bands
    audits_total: int = 0
    unscored_company_ids: list[str] = Field(default_factory=list)
    unaudited_company_ids: list[str] = Field(default_factory=list)
    # Funnel / finance signals for full-cycle planning (inspected, never invented)
    qualified_unaudited_count: int = 0
    draftable_leads: list[dict[str, str]] = Field(default_factory=list)
    draftable_leads_count: int = 0
    pending_outreach_drafts: int = 0
    draft_outreach_ids: list[str] = Field(default_factory=list)
    approved_outreach_ids: list[str] = Field(default_factory=list)
    pending_approvals: int = 0
    follow_ups_due: int = 0
    customers_active: int = 0
    converted_leads_without_project: int = 0
    converted_lead_ids: list[str] = Field(default_factory=list)
    active_projects: int = 0
    mrr: Decimal = Decimal("0")
    operating_costs_mtd: Decimal = Decimal("0")
    revenue_mtd: Decimal = Decimal("0")
    profit_mtd: Decimal = Decimal("0")
    responses_recorded: int = 0


class DelegationResult(BaseModel):
    """Normalized result returned by delegated agent/service executors."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "failed", "partial", "timeout"]
    summary: str = Field(min_length=1, max_length=2000)
    estimated_cost: Decimal = Decimal("0")
    output: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    error_message: str | None = None


class TaskResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    agent_name: str
    task_type: str
    status: str
    verified: bool = False
    attempt_count: int = 0
    estimated_cost: Decimal = Decimal("0")
    summary: str | None = None
    error_message: str | None = None


class DecisionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_type: str
    phase: str
    action: str
    rationale: str


class ManagerRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manager_run_id: UUID
    agent_run_id: UUID
    status: ManagerStatusLiteral
    goal: str
    phase: str
    plan_summary: str | None = None
    stop_reason: str | None = None
    target_qualified_leads: int | None = None
    measured_qualified_leads: int = 0
    tasks_created: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    retry_count: int = 0
    estimated_cost: Decimal = Decimal("0")
    tasks: list[TaskResultSummary] = Field(default_factory=list)
    decisions: list[DecisionSummary] = Field(default_factory=list)
    business_state: dict[str, Any] = Field(default_factory=dict)
    idempotent_replay: bool = False
    error_message: str | None = None
    logs: list[str] = Field(default_factory=list)
