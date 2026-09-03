from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from models.enums import (
    AgentName,
    AgentRunStatus,
    ApprovalStatus,
    ApprovalType,
    CostCategory,
    CustomerStatus,
    DeliveryProjectStatus,
    ExperimentStatus,
    Industry,
    LeadStatus,
    ReportType,
    TaskStatus,
)


def _enum(enum_cls: type, length: int = 50) -> Enum:
    return Enum(enum_cls, native_enum=False, length=length)


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    industry: Mapped[Industry] = mapped_column(
        _enum(Industry), nullable=False, default=Industry.OTHER
    )
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    leads: Mapped[list["Lead"]] = relationship(back_populates="company")
    customers: Mapped[list["Customer"]] = relationship(back_populates="company")


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "website_quality_score IS NULL OR (website_quality_score >= 0 AND website_quality_score <= 20)",
            name="website_quality_range",
        ),
        CheckConstraint(
            "online_presence_score IS NULL OR (online_presence_score >= 0 AND online_presence_score <= 20)",
            name="online_presence_range",
        ),
        CheckConstraint(
            "lead_capture_score IS NULL OR (lead_capture_score >= 0 AND lead_capture_score <= 20)",
            name="lead_capture_range",
        ),
        CheckConstraint(
            "automation_potential_score IS NULL OR (automation_potential_score >= 0 AND automation_potential_score <= 20)",
            name="automation_potential_range",
        ),
        CheckConstraint(
            "commercial_potential_score IS NULL OR (commercial_potential_score >= 0 AND commercial_potential_score <= 20)",
            name="commercial_potential_range",
        ),
        CheckConstraint(
            "total_score IS NULL OR (total_score >= 0 AND total_score <= 100)",
            name="total_score_range",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[LeadStatus] = mapped_column(
        _enum(LeadStatus), nullable=False, default=LeadStatus.NEW, index=True
    )
    website_quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    online_presence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lead_capture_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    automation_potential_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commercial_potential_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    company: Mapped[Company] = relationship(back_populates="leads")
    customer: Mapped["Customer | None"] = relationship(back_populates="lead")


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    status: Mapped[CustomerStatus] = mapped_column(
        _enum(CustomerStatus), nullable=False, default=CustomerStatus.ACTIVE, index=True
    )
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(back_populates="customers")
    lead: Mapped[Lead | None] = relationship(back_populates="customer")
    delivery_projects: Mapped[list["DeliveryProject"]] = relationship(back_populates="customer")


class DeliveryProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "delivery_projects"

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DeliveryProjectStatus] = mapped_column(
        _enum(DeliveryProjectStatus),
        nullable=False,
        default=DeliveryProjectStatus.PLANNED,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="delivery_projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="delivery_project")


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    agent_name: Mapped[AgentName] = mapped_column(
        _enum(AgentName), nullable=False, index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        _enum(AgentRunStatus), nullable=False, default=AgentRunStatus.PENDING, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        _enum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True
    )
    delivery_project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("delivery_projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    delivery_project: Mapped[DeliveryProject | None] = relationship(back_populates="tasks")


class Approval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approvals"

    approval_type: Mapped[ApprovalType] = mapped_column(
        _enum(ApprovalType), nullable=False, index=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        _enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requested_by_agent: Mapped[AgentName] = mapped_column(_enum(AgentName), nullable=False)
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CostEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_entries"

    category: Mapped[CostCategory] = mapped_column(
        _enum(CostCategory), nullable=False, default=CostCategory.OTHER, index=True
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    incurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RevenueEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "revenue_entries"

    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    delivery_project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("delivery_projects.id", ondelete="SET NULL"), nullable=True
    )
    recognized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DailyMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "daily_metrics"

    metric_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    leads_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outreach_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approvals_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_customers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    report_type: Mapped[ReportType] = mapped_column(
        _enum(ReportType), nullable=False, default=ReportType.DAILY, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExperimentStatus] = mapped_column(
        _enum(ExperimentStatus), nullable=False, default=ExperimentStatus.DRAFT, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
