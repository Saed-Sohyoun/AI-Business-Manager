"""Customer, delivery project, tasks, and deliverables."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import (
    CustomerStatus,
    DeliverableStatus,
    DeliveryProjectStatus,
    ProjectTaskStatus,
)

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.lead import Lead


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A converted lead / paying (or contracted) customer — no billing in Phase 13."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("lead_id", name="uq_customers_lead_id"),
        UniqueConstraint("idempotency_key", name="uq_customers_idempotency_key"),
        Index("ix_customers_company_id", "company_id"),
        Index("ix_customers_status", "status"),
        Index("ix_customers_email", "email"),
    )

    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    status: Mapped[CustomerStatus] = mapped_column(
        String(32),
        nullable=False,
        default=CustomerStatus.ACTIVE,
        server_default=CustomerStatus.ACTIVE.value,
    )
    converted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    company: Mapped["Company"] = relationship("Company")
    lead: Mapped[Optional["Lead"]] = relationship("Lead")
    projects: Mapped[list["DeliveryProject"]] = relationship(
        "DeliveryProject",
        back_populates="customer",
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} name={self.name!r} status={self.status}>"


class DeliveryProject(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Customer delivery engagement with lifecycle tracking."""

    __tablename__ = "delivery_projects"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_delivery_projects_idempotency_key"),
        Index("ix_delivery_projects_customer_id", "customer_id"),
        Index("ix_delivery_projects_company_id", "company_id"),
        Index("ix_delivery_projects_status", "status"),
    )

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[DeliveryProjectStatus] = mapped_column(
        String(32),
        nullable=False,
        default=DeliveryProjectStatus.PLANNING,
        server_default=DeliveryProjectStatus.PLANNING.value,
    )

    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="projects")
    company: Mapped["Company"] = relationship("Company")
    tasks: Mapped[list["ProjectTask"]] = relationship(
        "ProjectTask",
        back_populates="project",
        order_by="ProjectTask.sort_order",
    )
    deliverables: Mapped[list["Deliverable"]] = relationship(
        "Deliverable",
        back_populates="project",
    )
    activities: Mapped[list["DeliveryActivity"]] = relationship(
        "DeliveryActivity",
        back_populates="project",
        order_by="DeliveryActivity.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<DeliveryProject id={self.id} name={self.name!r} status={self.status}>"
        )


class ProjectTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A unit of delivery work; completion requires verification."""

    __tablename__ = "project_tasks"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "task_key",
            name="uq_project_tasks_project_id_task_key",
        ),
        Index("ix_project_tasks_project_id", "project_id"),
        Index("ix_project_tasks_status", "status"),
        Index("ix_project_tasks_sort_order", "sort_order"),
    )

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("delivery_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    status: Mapped[ProjectTaskStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ProjectTaskStatus.PENDING,
        server_default=ProjectTaskStatus.PENDING.value,
    )
    # List of task_key strings this task depends on (same project).
    depends_on: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    is_sensitive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    approval_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )

    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    project: Mapped["DeliveryProject"] = relationship(
        "DeliveryProject",
        back_populates="tasks",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectTask id={self.id} key={self.task_key!r} status={self.status}>"
        )


class Deliverable(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Concrete output produced during delivery."""

    __tablename__ = "deliverables"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_deliverables_idempotency_key"),
        Index("ix_deliverables_project_id", "project_id"),
        Index("ix_deliverables_task_id", "task_id"),
        Index("ix_deliverables_status", "status"),
    )

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("delivery_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    deliverable_type: Mapped[str] = mapped_column(String(64), nullable=False, default="document")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[DeliverableStatus] = mapped_column(
        String(32),
        nullable=False,
        default=DeliverableStatus.DRAFT,
        server_default=DeliverableStatus.DRAFT.value,
    )
    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    produced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    project: Mapped["DeliveryProject"] = relationship(
        "DeliveryProject",
        back_populates="deliverables",
    )
    task: Mapped[Optional["ProjectTask"]] = relationship("ProjectTask")

    def __repr__(self) -> str:
        return f"<Deliverable id={self.id} title={self.title!r} status={self.status}>"


class DeliveryActivity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable-ish activity log for delivery progress."""

    __tablename__ = "delivery_activities"
    __table_args__ = (
        Index("ix_delivery_activities_project_id", "project_id"),
        Index("ix_delivery_activities_task_id", "task_id"),
        Index("ix_delivery_activities_activity_type", "activity_type"),
        Index("ix_delivery_activities_created_at", "created_at"),
    )

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("delivery_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("project_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="delivery")
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    project: Mapped["DeliveryProject"] = relationship(
        "DeliveryProject",
        back_populates="activities",
    )

    def __repr__(self) -> str:
        return (
            f"<DeliveryActivity id={self.id} type={self.activity_type!r} "
            f"project={self.project_id}>"
        )
