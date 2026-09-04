"""Safe Mode — machine-triggerable safety posture; owner-clear only."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.security_event import SecurityEvent
from app.owner.controls import SystemControlService
from app.security.events import (
    AGENT_SCOPE_VIOLATION,
    POLICY_DENIED,
    WEBHOOK_REPLAY_REJECTED,
    WEBHOOK_SIGNATURE_INVALID,
)


@dataclass(frozen=True, slots=True)
class SafeModeThresholds:
    scope_violations: int = 5
    webhook_attacks: int = 5
    policy_denials: int = 20
    window_hours: int = 24


class SafeModeService:
    def __init__(
        self,
        session: Session,
        *,
        thresholds: SafeModeThresholds | None = None,
    ) -> None:
        self._session = session
        self._thresholds = thresholds or SafeModeThresholds()
        self._controls = SystemControlService(session)

    def evaluate_and_maybe_enter(self) -> bool:
        """Check recent security events; enter SAFE_MODE if thresholds exceeded."""
        from datetime import timedelta

        from app.models.base import utc_now

        since = utc_now() - timedelta(hours=self._thresholds.window_hours)
        scope = self._count(AGENT_SCOPE_VIOLATION, since)
        webhook = self._count(WEBHOOK_SIGNATURE_INVALID, since) + self._count(
            WEBHOOK_REPLAY_REJECTED, since
        )
        policy = self._count(POLICY_DENIED, since)

        reasons: list[str] = []
        if scope >= self._thresholds.scope_violations:
            reasons.append(f"scope_violations={scope}")
        if webhook >= self._thresholds.webhook_attacks:
            reasons.append(f"webhook_attacks={webhook}")
        if policy >= self._thresholds.policy_denials:
            reasons.append(f"policy_denials={policy}")
        if not reasons:
            return False
        self._controls.enter_safe_mode(
            reason="; ".join(reasons),
            actor="system:safe_mode",
        )
        return True

    def _count(self, event_type: str, since) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(
                    SecurityEvent.event_type == event_type,
                    SecurityEvent.created_at >= since,
                )
            )
            or 0
        )
