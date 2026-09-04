"""Owner customer catalog — persisted customers only."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import NotFoundError
from app.models import Customer, DeliveryActivity, DeliveryProject, RevenueEntry
from app.models.enums import DeliveryProjectStatus


class CustomerListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    email: str | None = None
    status: str
    converted_at: datetime | None = None
    company_id: UUID | None = None
    project_count: int = 0
    open_work: int = 0
    revenue_known: str | None = None


class CustomerDetailView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    customer: dict[str, Any]
    status: str
    revenue_value: str | None = None
    projects: list[dict[str, Any]]
    open_work: list[dict[str, Any]]
    recent_activity: list[dict[str, Any]]
    next_action: str


class CustomerListView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CustomerListItem]
    total: int
    limit: int
    offset: int


_NOT_AVAILABLE = "not available"


class CustomerCatalogService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_customers(
        self, *, limit: int = 50, offset: int = 0, q: str | None = None
    ) -> CustomerListView:
        capped = max(1, min(limit, 100))
        off = max(0, offset)
        stmt = select(Customer)
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(Customer.name.ilike(like), Customer.email.ilike(like))
            )
        total = int(
            self._session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = self._session.scalars(
            stmt.order_by(Customer.converted_at.desc()).offset(off).limit(capped)
        ).all()
        items = [self._to_list_item(c) for c in rows]
        return CustomerListView(items=items, total=total, limit=capped, offset=off)

    def get_customer(self, customer_id: UUID) -> CustomerDetailView:
        customer = self._session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError(
                "Customer not found", details={"customer_id": str(customer_id)}
            )
        projects = self._session.scalars(
            select(DeliveryProject)
            .where(DeliveryProject.customer_id == customer.id)
            .order_by(DeliveryProject.updated_at.desc())
            .limit(50)
        ).all()
        activities: list[DeliveryActivity] = []
        if projects:
            project_ids = [p.id for p in projects]
            activities = list(
                self._session.scalars(
                    select(DeliveryActivity)
                    .where(DeliveryActivity.project_id.in_(project_ids))
                    .order_by(DeliveryActivity.created_at.desc())
                    .limit(20)
                ).all()
            )

        revenue = self._session.scalar(
            select(func.coalesce(func.sum(RevenueEntry.amount), 0)).where(
                RevenueEntry.customer_id == customer.id
            )
        )
        open_projects = [
            p
            for p in projects
            if (
                p.status.value
                if hasattr(p.status, "value")
                else str(p.status)
            )
            not in {
                DeliveryProjectStatus.COMPLETED.value,
                DeliveryProjectStatus.CANCELLED.value,
                "completed",
                "cancelled",
            }
        ]
        next_action = (
            f"Continue work on {open_projects[0].name}"
            if open_projects
            else "No open delivery work"
        )
        return CustomerDetailView(
            id=customer.id,
            customer={
                "name": customer.name,
                "email": customer.email or _NOT_AVAILABLE,
                "company_id": str(customer.company_id),
                "converted_at": str(customer.converted_at),
            },
            status=customer.status.value
            if hasattr(customer.status, "value")
            else str(customer.status),
            revenue_value=str(revenue) if revenue else _NOT_AVAILABLE,
            projects=[
                {
                    "id": str(p.id),
                    "name": getattr(p, "name", None) or getattr(p, "title", "Project"),
                    "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                }
                for p in projects
            ],
            open_work=[
                {
                    "id": str(p.id),
                    "name": getattr(p, "name", None) or getattr(p, "title", "Project"),
                    "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                }
                for p in open_projects
            ],
            recent_activity=[
                {
                    "id": str(a.id),
                    "summary": a.message or a.activity_type,
                    "at": str(getattr(a, "created_at", "")),
                }
                for a in activities
            ],
            next_action=next_action,
        )

    def _to_list_item(self, customer: Customer) -> CustomerListItem:
        project_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(DeliveryProject)
                .where(DeliveryProject.customer_id == customer.id)
            )
            or 0
        )
        open_work = int(
            self._session.scalar(
                select(func.count())
                .select_from(DeliveryProject)
                .where(
                    DeliveryProject.customer_id == customer.id,
                    DeliveryProject.status.notin_(
                        [
                            DeliveryProjectStatus.COMPLETED.value,
                            DeliveryProjectStatus.CANCELLED.value,
                        ]
                    ),
                )
            )
            or 0
        )
        return CustomerListItem(
            id=customer.id,
            name=customer.name,
            email=customer.email,
            status=customer.status.value
            if hasattr(customer.status, "value")
            else str(customer.status),
            converted_at=customer.converted_at,
            company_id=customer.company_id,
            project_count=project_count,
            open_work=open_work,
            revenue_known=None,
        )
