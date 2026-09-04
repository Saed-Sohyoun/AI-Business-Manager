"""System control service — persistent owner switches + enforcement."""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import ForbiddenError
from app.models.base import utc_now
from app.models.system_control import SYSTEM_CONTROL_KEY, SystemControlState
from app.models.system_mode import SystemMode
from app.security.events import (
    OWNER_PAUSED_AI,
    OWNER_PAUSED_ALL,
    OWNER_PAUSED_BROWSER,
    OWNER_PAUSED_OUTBOUND,
    OWNER_PAUSED_SPENDING,
    OWNER_RESUMED_AI,
    OWNER_RESUMED_BROWSER,
    OWNER_RESUMED_OUTBOUND,
    OWNER_RESUMED_SPENDING,
    SAFE_MODE_CLEARED,
    SAFE_MODE_ENTERED,
    SYSTEM_CONTROL_DENIED,
    record_security_event,
)

logger = logging.getLogger(__name__)

ControlName = Literal[
    "ai_operations",
    "outbound",
    "spending",
    "browser_automation",
]


class SystemControlService:
    """Load/mutate singleton control state; enforce on governed paths."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(self) -> SystemControlState:
        row = self._session.scalar(
            select(SystemControlState).where(
                SystemControlState.control_key == SYSTEM_CONTROL_KEY
            )
        )
        if row is not None:
            return row
        from sqlalchemy.exc import IntegrityError

        try:
            with self._session.begin_nested():
                row = SystemControlState(control_key=SYSTEM_CONTROL_KEY)
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            row = self._session.scalar(
                select(SystemControlState).where(
                    SystemControlState.control_key == SYSTEM_CONTROL_KEY
                )
            )
            if row is None:
                raise
            return row
        return row

    def snapshot(self) -> SystemControlState:
        return self.get_or_create()

    # --- enforcement ---------------------------------------------------------

    def assert_ai_operations(self, *, actor: str = "system") -> None:
        state = self.get_or_create()
        if state.system_mode == SystemMode.PAUSED_BY_OWNER.value:
            self._deny("ai_operations", "system_paused_by_owner", actor=actor)
        if not state.ai_operations_enabled:
            self._deny("ai_operations", "ai_operations_disabled", actor=actor)

    def assert_outbound(self, *, actor: str = "system") -> None:
        self.assert_ai_operations(actor=actor)
        state = self.get_or_create()
        if state.system_mode == SystemMode.SAFE_MODE.value or not state.outbound_enabled:
            self._deny("outbound", "outbound_disabled_or_safe_mode", actor=actor)

    def assert_spending(self, *, actor: str = "system") -> None:
        self.assert_ai_operations(actor=actor)
        state = self.get_or_create()
        if state.system_mode == SystemMode.SAFE_MODE.value or not state.spending_enabled:
            self._deny("spending", "spending_disabled_or_safe_mode", actor=actor)

    def assert_browser(self, *, actor: str = "system") -> None:
        self.assert_ai_operations(actor=actor)
        state = self.get_or_create()
        if not state.browser_automation_enabled:
            self._deny("browser_automation", "browser_automation_disabled", actor=actor)

    def _deny(self, control: str, reason: str, *, actor: str) -> None:
        record_security_event(
            self._session,
            event_type=SYSTEM_CONTROL_DENIED,
            agent_id=actor if actor != "system" else None,
            action=control,
            reason=reason,
        )
        raise ForbiddenError(
            "This operation is currently disabled by system controls.",
            details={"control": control, "reason": reason},
        )

    # --- owner mutations -----------------------------------------------------

    def pause_all(self, *, actor: str, reason: str | None = None) -> SystemControlState:
        state = self.get_or_create()
        state.system_mode = SystemMode.PAUSED_BY_OWNER.value
        state.ai_operations_enabled = False
        state.outbound_enabled = False
        state.spending_enabled = False
        state.browser_automation_enabled = False
        state.paused_by = actor
        state.paused_at = utc_now()
        state.pause_reason = reason or "Owner paused all operations"
        state.last_changed_by = actor
        state.last_changed_at = utc_now()
        self._session.flush()
        record_security_event(
            self._session,
            event_type=OWNER_PAUSED_ALL,
            reason=reason or "pause_all",
            details={"actor": actor},
        )
        self._session.commit()
        return state

    def set_control(
        self,
        control: ControlName,
        *,
        enabled: bool,
        actor: str,
        reason: str | None = None,
    ) -> SystemControlState:
        identity = (actor or "").strip().lower()
        if identity in {
            "manager",
            "research",
            "sales",
            "finance",
            "audit",
            "delivery",
            "report",
            "scoring",
            "system",
            "agent",
        } or identity.startswith("agent:"):
            record_security_event(
                self._session,
                event_type=SYSTEM_CONTROL_DENIED,
                agent_id=actor,
                action=f"set_control:{control}",
                reason="agent_cannot_change_owner_controls",
            )
            raise ForbiddenError(
                "Agents cannot change owner system controls",
                details={"actor": actor, "control": control},
            )
        state = self.get_or_create()
        if state.system_mode == SystemMode.PAUSED_BY_OWNER.value and enabled:
            # Resuming a single control while paused-by-owner requires leaving pause mode
            # via resume_ai / clear path — do not silently exit PAUSED_BY_OWNER here
            # except when enabling ai_operations explicitly via resume helpers.
            pass

        event_map_on = {
            "ai_operations": OWNER_RESUMED_AI,
            "outbound": OWNER_RESUMED_OUTBOUND,
            "spending": OWNER_RESUMED_SPENDING,
            "browser_automation": OWNER_RESUMED_BROWSER,
        }
        event_map_off = {
            "ai_operations": OWNER_PAUSED_AI,
            "outbound": OWNER_PAUSED_OUTBOUND,
            "spending": OWNER_PAUSED_SPENDING,
            "browser_automation": OWNER_PAUSED_BROWSER,
        }
        attr = {
            "ai_operations": "ai_operations_enabled",
            "outbound": "outbound_enabled",
            "spending": "spending_enabled",
            "browser_automation": "browser_automation_enabled",
        }[control]
        setattr(state, attr, enabled)
        if control == "ai_operations" and enabled:
            if state.system_mode == SystemMode.PAUSED_BY_OWNER.value:
                state.system_mode = SystemMode.NORMAL.value
                state.paused_by = None
                state.paused_at = None
                state.pause_reason = None
        if control == "ai_operations" and not enabled:
            # Pausing AI alone does not force PAUSED_BY_OWNER (use pause-all for that)
            pass
        state.last_changed_by = actor
        state.last_changed_at = utc_now()
        self._session.flush()
        record_security_event(
            self._session,
            event_type=event_map_on[control] if enabled else event_map_off[control],
            reason=reason or ("enabled" if enabled else "disabled"),
            details={"actor": actor, "control": control, "enabled": enabled},
        )
        self._session.commit()
        return state

    def enter_safe_mode(self, *, reason: str, actor: str = "system") -> SystemControlState:
        state = self.get_or_create()
        if state.system_mode == SystemMode.PAUSED_BY_OWNER.value:
            # Owner pause is higher authority — keep paused, still tighten switches
            pass
        else:
            state.system_mode = SystemMode.SAFE_MODE.value
        state.outbound_enabled = False
        state.spending_enabled = False
        state.safe_mode_reason = reason
        state.safe_mode_entered_at = utc_now()
        state.last_changed_by = actor
        state.last_changed_at = utc_now()
        self._session.flush()
        record_security_event(
            self._session,
            event_type=SAFE_MODE_ENTERED,
            reason=reason,
            details={"actor": actor},
        )
        try:
            from app.models.system_mode import AlertPriority
            from app.owner.alerts import OwnerAlertService

            OwnerAlertService(self._session).upsert_alert(
                dedupe_key="system:safe_mode",
                title="Safe Mode activated",
                body=reason,
                priority=AlertPriority.CRITICAL,
                source="system",
                details={"actor": actor},
                commit=False,
            )
        except Exception:  # noqa: BLE001
            logger.debug("safe_mode_alert_skipped", exc_info=True)
        self._session.commit()
        return state

    def clear_safe_mode(self, *, actor: str, reason: str | None = None) -> SystemControlState:
        """Owner-only. Agents must never call this."""
        identity = (actor or "").strip().lower()
        if identity in {
            "manager",
            "research",
            "sales",
            "finance",
            "audit",
            "delivery",
            "report",
            "scoring",
            "system",
            "agent",
        } or identity.startswith("agent:"):
            record_security_event(
                self._session,
                event_type=SYSTEM_CONTROL_DENIED,
                agent_id=actor,
                action="clear_safe_mode",
                reason="agent_cannot_clear_safe_mode",
            )
            raise ForbiddenError(
                "Only the owner may clear SAFE_MODE",
                details={"actor": actor},
            )
        state = self.get_or_create()
        if state.system_mode == SystemMode.PAUSED_BY_OWNER.value:
            raise ForbiddenError(
                "System is paused by owner — clear pause before clearing safe mode",
                details={"system_mode": state.system_mode},
            )
        state.system_mode = SystemMode.NORMAL.value
        state.safe_mode_reason = None
        state.safe_mode_entered_at = None
        # Restore outbound/spending unless owner had them off independently — default restore
        state.outbound_enabled = True
        state.spending_enabled = True
        state.last_changed_by = actor
        state.last_changed_at = utc_now()
        self._session.flush()
        record_security_event(
            self._session,
            event_type=SAFE_MODE_CLEARED,
            reason=reason or "owner_cleared_safe_mode",
            details={"actor": actor},
        )
        self._session.commit()
        return state

    def as_dict(self) -> dict[str, Any]:
        s = self.get_or_create()
        return {
            "system_mode": s.system_mode,
            "ai_operations_enabled": s.ai_operations_enabled,
            "outbound_enabled": s.outbound_enabled,
            "spending_enabled": s.spending_enabled,
            "browser_automation_enabled": s.browser_automation_enabled,
            "safe_mode_reason": s.safe_mode_reason,
            "paused_by": s.paused_by,
            "pause_reason": s.pause_reason,
        }
