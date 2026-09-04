"""n8n orchestration layer — thin triggers into backend business logic.

n8n schedules and calls authenticated webhooks. Critical logic, approvals,
and source-of-truth state remain in the backend.
"""

from app.orchestration.schemas import (
    WorkflowExecutionView,
    WorkflowTriggerRequest,
    WorkflowTriggerResponse,
)
from app.orchestration.service import N8nOrchestrationService

__all__ = [
    "N8nOrchestrationService",
    "WorkflowExecutionView",
    "WorkflowTriggerRequest",
    "WorkflowTriggerResponse",
]
