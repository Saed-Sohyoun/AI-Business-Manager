"""Manager Agent — central orchestration layer."""

from app.agents.manager.agent import AGENT_NAME, TASK_TYPE, ManagerAgent
from app.agents.manager.registry import AgentExecutor, RegistryExecutor
from app.agents.manager.schemas import (
    BusinessStateSnapshot,
    DecisionSummary,
    DelegationResult,
    ManagerRequest,
    ManagerRunResult,
    PlannedTaskSpec,
    TaskResultSummary,
)
from app.agents.manager.state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTaskTransition,
    can_transition,
    transition,
)

__all__ = [
    "AGENT_NAME",
    "ALLOWED_TRANSITIONS",
    "AgentExecutor",
    "BusinessStateSnapshot",
    "DecisionSummary",
    "DelegationResult",
    "InvalidTaskTransition",
    "ManagerAgent",
    "ManagerRequest",
    "ManagerRunResult",
    "PlannedTaskSpec",
    "RegistryExecutor",
    "TASK_TYPE",
    "TaskResultSummary",
    "can_transition",
    "transition",
]
