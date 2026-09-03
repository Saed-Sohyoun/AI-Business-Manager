from enum import Enum


class Industry(str, Enum):
    CLEANING = "cleaning"
    PAINTING = "painting"
    REPAIR = "repair"
    MOVING = "moving"
    BARBER = "barber"
    BEAUTY = "beauty"
    REAL_ESTATE = "real_estate"
    RESTAURANT = "restaurant"
    OTHER = "other"


class LeadStatus(str, Enum):
    NEW = "new"
    RESEARCHING = "researching"
    AUDITED = "audited"
    SCORED = "scored"
    AWAITING_APPROVAL = "awaiting_approval"
    OUTREACH = "outreach"
    REPLIED = "replied"
    WON = "won"
    LOST = "lost"
    DISQUALIFIED = "disqualified"


class AgentName(str, Enum):
    MANAGER = "manager"
    RESEARCH = "research"
    AUDIT = "audit"
    SALES = "sales"
    DELIVERY = "delivery"
    FINANCE = "finance"
    REPORT = "report"


class AgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalType(str, Enum):
    FIRST_EXTERNAL_OUTREACH = "first_external_outreach"
    SPENDING_MONEY = "spending_money"
    DISCOUNT_ABOVE_15 = "discount_above_15"
    CONTRACT_LEGAL = "contract_legal"
    MAJOR_BUSINESS_CHANGE = "major_business_change"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CustomerStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CHURNED = "churned"


class DeliveryProjectStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class CostCategory(str, Enum):
    AI = "ai"
    SEARCH = "search"
    BROWSER = "browser"
    EMAIL = "email"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"


class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    AD_HOC = "ad_hoc"


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
