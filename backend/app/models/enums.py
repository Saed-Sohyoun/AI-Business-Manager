"""Shared enumerations for domain models."""

from __future__ import annotations

import enum


class CompanyStatus(str, enum.Enum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    CONVERTED = "converted"
    ARCHIVED = "archived"


class LeadScoreCategory(str, enum.Enum):
    UNSCORED = "unscored"
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


class AgentRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RiskLevel(str, enum.Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class ScoreBand(str, enum.Enum):
    """Company lead-score bands (0–100 total)."""

    LOW = "low"  # 0–49
    MEDIUM = "medium"  # 50–69
    GOOD = "good"  # 70–84
    HIGH = "high"  # 85–100


class AuditPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditStatus(str, enum.Enum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class OutreachStatus(str, enum.Enum):
    """Outbound outreach / email lifecycle."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OutboundMessageStatus(str, enum.Enum):
    """Outbound email message state machine."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FollowUpSequenceStatus(str, enum.Enum):
    """Lifecycle of a per-lead follow-up sequence."""

    ACTIVE = "active"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    STOPPED = "stopped"


class FollowUpStopReason(str, enum.Enum):
    """Why a follow-up sequence stopped or an item was skipped."""

    NONE = "none"
    REPLIED = "replied"
    OPTED_OUT = "opted_out"
    BECAME_CUSTOMER = "became_customer"
    BLOCKED = "blocked"
    APPROVAL_MISSING = "approval_missing"
    MAX_FOLLOWUPS = "max_followups"
    CANCELLED = "cancelled"
    DUPLICATE = "duplicate"


class FollowUpItemStatus(str, enum.Enum):
    """Individual scheduled follow-up message state."""

    SCHEDULED = "scheduled"
    DRAFT_READY = "draft_ready"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManagerRunStatus(str, enum.Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class ManagerTaskStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    INVALID = "invalid"


class ManagerDecisionType(str, enum.Enum):
    PLAN_CREATED = "plan_created"
    DELEGATE = "delegate"
    EXECUTE = "execute"
    VERIFY = "verify"
    MEASURE = "measure"
    RETRY = "retry"
    REQUEST_APPROVAL = "request_approval"
    SKIP = "skip"
    STOP = "stop"
    COMPLETE = "complete"
    ACT = "act"
    REJECT_INVALID = "reject_invalid"


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CHURNED = "churned"


class DeliveryProjectStatus(str, enum.Enum):
    """Project lifecycle after a lead becomes a customer."""

    PLANNING = "planning"
    ACTIVE = "active"
    DELIVERY = "delivery"
    VERIFICATION = "verification"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectTaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeliverableStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CostCategory(str, enum.Enum):
    """Operational cost categories tracked by FinanceAgent."""

    AI = "ai"
    SEARCH = "search"
    EMAIL = "email"
    BROWSER = "browser"
    DELIVERY = "delivery"
    OTHER_OPERATIONAL = "other_operational"


class RevenueType(str, enum.Enum):
    ONE_TIME = "one_time"
    SUBSCRIPTION = "subscription"
    ADJUSTMENT = "adjustment"
    OTHER = "other"


class ReportPeriodType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportStatementKind(str, enum.Enum):
    FACT = "fact"
    INTERPRETATION = "interpretation"
    RECOMMENDATION = "recommendation"
    UNAVAILABLE = "unavailable"


class BusinessReportStatus(str, enum.Enum):
    GENERATED = "generated"
    FAILED = "failed"


class NotificationPriority(str, enum.Enum):
    INFO = "info"
    IMPORTANT = "important"
    URGENT = "urgent"
    CRITICAL = "critical"


class NotificationCategory(str, enum.Enum):
    APPROVAL_REQUEST = "approval_request"
    CRITICAL_FAILURE = "critical_failure"
    DAILY_CEO_REPORT = "daily_ceo_report"
    MAJOR_OPPORTUNITY = "major_opportunity"
    BLOCKED_TASK = "blocked_task"
    BUDGET_WARNING = "budget_warning"
    DAILY_LIMIT = "daily_limit"
    SECURITY_WARNING = "security_warning"
    OTHER = "other"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    RATE_LIMITED = "rate_limited"
    DUPLICATE = "duplicate"


class WorkflowName(str, enum.Enum):
    """n8n-triggered workflow names — orchestration only; logic stays in backend."""

    DAILY_CYCLE = "daily_cycle"
    RESEARCH = "research"
    AUDIT = "audit"
    OUTREACH_APPROVAL_QUEUE = "outreach_approval_queue"
    FOLLOW_UPS = "follow_ups"
    DAILY_REPORT = "daily_report"
    ERROR_MONITORING = "error_monitoring"


class WorkflowExecutionStatus(str, enum.Enum):
    RECEIVED = "received"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
