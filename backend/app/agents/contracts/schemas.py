"""Agent contract schemas — explicit, machine-checked agent boundaries."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maximum_runtime_seconds: int | None = Field(default=None, ge=1)
    maximum_retries: int | None = Field(default=None, ge=0)
    maximum_tasks: int | None = Field(default=None, ge=1)
    maximum_cost: Decimal | None = None
    max_companies_per_run: int | None = Field(default=None, ge=1)
    max_audits_per_run: int | None = Field(default=None, ge=1)
    max_search_requests: int | None = Field(default=None, ge=1)
    max_browser_runtime_seconds: float | None = Field(default=None, ge=1.0)


class EscalationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: str = Field(min_length=1, max_length=128)
    action: Literal["stop_request_manager", "stop", "request_approval"] = "stop_request_manager"
    description: str = Field(min_length=1, max_length=500)


class AgentContract(BaseModel):
    """Explicit machine-readable contract for one agent.

    The LLM must never be trusted to respect this contract.
    The backend validates every requested action/tool against it.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=64)
    version: str = Field(default="1.0.0", min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1000)
    responsibility: str = Field(min_length=1, max_length=1000)

    allowed_actions: frozenset[str] = Field(min_length=1)
    forbidden_actions: frozenset[str] = Field(default_factory=frozenset)
    allowed_tools: frozenset[str] = Field(min_length=1)
    forbidden_tools: frozenset[str] = Field(default_factory=frozenset)
    allowed_entities: frozenset[str] = Field(default_factory=frozenset)
    resource_scope: frozenset[str] = Field(default_factory=frozenset)

    required_inputs: frozenset[str] = Field(default_factory=frozenset)
    expected_outputs: frozenset[str] = Field(min_length=1)
    output_schema: str = Field(min_length=1, max_length=128)

    limits: AgentLimits = Field(default_factory=AgentLimits)
    approval_requirements: frozenset[str] = Field(default_factory=frozenset)
    escalation_rules: tuple[EscalationRule, ...] = Field(default_factory=tuple)
    verification_rules: frozenset[str] = Field(default_factory=frozenset)

    user_facing_scope_message: str = Field(
        default=(
            "This work was stopped because the team attempted an action "
            "outside its responsibilities."
        ),
        min_length=1,
        max_length=500,
    )

    @field_validator(
        "allowed_actions",
        "forbidden_actions",
        "allowed_tools",
        "forbidden_tools",
        "allowed_entities",
        "resource_scope",
        "required_inputs",
        "expected_outputs",
        "approval_requirements",
        "verification_rules",
        mode="before",
    )
    @classmethod
    def _coerce_frozenset(cls, value: object) -> object:
        if isinstance(value, (list, tuple, set)):
            return frozenset(value)
        return value

    def allows_action(self, action: str) -> bool:
        normalized = action.strip().lower()
        if normalized in {a.lower() for a in self.forbidden_actions}:
            return False
        if normalized in {a.lower() for a in self.allowed_actions}:
            return True
        # Namespaced aliases: discover_companies ↔ research.discover_companies
        short = normalized.split(".", 1)[-1]
        allowed_short = {a.lower().split(".", 1)[-1] for a in self.allowed_actions}
        forbidden_short = {a.lower().split(".", 1)[-1] for a in self.forbidden_actions}
        if short in forbidden_short:
            return False
        return short in allowed_short

    def allows_tool(self, tool: str) -> bool:
        normalized = tool.strip().lower()
        if normalized in {t.lower() for t in self.forbidden_tools}:
            return False
        return normalized in {t.lower() for t in self.allowed_tools}
