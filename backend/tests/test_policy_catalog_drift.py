"""Wave 1 — policy catalog / manager delegable drift detection."""

from __future__ import annotations

from app.agents.manager.permissions import _DELEGABLE, get_permission
from app.approvals.action_ids import CANONICAL_ACTIONS
from app.approvals.policy import POLICY_CATALOG, action_type_for_agent


def test_policy_catalog_subset_of_canonical():
    missing = set(POLICY_CATALOG.keys()) - CANONICAL_ACTIONS
    assert not missing, f"POLICY_CATALOG has undeclared actions: {sorted(missing)}"


def test_delegable_maps_to_policy_catalog():
    for agent, task in _DELEGABLE:
        action = action_type_for_agent(agent, task)
        assert action in POLICY_CATALOG, f"delegable {agent}.{task} → {action} missing from POLICY"
        perm = get_permission(agent, task)
        assert perm is not None
        assert perm.action_type == action


def test_canonical_actions_have_policy_entries():
    missing = CANONICAL_ACTIONS - set(POLICY_CATALOG.keys())
    assert not missing, f"Canonical actions missing from POLICY_CATALOG: {sorted(missing)}"
