"""Owner-facing Pydantic schemas — no ORM leakage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OwnerAPIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DecisionNoteBody(OwnerAPIModel):
    note: str | None = Field(default=None, max_length=4000)


class ControlChangeBody(OwnerAPIModel):
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalAdvancedDetails(OwnerAPIModel):
    requesting_agent: str | None = None
    action_id: str | None = None
    execution_id: str | None = None
    policy_level: str | None = None
    fingerprint: str | None = None
    contract_version: str | None = None
    manager_run_id: str | None = None
    manager_task_id: str | None = None
    agent_run_id: str | None = None


class ApprovalDecisionView(OwnerAPIModel):
    id: UUID
    title: str
    summary: str
    why: str
    affected_party: str | None = None
    expected_benefit: str | None = None
    estimated_cost: str | None = None
    risk: str
    reversibility: str
    expires_at: datetime | None = None
    status: str
    recommended_action: str
    advanced_details: ApprovalAdvancedDetails
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class SystemStatusView(OwnerAPIModel):
    system_mode: str
    ai_operations: bool
    outbound: bool
    spending: bool
    browser_automation: bool
    pilot_mode: bool
    production_locked: bool
    active_runs: int
    pending_approvals: int
    recent_failures: int
    security_alerts: int
    current_budget_usage: str
    budget_limit: str
    currency: str = "EUR"
    last_successful_run: datetime | None = None
    safe_mode_reason: str | None = None
    pause_reason: str | None = None
    provider_health: list[dict[str, Any]] = Field(default_factory=list)
    health_summary: str = "System operational"


class DashboardGoal(OwnerAPIModel):
    title: str
    progress: float = 0
    target: float = 0
    unit: str = ""


class DashboardMoney(OwnerAPIModel):
    revenue: str
    costs: str
    profit: str
    currency: str = "EUR"


class DashboardPipeline(OwnerAPIModel):
    companies: int = 0
    qualified_leads: int = 0
    opportunities: int = 0
    customers: int = 0


class DashboardAttention(OwnerAPIModel):
    pending_approvals: int = 0
    urgent_alerts: int = 0
    blocked_work: int = 0


class DashboardTeamActivity(OwnerAPIModel):
    researching: int = 0
    auditing: int = 0
    drafting: int = 0
    delivering: int = 0
    waiting: int = 0


class DashboardActivityEntry(OwnerAPIModel):
    title: str
    at: datetime | None = None
    kind: str = "activity"


class DashboardSummaryView(OwnerAPIModel):
    current_goal: DashboardGoal
    money: DashboardMoney
    pipeline: DashboardPipeline
    attention: DashboardAttention
    team_activity: DashboardTeamActivity
    recent_activity: list[DashboardActivityEntry] = Field(default_factory=list)


class ActiveWorkAdvanced(OwnerAPIModel):
    agent_run_id: str | None = None
    manager_task_id: str | None = None
    manager_run_id: str | None = None
    agent_name: str | None = None


class ActiveWorkItem(OwnerAPIModel):
    title: str
    status: str
    progress: int = 0
    total: int = 0
    needs_attention: bool = False
    business_purpose: str | None = None
    started_at: datetime | None = None
    duration_seconds: int | None = None
    advanced_details: ActiveWorkAdvanced = Field(default_factory=ActiveWorkAdvanced)


class ActiveWorkListView(OwnerAPIModel):
    items: list[ActiveWorkItem] = Field(default_factory=list)


class OwnerAlertView(OwnerAPIModel):
    id: UUID
    priority: str
    title: str
    body: str
    source: str
    acknowledged: bool
    created_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class OwnerAlertListView(OwnerAPIModel):
    items: list[OwnerAlertView] = Field(default_factory=list)


class SecurityEventAdvanced(OwnerAPIModel):
    event_type: str
    agent: str | None = None
    execution_id: str | None = None
    timestamp: datetime
    reason: str | None = None
    policy_version: str | None = None
    action: str | None = None
    tool: str | None = None


class SecurityEventSummary(OwnerAPIModel):
    id: UUID
    title: str
    summary: str
    severity: Literal["info", "important", "urgent", "critical"] = "important"
    created_at: datetime
    advanced_details: SecurityEventAdvanced


class SecurityEventListView(OwnerAPIModel):
    items: list[SecurityEventSummary] = Field(default_factory=list)


class ControlStateView(OwnerAPIModel):
    system_mode: str
    ai_operations_enabled: bool
    outbound_enabled: bool
    spending_enabled: bool
    browser_automation_enabled: bool
    safe_mode_reason: str | None = None
    pause_reason: str | None = None
    last_changed_by: str | None = None
    last_changed_at: datetime | None = None
