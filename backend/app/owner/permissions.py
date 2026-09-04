"""Owner permissions — separate from agent contracts. Unknown = deny."""

from __future__ import annotations

OWNER_PERMISSIONS: frozenset[str] = frozenset(
    {
        "owner.read_dashboard",
        "owner.read_approvals",
        "owner.resolve_approvals",
        "owner.pause_ai",
        "owner.pause_outbound",
        "owner.pause_spending",
        "owner.pause_browser",
        "owner.resume_operations",
        "owner.read_security_events",
        "owner.manage_pilot_controls",
        "owner.read_alerts",
        "owner.read_work",
        "owner.read_system_status",
        "owner.manage_safe_mode",
        "owner.pause_all",
        "owner.launch_commands",
        "owner.read_executions",
        "owner.cancel_executions",
        "owner.read_opportunities",
        "owner.read_customers",
        "owner.read_reports",
        "owner.generate_reports",
        "owner.read_readiness",
        "owner.manage_pilot_experiment",
    }
)

# Interim: authenticated owner with API key receives the full owner permission set.
# Later: map roles → subsets.
DEFAULT_OWNER_PERMISSIONS: frozenset[str] = OWNER_PERMISSIONS


def has_owner_permission(granted: frozenset[str] | set[str], permission: str) -> bool:
    if permission not in OWNER_PERMISSIONS:
        return False
    return permission in granted
