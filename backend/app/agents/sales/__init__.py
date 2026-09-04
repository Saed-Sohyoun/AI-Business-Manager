"""Sales Agent — personalized outreach drafts (no sending)."""

from app.agents.sales.agent import AGENT_NAME, TASK_TYPE, SalesAgent
from app.agents.sales.composer import OUTREACH_VERSION
from app.agents.sales.schemas import (
    OutreachDraft,
    OutreachResult,
    PersonalizationReason,
    SalesAIEnrichment,
    SalesEvidenceItem,
    SalesRequest,
    SalesRunResult,
)

__all__ = [
    "AGENT_NAME",
    "OUTREACH_VERSION",
    "OutreachDraft",
    "OutreachResult",
    "PersonalizationReason",
    "SalesAIEnrichment",
    "SalesAgent",
    "SalesEvidenceItem",
    "SalesRequest",
    "SalesRunResult",
    "TASK_TYPE",
]
