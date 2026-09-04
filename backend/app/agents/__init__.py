"""AI agent plugins."""

from app.agents.audit import AuditAgent, AuditRequest, AuditRunResult
from app.agents.delivery import DeliveryAgent, DeliveryRequest, DeliveryRunResult
from app.agents.finance import FinanceAgent, FinanceCalculateRequest, FinanceRunResult
from app.agents.manager import ManagerAgent, ManagerRequest, ManagerRunResult
from app.agents.report import ReportAgent, ReportRequest, ReportRunResult
from app.agents.research import ResearchAgent, ResearchRequest, ResearchRunResult
from app.agents.sales import SalesAgent, SalesRequest, SalesRunResult

__all__ = [
    "AuditAgent",
    "AuditRequest",
    "AuditRunResult",
    "DeliveryAgent",
    "DeliveryRequest",
    "DeliveryRunResult",
    "FinanceAgent",
    "FinanceCalculateRequest",
    "FinanceRunResult",
    "ManagerAgent",
    "ManagerRequest",
    "ManagerRunResult",
    "ReportAgent",
    "ReportRequest",
    "ReportRunResult",
    "ResearchAgent",
    "ResearchRequest",
    "ResearchRunResult",
    "SalesAgent",
    "SalesRequest",
    "SalesRunResult",
]
