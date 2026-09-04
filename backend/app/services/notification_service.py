"""NotificationService — owner alerts via NotificationProvider.

Anti-spam: priority floors, hourly rate limits, idempotent dedupe.
Never logs secrets. Never required for app boot.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import NotificationRecord
from app.models.base import utc_now
from app.models.enums import NotificationCategory, NotificationPriority, NotificationStatus
from app.providers.notification.base import NotificationProvider
from app.providers.notification.exceptions import (
    NotificationConfigurationError,
    NotificationIdempotencyError,
    NotificationRateLimitError,
    NotificationValidationError,
)
from app.providers.notification.telegram_provider import TelegramProvider
from app.providers.notification.types import NotificationSendRequest

logger = logging.getLogger(__name__)

# Priority rank for comparisons (higher = more urgent)
_PRIORITY_RANK = {
    NotificationPriority.INFO: 1,
    NotificationPriority.IMPORTANT: 2,
    NotificationPriority.URGENT: 3,
    NotificationPriority.CRITICAL: 4,
}


def _as_priority(value: NotificationPriority | str) -> NotificationPriority:
    if isinstance(value, NotificationPriority):
        return value
    return NotificationPriority(value)


def _as_status(value: NotificationStatus | str) -> NotificationStatus:
    if isinstance(value, NotificationStatus):
        return value
    return NotificationStatus(value)


class NotificationService:
    """High-level notification API with dedupe + rate limits."""

    def __init__(
        self,
        provider: NotificationProvider,
        *,
        session: Session,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._session = session
        self._settings = settings

    @property
    def provider(self) -> NotificationProvider:
        return self._provider

    def is_configured(self) -> bool:
        return self._provider.is_configured()

    def notify(
        self,
        *,
        title: str,
        body: str,
        priority: NotificationPriority,
        category: NotificationCategory,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
        force_info: bool = False,
        commit: bool = True,
    ) -> NotificationRecord:
        """Send a notification or return the existing idempotent record.

        Raises NotificationConfigurationError when Telegram is not configured.
        Raises NotificationRateLimitError when anti-spam caps are hit.
        """
        if not title.strip() or not body.strip():
            raise NotificationValidationError("title and body are required")
        if not idempotency_key.strip():
            raise NotificationValidationError("idempotency_key is required")

        existing = self._find_by_key(idempotency_key)
        if existing is not None:
            return self._handle_existing(existing)

        priority = _as_priority(priority)
        # Anti-spam: drop INFO unless explicitly forced
        min_priority = _as_priority(self._settings.notification_min_priority)
        if (
            _PRIORITY_RANK[priority] < _PRIORITY_RANK[min_priority]
            and not force_info
        ):
            record = NotificationRecord(
                idempotency_key=idempotency_key,
                channel="telegram",
                priority=priority,
                category=category,
                status=NotificationStatus.SKIPPED,
                title=title.strip()[:200],
                body=body.strip()[:4000],
                provider=self._provider.name,
                error_message="below_min_priority",
                extra_metadata={"skipped": True, **(metadata or {})},
            )
            self._session.add(record)
            self._finalize(commit=commit)
            logger.info(
                "notification_skipped_priority key=%s priority=%s min=%s",
                idempotency_key,
                priority.value,
                min_priority.value,
            )
            return record

        if not self.is_configured():
            raise NotificationConfigurationError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured",
                details={"provider": self._provider.name},
            )

        sent_hour = self._count_sent_since(utc_now() - timedelta(hours=1))
        if sent_hour >= self._settings.notification_max_per_hour:
            record = self._persist_rate_limited(
                idempotency_key=idempotency_key,
                title=title,
                body=body,
                priority=priority,
                category=category,
                metadata=metadata,
                reason="hourly_cap",
                sent_hour=sent_hour,
                commit=commit,
            )
            raise NotificationRateLimitError(
                "Hourly notification limit reached (anti-spam)",
                details={
                    "sent_last_hour": sent_hour,
                    "limit": self._settings.notification_max_per_hour,
                    "notification_id": str(record.id),
                },
            )

        if priority == NotificationPriority.INFO:
            info_day = self._count_sent_since(
                utc_now() - timedelta(hours=24),
                priority=NotificationPriority.INFO,
            )
            if info_day >= self._settings.notification_max_info_per_day:
                record = self._persist_rate_limited(
                    idempotency_key=idempotency_key,
                    title=title,
                    body=body,
                    priority=priority,
                    category=category,
                    metadata=metadata,
                    reason="info_daily_cap",
                    sent_hour=info_day,
                    commit=commit,
                )
                raise NotificationRateLimitError(
                    "Daily INFO notification limit reached (anti-spam)",
                    details={
                        "info_sent_last_day": info_day,
                        "limit": self._settings.notification_max_info_per_day,
                        "notification_id": str(record.id),
                    },
                )

        record = NotificationRecord(
            idempotency_key=idempotency_key,
            channel="telegram",
            priority=priority,
            category=category,
            status=NotificationStatus.PENDING,
            title=title.strip()[:200],
            body=body.strip()[:4000],
            provider=self._provider.name,
            extra_metadata=dict(metadata or {}),
        )
        self._session.add(record)
        self._session.flush()

        try:
            response = self._provider.send(
                NotificationSendRequest(
                    title=record.title,
                    body=record.body,
                    priority=priority,
                    category=category,
                    idempotency_key=idempotency_key,
                    metadata={"notification_id": str(record.id)},
                )
            )
            record.status = NotificationStatus.SENT
            record.sent_at = utc_now()
            record.provider_message_id = response.provider_message_id
            record.extra_metadata = {
                **(record.extra_metadata or {}),
                "latency_ms": response.latency_ms,
                "attempts": response.attempts,
            }
            self._finalize(commit=commit)
            return record
        except Exception as exc:  # noqa: BLE001
            record.status = NotificationStatus.FAILED
            record.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            token = None
            if self._settings.telegram_bot_token is not None:
                token = self._settings.telegram_bot_token.get_secret_value()
                if token and token in (record.error_message or ""):
                    record.error_message = (record.error_message or "").replace(token, "***")
            self._finalize(commit=commit)
            raise

    def try_notify(self, **kwargs: Any) -> NotificationRecord | None:
        """Best-effort notify — returns None when not configured (no raise)."""
        if not self.is_configured():
            logger.info(
                "notification_skipped_unconfigured category=%s",
                getattr(kwargs.get("category"), "value", kwargs.get("category")),
            )
            return None
        kwargs.setdefault("commit", False)
        try:
            return self.notify(**kwargs)
        except NotificationRateLimitError:
            logger.warning("notification_rate_limited category=%s", kwargs.get("category"))
            return None
        except Exception:  # noqa: BLE001
            logger.exception("notification_try_failed")
            return None

    # Convenience emitters for important owner events ------------------------
    def notify_approval_request(
        self,
        *,
        approval_id: UUID,
        action_type: str,
        risk_level: str,
        description: str,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Approval required",
            body=(
                f"Action: {action_type}\n"
                f"Risk: {risk_level}\n"
                f"{description[:500]}\n"
                f"approval_id={approval_id}"
            ),
            priority=NotificationPriority.IMPORTANT,
            category=NotificationCategory.APPROVAL_REQUEST,
            idempotency_key=f"notify:approval:{approval_id}",
            metadata={"approval_id": str(approval_id)},
        )

    def notify_critical_failure(
        self,
        *,
        source: str,
        message: str,
        reference: str,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Critical failure",
            body=f"Source: {source}\n{message[:800]}\nref={reference}",
            priority=NotificationPriority.CRITICAL,
            category=NotificationCategory.CRITICAL_FAILURE,
            idempotency_key=f"notify:failure:{reference}",
            metadata={"source": source, "reference": reference},
        )

    def notify_daily_ceo_report(
        self,
        *,
        report_id: UUID,
        title: str,
        summary: str | None = None,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Daily CEO report ready",
            body=f"{title}\n\n{(summary or 'Report generated.')[:1500]}\nreport_id={report_id}",
            priority=NotificationPriority.IMPORTANT,
            category=NotificationCategory.DAILY_CEO_REPORT,
            idempotency_key=f"notify:report:{report_id}",
            metadata={"report_id": str(report_id)},
        )

    def notify_major_opportunity(
        self,
        *,
        label: str,
        reference: str,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Major opportunity",
            body=f"{label[:800]}\nref={reference}",
            priority=NotificationPriority.IMPORTANT,
            category=NotificationCategory.MAJOR_OPPORTUNITY,
            idempotency_key=f"notify:opportunity:{reference}",
        )

    def notify_blocked_task(
        self,
        *,
        task_key: str,
        project_id: UUID | str,
        detail: str,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Delivery task blocked",
            body=f"Task: {task_key}\nProject: {project_id}\n{detail[:500]}",
            priority=NotificationPriority.URGENT,
            category=NotificationCategory.BLOCKED_TASK,
            idempotency_key=f"notify:blocked:{project_id}:{task_key}",
        )

    def notify_budget_warning(
        self,
        *,
        message: str,
        reference: str,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Budget warning",
            body=f"{message[:800]}\nref={reference}",
            priority=NotificationPriority.URGENT,
            category=NotificationCategory.BUDGET_WARNING,
            idempotency_key=f"notify:budget:{reference}",
        )

    def notify_security_warning(
        self,
        *,
        message: str,
        reference: str,
    ) -> NotificationRecord | None:
        return self.try_notify(
            title="Security warning",
            body=f"{message[:800]}\nref={reference}",
            priority=NotificationPriority.CRITICAL,
            category=NotificationCategory.SECURITY_WARNING,
            idempotency_key=f"notify:security:{reference}",
        )

    # Internals --------------------------------------------------------------
    def _handle_existing(self, existing: NotificationRecord) -> NotificationRecord:
        status = _as_status(existing.status)
        if status == NotificationStatus.SENT:
            logger.info(
                "notification_idempotent_replay id=%s key=%s",
                existing.id,
                existing.idempotency_key,
            )
            return existing
        if status == NotificationStatus.PENDING:
            raise NotificationIdempotencyError(
                "Notification already in flight for this idempotency key",
                details={
                    "notification_id": str(existing.id),
                    "status": status.value,
                },
            )
        if status in {
            NotificationStatus.FAILED,
            NotificationStatus.RATE_LIMITED,
            NotificationStatus.SKIPPED,
            NotificationStatus.DUPLICATE,
        }:
            # Return existing without resending — prevents spam retries
            return existing
        raise NotificationIdempotencyError(
            "Notification already exists for this idempotency key",
            details={
                "notification_id": str(existing.id),
                "status": status.value,
            },
        )

    def _find_by_key(self, key: str) -> NotificationRecord | None:
        return self._session.scalar(
            select(NotificationRecord).where(NotificationRecord.idempotency_key == key)
        )

    def _count_sent_since(
        self,
        since: datetime,
        *,
        priority: NotificationPriority | None = None,
    ) -> int:
        q = (
            select(func.count())
            .select_from(NotificationRecord)
            .where(
                NotificationRecord.status == NotificationStatus.SENT.value,
                NotificationRecord.sent_at.is_not(None),
                NotificationRecord.sent_at >= since,
            )
        )
        if priority is not None:
            q = q.where(NotificationRecord.priority == priority.value)
        return int(self._session.scalar(q) or 0)

    def _persist_rate_limited(
        self,
        *,
        idempotency_key: str,
        title: str,
        body: str,
        priority: NotificationPriority,
        category: NotificationCategory,
        metadata: dict[str, Any] | None,
        reason: str,
        sent_hour: int,
        commit: bool = True,
    ) -> NotificationRecord:
        record = NotificationRecord(
            idempotency_key=idempotency_key,
            channel="telegram",
            priority=priority,
            category=category,
            status=NotificationStatus.RATE_LIMITED,
            title=title.strip()[:200],
            body=body.strip()[:4000],
            provider=self._provider.name,
            error_message=reason,
            extra_metadata={"sent_window_count": sent_hour, **(metadata or {})},
        )
        self._session.add(record)
        self._finalize(commit=commit)
        return record

    def _finalize(self, *, commit: bool) -> None:
        if commit:
            self._session.commit()
        else:
            self._session.flush()


def build_notification_service(
    session: Session,
    settings: Settings | None = None,
    *,
    provider: NotificationProvider | None = None,
) -> NotificationService:
    cfg = settings or get_settings()
    return NotificationService(
        provider or TelegramProvider(cfg),
        session=session,
        settings=cfg,
    )
