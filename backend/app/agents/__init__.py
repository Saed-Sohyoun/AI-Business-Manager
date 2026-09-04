"""AI agent plugins — lazy exports to avoid circular imports with ToolGateway."""

from __future__ import annotations

from typing import Any

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

_LAZY: dict[str, tuple[str, str]] = {
    "AuditAgent": ("app.agents.audit", "AuditAgent"),
    "AuditRequest": ("app.agents.audit", "AuditRequest"),
    "AuditRunResult": ("app.agents.audit", "AuditRunResult"),
    "DeliveryAgent": ("app.agents.delivery", "DeliveryAgent"),
    "DeliveryRequest": ("app.agents.delivery", "DeliveryRequest"),
    "DeliveryRunResult": ("app.agents.delivery", "DeliveryRunResult"),
    "FinanceAgent": ("app.agents.finance", "FinanceAgent"),
    "FinanceCalculateRequest": ("app.agents.finance", "FinanceCalculateRequest"),
    "FinanceRunResult": ("app.agents.finance", "FinanceRunResult"),
    "ManagerAgent": ("app.agents.manager", "ManagerAgent"),
    "ManagerRequest": ("app.agents.manager", "ManagerRequest"),
    "ManagerRunResult": ("app.agents.manager", "ManagerRunResult"),
    "ReportAgent": ("app.agents.report", "ReportAgent"),
    "ReportRequest": ("app.agents.report", "ReportRequest"),
    "ReportRunResult": ("app.agents.report", "ReportRunResult"),
    "ResearchAgent": ("app.agents.research", "ResearchAgent"),
    "ResearchRequest": ("app.agents.research", "ResearchRequest"),
    "ResearchRunResult": ("app.agents.research", "ResearchRunResult"),
    "SalesAgent": ("app.agents.sales", "SalesAgent"),
    "SalesRequest": ("app.agents.sales", "SalesRequest"),
    "SalesRunResult": ("app.agents.sales", "SalesRunResult"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr = target
    import importlib

    module = importlib.import_module(module_path)
    value = getattr(module, attr)
    globals()[name] = value
    return value
