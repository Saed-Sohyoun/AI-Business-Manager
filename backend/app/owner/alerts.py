"""Owner alerts — deduplicated operational notifications."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.owner_alert import OwnerAlert
from app.models.system_mode import AlertPriority
from app.owner.schemas import OwnerAlertListView, OwnerAlertView


class OwnerAlertService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_alerts(self, *, limit: int = 50, include_acknowledged: bool = False) -> OwnerAlertListView:
        capped = max(1, min(limit, 200))
        stmt = select(OwnerAlert).order_by(OwnerAlert.created_at.desc()).limit(capped)
        if not include_acknowledged:
            stmt = (
                select(OwnerAlert)
                .where(OwnerAlert.acknowledged.is_(False))
                .order_by(OwnerAlert.created_at.desc())
                .limit(capped)
            )
        rows = self._session.scalars(stmt).all()
        return OwnerAlertListView(
            items=[
                OwnerAlertView(
                    id=r.id,
                    priority=r.priority,
                    title=r.title,
                    body=r.body,
                    source=r.source,
                    acknowledged=r.acknowledged,
                    created_at=r.created_at,
                    details=_safe_details(r.details or {}),
                )
                for r in rows
            ]
        )

    def upsert_alert(
        self,
        *,
        dedupe_key: str,
        title: str,
        body: str,
        priority: AlertPriority | str = AlertPriority.INFO,
        source: str = "system",
        details: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> OwnerAlert:
        """Create or refresh an alert by dedupe_key to avoid spam."""
        key = dedupe_key[:191]
        existing = self._session.scalar(select(OwnerAlert).where(OwnerAlert.dedupe_key == key))
        pri = priority.value if isinstance(priority, AlertPriority) else str(priority)
        if existing is not None:
            existing.title = title[:255]
            existing.body = body
            existing.priority = pri
            existing.source = source
            existing.details = _safe_details(details or {})
            existing.acknowledged = False
            existing.acknowledged_at = None
            existing.acknowledged_by = None
            existing.updated_at = utc_now()
            self._session.flush()
            if commit:
                self._session.commit()
            return existing
        row = OwnerAlert(
            dedupe_key=key,
            title=title[:255],
            body=body,
            priority=pri,
            source=source,
            details=_safe_details(details or {}),
        )
        self._session.add(row)
        self._session.flush()
        if commit:
            self._session.commit()
        return row


def _safe_details(details: dict[str, Any]) -> dict[str, Any]:
    blocked = {"api_key", "password", "secret", "authorization", "token", "body_html", "raw_payload"}
    return {k: v for k, v in details.items() if k.lower() not in blocked}
