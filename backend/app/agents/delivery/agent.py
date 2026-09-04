"""Delivery Agent — customer projects, tasks, verification, deliverables.

Lifecycle: LEAD → CUSTOMER → PROJECT → TASKS → DELIVERY → VERIFICATION → COMPLETION

Never marks work COMPLETED without verification.
Sensitive task execution requires ApprovalService (YELLOW).
No billing.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.delivery.schemas import (
    DeliveryRequest,
    DeliveryRunResult,
    ProjectProgress,
    TaskSpec,
    TaskView,
)
from app.approvals.schemas import ApprovalRequest
from app.approvals.service import ApprovalService
from app.config import Settings
from app.exceptions import ForbiddenError, ValidationAppError
from app.models import (
    AgentRun,
    Customer,
    DailyMetric,
    Deliverable,
    DeliveryActivity,
    DeliveryProject,
    Lead,
    ProjectTask,
)
from app.models.base import utc_now
from app.models.enums import (
    AgentRunStatus,
    ApprovalStatus,
    CustomerStatus,
    DeliverableStatus,
    DeliveryProjectStatus,
    FollowUpStopReason,
    LeadStatus,
    ProjectTaskStatus,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "delivery"
TASK_TYPE = "create_project"

ACTION_CREATE_PROJECT = "delivery.create_project"
ACTION_CREATE_TASKS = "delivery.create_tasks"
ACTION_EXECUTE_SAFE = "delivery.execute_safe_task"
ACTION_EXECUTE_SENSITIVE = "delivery.execute_sensitive_task"
ACTION_VERIFY_TASK = "delivery.verify_task"
ACTION_PRODUCE_DELIVERABLE = "delivery.produce_deliverable"
ACTION_VERIFY_PROJECT = "delivery.verify_project"
ACTION_COMPLETE_PROJECT = "delivery.complete_project"

DEFAULT_TASKS: list[TaskSpec] = [
    TaskSpec(
        task_key="kickoff",
        title="Project kickoff & scope",
        description="Confirm scope, success criteria, and timeline with the customer.",
        depends_on=[],
        is_sensitive=False,
        sort_order=10,
    ),
    TaskSpec(
        task_key="requirements",
        title="Gather requirements",
        description="Collect and document delivery requirements.",
        depends_on=["kickoff"],
        is_sensitive=False,
        sort_order=20,
    ),
    TaskSpec(
        task_key="draft_deliverable",
        title="Produce deliverable draft",
        description="Create the primary delivery artifact draft.",
        depends_on=["requirements"],
        is_sensitive=False,
        sort_order=30,
    ),
    TaskSpec(
        task_key="internal_review",
        title="Internal review",
        description="Review draft quality and completeness before customer handoff.",
        depends_on=["draft_deliverable"],
        is_sensitive=False,
        sort_order=40,
    ),
    TaskSpec(
        task_key="customer_handoff",
        title="Customer handoff",
        description="Deliver final package to the customer (sensitive / approval required).",
        depends_on=["internal_review"],
        is_sensitive=True,
        sort_order=50,
    ),
]


def _as_task_status(value: ProjectTaskStatus | str) -> ProjectTaskStatus:
    if isinstance(value, ProjectTaskStatus):
        return value
    return ProjectTaskStatus(value)


def _as_project_status(value: DeliveryProjectStatus | str) -> DeliveryProjectStatus:
    if isinstance(value, DeliveryProjectStatus):
        return value
    return DeliveryProjectStatus(value)


class DeliveryAgent:
    """Owns customer conversion, projects, task execution, verification, deliverables."""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._approvals = approval_service or ApprovalService(session, settings)

    # ----------------------------------------------------------------- run
    def run(self, request: DeliveryRequest) -> DeliveryRunResult:
        logs: list[str] = []

        if request.idempotency_key:
            existing = self._find_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                return self._result_from_existing(existing, logs=["idempotent_replay"])

        try:
            self._approvals.assert_executable(ACTION_CREATE_PROJECT)
        except ForbiddenError as exc:
            return DeliveryRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=f"approval_gate: {exc.message}",
                logs=["create_project_blocked_by_gate"],
            )

        lead = self._session.get(Lead, request.lead_id)
        if lead is None:
            return DeliveryRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message="lead_not_found",
                logs=["lead_not_found"],
            )

        agent_run = AgentRun(
            agent_name=AGENT_NAME,
            task_type=TASK_TYPE,
            status=AgentRunStatus.RUNNING,
            input_summary=f"lead_id={lead.id} name={lead.name!r}",
            idempotency_key=request.idempotency_key,
            estimated_cost=Decimal("0"),
            extra_metadata={
                "lead_id": str(lead.id),
                **(request.metadata or {}),
            },
        )
        try:
            self._session.add(agent_run)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            return DeliveryRunResult(
                agent_run_id=UUID(int=0),
                status="failed",
                error_message=f"database_failure: {type(exc).__name__}",
                logs=["database_failure_on_run_create"],
            )

        try:
            customer = self.convert_lead_to_customer(lead.id, commit=False)
            logs.append("customer_ready")

            project_name = request.project_name or f"Delivery for {lead.name}"
            project = self.create_project(
                customer_id=customer.id,
                name=project_name,
                description=request.project_description,
                idempotency_key=(
                    f"delivery-project:{request.idempotency_key}"
                    if request.idempotency_key
                    else f"delivery-project:lead:{lead.id}:default"
                ),
                agent_run_id=agent_run.id,
                commit=False,
            )
            logs.append("project_created")

            specs = request.tasks if request.tasks is not None else DEFAULT_TASKS
            tasks = self.create_tasks(project.id, specs, commit=False)
            logs.append(f"tasks_created:{len(tasks)}")

            agent_run.status = AgentRunStatus.SUCCEEDED
            agent_run.completed_at = utc_now()
            agent_run.output_summary = (
                f"customer={customer.id} project={project.id} tasks={len(tasks)}"
            )
            self._session.commit()

            progress = self.get_progress(project.id)
            return DeliveryRunResult(
                agent_run_id=agent_run.id,
                status="succeeded",
                customer_id=customer.id,
                project_id=project.id,
                tasks=[self._task_view(t) for t in tasks],
                progress=progress,
                logs=logs,
            )
        except (ValidationAppError, ForbiddenError) as exc:
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = exc.message
            agent_run.completed_at = utc_now()
            self._session.commit()
            return DeliveryRunResult(
                agent_run_id=agent_run.id,
                status="failed",
                error_message=exc.message,
                logs=logs + ["validation_or_forbidden"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("DeliveryAgent.run failed")
            agent_run.status = AgentRunStatus.FAILED
            agent_run.error_message = f"{type(exc).__name__}: {exc}"
            agent_run.completed_at = utc_now()
            self._session.commit()
            return DeliveryRunResult(
                agent_run_id=agent_run.id,
                status="failed",
                error_message=agent_run.error_message,
                logs=logs + ["unhandled_error"],
            )

    # ------------------------------------------------------------- customer
    def convert_lead_to_customer(
        self,
        lead_id: UUID,
        *,
        commit: bool = True,
    ) -> Customer:
        """LEAD → CUSTOMER. Idempotent per lead."""
        lead = self._session.get(Lead, lead_id)
        if lead is None:
            raise ValidationAppError("Lead not found", details={"lead_id": str(lead_id)})

        key = f"customer:lead:{lead.id}"
        existing = self._session.scalar(
            select(Customer).where(Customer.idempotency_key == key)
        )
        if existing is not None:
            return existing
        by_lead = self._session.scalar(select(Customer).where(Customer.lead_id == lead.id))
        if by_lead is not None:
            return by_lead

        lead.status = LeadStatus.CONVERTED
        customer = Customer(
            company_id=lead.company_id,
            lead_id=lead.id,
            idempotency_key=key,
            name=lead.name,
            email=lead.email,
            status=CustomerStatus.ACTIVE,
            converted_at=utc_now(),
            extra_metadata={"source": "delivery_agent"},
        )
        try:
            with self._session.begin_nested():
                self._session.add(customer)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(Customer).where(Customer.idempotency_key == key)
            )
            if existing is None:
                raise
            return existing

        self._bump_daily_customers()
        try:
            from app.services.follow_up_service import FollowUpService

            FollowUpService(
                session=self._session,
                settings=self._settings,
                approval_service=self._approvals,
            )._stop_lead_sequence(lead.id, FollowUpStopReason.BECAME_CUSTOMER)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.debug("follow-up stop skipped during customer conversion", exc_info=True)

        if commit:
            self._session.commit()
        else:
            self._session.flush()
        logger.info("customer_created id=%s lead_id=%s", customer.id, lead.id)
        return customer

    # -------------------------------------------------------------- project
    def create_project(
        self,
        *,
        customer_id: UUID,
        name: str,
        description: str | None = None,
        idempotency_key: str,
        agent_run_id: UUID | None = None,
        commit: bool = True,
    ) -> DeliveryProject:
        self._approvals.assert_executable(ACTION_CREATE_PROJECT)

        existing = self._session.scalar(
            select(DeliveryProject).where(DeliveryProject.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        customer = self._session.get(Customer, customer_id)
        if customer is None:
            raise ValidationAppError(
                "Customer not found",
                details={"customer_id": str(customer_id)},
            )

        project = DeliveryProject(
            customer_id=customer.id,
            company_id=customer.company_id,
            agent_run_id=agent_run_id,
            idempotency_key=idempotency_key,
            name=name.strip(),
            description=description,
            status=DeliveryProjectStatus.PLANNING,
            verified=False,
            progress_percent=0,
            extra_metadata={},
        )
        try:
            with self._session.begin_nested():
                self._session.add(project)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(DeliveryProject).where(
                    DeliveryProject.idempotency_key == idempotency_key
                )
            )
            if existing is None:
                raise
            return existing

        self._record_activity(
            project.id,
            "project_created",
            f"Project {project.name!r} created",
            commit=False,
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return project

    def create_tasks(
        self,
        project_id: UUID,
        specs: list[TaskSpec],
        *,
        commit: bool = True,
    ) -> list[ProjectTask]:
        self._approvals.assert_executable(ACTION_CREATE_TASKS)

        project = self._session.get(DeliveryProject, project_id)
        if project is None:
            raise ValidationAppError(
                "Project not found",
                details={"project_id": str(project_id)},
            )
        if not specs:
            raise ValidationAppError("At least one task is required")

        keys = [s.task_key for s in specs]
        if len(keys) != len(set(keys)):
            raise ValidationAppError("Duplicate task_key in task specs")
        known = set(keys)
        for spec in specs:
            for dep in spec.depends_on:
                if dep not in known:
                    raise ValidationAppError(
                        f"Task {spec.task_key!r} depends on unknown task_key {dep!r}"
                    )
                if dep == spec.task_key:
                    raise ValidationAppError(
                        f"Task {spec.task_key!r} cannot depend on itself"
                    )

        created: list[ProjectTask] = []
        for spec in specs:
            existing = self._session.scalar(
                select(ProjectTask).where(
                    ProjectTask.project_id == project_id,
                    ProjectTask.task_key == spec.task_key,
                )
            )
            if existing is not None:
                created.append(existing)
                continue
            task = ProjectTask(
                project_id=project_id,
                task_key=spec.task_key,
                title=spec.title,
                description=spec.description,
                sort_order=spec.sort_order,
                status=ProjectTaskStatus.PENDING,
                depends_on=list(spec.depends_on),
                is_sensitive=spec.is_sensitive,
                verified=False,
                extra_metadata={},
            )
            self._session.add(task)
            created.append(task)

        self._session.flush()
        if _as_project_status(project.status) == DeliveryProjectStatus.PLANNING:
            project.status = DeliveryProjectStatus.ACTIVE
        self._record_activity(
            project_id,
            "tasks_created",
            f"Created/ensured {len(created)} tasks",
            commit=False,
        )
        self._refresh_progress(project)
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return created

    # ---------------------------------------------------------------- execute
    def execute_task(self, task_id: UUID, *, notes: str | None = None) -> ProjectTask:
        """Execute a ready task. Sensitive tasks require an APPROVED approval."""
        task = self._require_task(task_id)
        project = self._require_project(task.project_id)

        status = _as_task_status(task.status)
        if status == ProjectTaskStatus.COMPLETED:
            return task
        if status in {ProjectTaskStatus.FAILED, ProjectTaskStatus.CANCELLED}:
            raise ValidationAppError(
                "Cannot execute a failed/cancelled task",
                details={"status": status.value},
            )

        if not self._dependencies_satisfied(task):
            task.status = ProjectTaskStatus.BLOCKED
            self._record_activity(
                project.id,
                "task_blocked",
                f"Task {task.task_key!r} blocked on unmet dependencies",
                task_id=task.id,
                commit=False,
            )
            self._session.commit()
            raise ValidationAppError(
                "Task dependencies are not completed",
                details={
                    "task_key": task.task_key,
                    "depends_on": list(task.depends_on or []),
                },
            )

        if task.is_sensitive:
            self._assert_sensitive_executable(task)
            action = ACTION_EXECUTE_SENSITIVE
        else:
            self._approvals.assert_executable(ACTION_EXECUTE_SAFE)
            action = ACTION_EXECUTE_SAFE

        task.status = ProjectTaskStatus.IN_PROGRESS
        task.started_at = task.started_at or utc_now()
        if _as_project_status(project.status) in {
            DeliveryProjectStatus.PLANNING,
            DeliveryProjectStatus.ACTIVE,
        }:
            project.status = DeliveryProjectStatus.DELIVERY

        # Safe execution: move to REVIEW for verification (never auto-complete)
        task.status = ProjectTaskStatus.REVIEW
        task.extra_metadata = {
            **(task.extra_metadata or {}),
            "last_execution_action": action,
            "execution_notes": (notes or "")[:2000],
            "executed_at": utc_now().isoformat(),
        }
        self._record_activity(
            project.id,
            "task_executed",
            f"Task {task.task_key!r} executed; awaiting verification",
            task_id=task.id,
            commit=False,
            metadata={"action": action, "sensitive": task.is_sensitive},
        )
        self._refresh_progress(project)
        self._session.commit()
        return task

    def request_sensitive_approval(
        self,
        task_id: UUID,
        *,
        requested_by: str = "delivery",
    ) -> UUID:
        task = self._require_task(task_id)
        if not task.is_sensitive:
            raise ValidationAppError(
                "Task is not marked sensitive",
                details={"task_id": str(task_id)},
            )
        gate = self._approvals.evaluate_gate(ACTION_EXECUTE_SENSITIVE)
        if gate.decision != "require_approval":
            raise ForbiddenError(
                "Sensitive execute path misconfigured — expected YELLOW require_approval",
                details={"decision": gate.decision},
            )
        view = self._approvals.request_approval(
            ApprovalRequest(
                action_type=ACTION_EXECUTE_SENSITIVE,
                description=f"Approve sensitive delivery task {task.task_key}",
                requested_by=requested_by,
                action_payload={
                    "task_id": str(task.id),
                    "project_id": str(task.project_id),
                    "task_key": task.task_key,
                    "title": task.title,
                },
                metadata={"task_id": str(task.id)},
            )
        )
        task.approval_id = view.id
        self._record_activity(
            task.project_id,
            "approval_requested",
            f"Approval requested for sensitive task {task.task_key!r}",
            task_id=task.id,
            commit=False,
        )
        self._session.commit()
        return view.id

    # ---------------------------------------------------------------- verify
    def verify_task(
        self,
        task_id: UUID,
        *,
        notes: str,
        actor: str = "delivery",
    ) -> ProjectTask:
        """Mark task verified and COMPLETED. Refuses without notes/verification."""
        self._approvals.assert_executable(ACTION_VERIFY_TASK)
        task = self._require_task(task_id)
        project = self._require_project(task.project_id)

        status = _as_task_status(task.status)
        if status == ProjectTaskStatus.COMPLETED and task.verified:
            return task
        if status not in {ProjectTaskStatus.REVIEW, ProjectTaskStatus.IN_PROGRESS}:
            raise ValidationAppError(
                "Only tasks in REVIEW (or IN_PROGRESS) can be verified",
                details={"status": status.value},
            )
        cleaned = (notes or "").strip()
        if not cleaned:
            raise ValidationAppError("Verification notes are required")

        task.verified = True
        task.verified_at = utc_now()
        task.verification_notes = cleaned[:4000]
        task.status = ProjectTaskStatus.COMPLETED
        task.completed_at = utc_now()

        self._record_activity(
            project.id,
            "task_verified",
            f"Task {task.task_key!r} verified and completed",
            task_id=task.id,
            actor=actor,
            commit=False,
        )
        self._refresh_progress(project)

        # When all tasks completed+verified, move project to VERIFICATION
        progress = self._compute_progress(project)
        if (
            progress.total_tasks > 0
            and progress.completed_tasks == progress.total_tasks
            and progress.verified_tasks == progress.total_tasks
        ):
            project.status = DeliveryProjectStatus.VERIFICATION

        self._session.commit()
        return task

    def complete_task_without_verification(self, task_id: UUID) -> None:
        """Explicitly blocked — completion always requires verify_task."""
        raise ForbiddenError(
            "Never mark work complete without verification",
            details={"task_id": str(task_id)},
        )

    # ---------------------------------------------------------- deliverables
    def produce_deliverable(
        self,
        *,
        project_id: UUID,
        title: str,
        content: str,
        deliverable_type: str = "document",
        task_id: UUID | None = None,
        idempotency_key: str,
        commit: bool = True,
    ) -> Deliverable:
        self._approvals.assert_executable(ACTION_PRODUCE_DELIVERABLE)
        self._require_project(project_id)

        existing = self._session.scalar(
            select(Deliverable).where(Deliverable.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        if task_id is not None:
            task = self._require_task(task_id)
            if task.project_id != project_id:
                raise ValidationAppError("Deliverable task does not belong to project")

        deliverable = Deliverable(
            project_id=project_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            title=title.strip(),
            deliverable_type=deliverable_type.strip() or "document",
            content=content,
            status=DeliverableStatus.DRAFT,
            verified=False,
            produced_at=utc_now(),
            extra_metadata={},
        )
        try:
            with self._session.begin_nested():
                self._session.add(deliverable)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(Deliverable).where(Deliverable.idempotency_key == idempotency_key)
            )
            if existing is None:
                raise
            return existing

        self._record_activity(
            project_id,
            "deliverable_produced",
            f"Deliverable {title!r} produced",
            task_id=task_id,
            commit=False,
            metadata={"deliverable_id": str(deliverable.id)},
        )
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return deliverable

    def verify_deliverable(
        self,
        deliverable_id: UUID,
        *,
        notes: str = "verified",
    ) -> Deliverable:
        deliverable = self._session.get(Deliverable, deliverable_id)
        if deliverable is None:
            raise ValidationAppError(
                "Deliverable not found",
                details={"deliverable_id": str(deliverable_id)},
            )
        if not (notes or "").strip():
            raise ValidationAppError("Verification notes are required")
        deliverable.verified = True
        deliverable.status = DeliverableStatus.READY
        deliverable.extra_metadata = {
            **(deliverable.extra_metadata or {}),
            "verification_notes": notes.strip()[:2000],
            "verified_at": utc_now().isoformat(),
        }
        self._record_activity(
            deliverable.project_id,
            "deliverable_verified",
            f"Deliverable {deliverable.title!r} verified",
            task_id=deliverable.task_id,
            commit=False,
        )
        self._session.commit()
        return deliverable

    # ----------------------------------------------------- project complete
    def verify_project(
        self,
        project_id: UUID,
        *,
        notes: str,
        actor: str = "delivery",
    ) -> DeliveryProject:
        self._approvals.assert_executable(ACTION_VERIFY_PROJECT)
        project = self._require_project(project_id)
        cleaned = (notes or "").strip()
        if not cleaned:
            raise ValidationAppError("Project verification notes are required")

        progress = self._compute_progress(project)
        if progress.total_tasks == 0:
            raise ValidationAppError("Cannot verify a project with no tasks")
        if progress.completed_tasks != progress.total_tasks:
            raise ValidationAppError(
                "All tasks must be completed before project verification",
                details=progress.model_dump(mode="json"),
            )
        if progress.verified_tasks != progress.total_tasks:
            raise ValidationAppError(
                "All tasks must be verified before project verification",
                details=progress.model_dump(mode="json"),
            )

        project.verified = True
        project.verified_at = utc_now()
        project.verification_notes = cleaned[:4000]
        project.status = DeliveryProjectStatus.VERIFICATION
        self._record_activity(
            project.id,
            "project_verified",
            "Project verified; ready for completion",
            actor=actor,
            commit=False,
        )
        self._session.commit()
        return project

    def complete_project(self, project_id: UUID) -> DeliveryProject:
        """COMPLETION — only after project verification. Never skips verification."""
        self._approvals.assert_executable(ACTION_COMPLETE_PROJECT)
        project = self._require_project(project_id)

        if not project.verified:
            raise ForbiddenError(
                "Never mark work complete without verification",
                details={"project_id": str(project_id), "verified": False},
            )
        progress = self._compute_progress(project)
        if progress.verified_tasks != progress.total_tasks or progress.total_tasks == 0:
            raise ForbiddenError(
                "Never mark work complete without verification",
                details=progress.model_dump(mode="json"),
            )

        project.status = DeliveryProjectStatus.COMPLETED
        project.completed_at = utc_now()
        project.progress_percent = 100
        self._record_activity(
            project.id,
            "project_completed",
            "Project completed after verification",
            commit=False,
        )
        self._session.commit()
        return project

    # --------------------------------------------------------------- progress
    def get_progress(self, project_id: UUID) -> ProjectProgress:
        project = self._require_project(project_id)
        return self._compute_progress(project)

    def list_activities(self, project_id: UUID) -> list[DeliveryActivity]:
        self._require_project(project_id)
        return list(
            self._session.scalars(
                select(DeliveryActivity)
                .where(DeliveryActivity.project_id == project_id)
                .order_by(DeliveryActivity.created_at.asc())
            )
        )

    # --------------------------------------------------------------- helpers
    def _assert_sensitive_executable(self, task: ProjectTask) -> None:
        if task.approval_id is None:
            raise ForbiddenError(
                "Sensitive delivery task requires approval before execution",
                details={"task_id": str(task.id), "task_key": task.task_key},
            )
        gate = self._approvals.evaluate_gate(
            ACTION_EXECUTE_SENSITIVE,
            approval_id=task.approval_id,
        )
        if not gate.may_execute:
            raise ForbiddenError(
                "Sensitive delivery task blocked by approval gate",
                details={
                    "decision": gate.decision,
                    "reason": gate.reason,
                    "approval_id": str(task.approval_id),
                },
            )
        approval = self._approvals.get_approval(task.approval_id)
        if approval.status != ApprovalStatus.APPROVED:
            raise ForbiddenError(
                "Sensitive delivery task requires an APPROVED approval",
                details={"status": approval.status.value},
            )

    def _dependencies_satisfied(self, task: ProjectTask) -> bool:
        deps = list(task.depends_on or [])
        if not deps:
            return True
        siblings = {
            t.task_key: t
            for t in self._session.scalars(
                select(ProjectTask).where(ProjectTask.project_id == task.project_id)
            )
        }
        for dep_key in deps:
            dep = siblings.get(dep_key)
            if dep is None:
                return False
            if _as_task_status(dep.status) != ProjectTaskStatus.COMPLETED or not dep.verified:
                return False
        return True

    def _compute_progress(self, project: DeliveryProject) -> ProjectProgress:
        tasks = list(
            self._session.scalars(
                select(ProjectTask).where(ProjectTask.project_id == project.id)
            )
        )
        total = len(tasks)
        completed = sum(
            1 for t in tasks if _as_task_status(t.status) == ProjectTaskStatus.COMPLETED
        )
        verified = sum(1 for t in tasks if t.verified)
        blocked = sum(
            1 for t in tasks if _as_task_status(t.status) == ProjectTaskStatus.BLOCKED
        )
        pending = sum(
            1 for t in tasks if _as_task_status(t.status) == ProjectTaskStatus.PENDING
        )
        deliverable_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(Deliverable)
                .where(Deliverable.project_id == project.id)
            )
            or 0
        )
        percent = int(round((completed / total) * 100)) if total else 0
        return ProjectProgress(
            project_id=project.id,
            status=str(
                project.status.value
                if isinstance(project.status, DeliveryProjectStatus)
                else project.status
            ),
            progress_percent=percent,
            total_tasks=total,
            completed_tasks=completed,
            verified_tasks=verified,
            blocked_tasks=blocked,
            pending_tasks=pending,
            deliverable_count=deliverable_count,
            verified=bool(project.verified),
            completed_at=project.completed_at,
        )

    def _refresh_progress(self, project: DeliveryProject) -> None:
        progress = self._compute_progress(project)
        project.progress_percent = progress.progress_percent

    def _record_activity(
        self,
        project_id: UUID,
        activity_type: str,
        message: str,
        *,
        task_id: UUID | None = None,
        actor: str = "delivery",
        commit: bool = True,
        metadata: dict | None = None,
    ) -> DeliveryActivity:
        row = DeliveryActivity(
            project_id=project_id,
            task_id=task_id,
            activity_type=activity_type,
            message=message,
            actor=actor,
            extra_metadata=dict(metadata or {}),
        )
        self._session.add(row)
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return row

    def _require_task(self, task_id: UUID) -> ProjectTask:
        task = self._session.get(ProjectTask, task_id)
        if task is None:
            raise ValidationAppError(
                "Task not found",
                details={"task_id": str(task_id)},
            )
        return task

    def _require_project(self, project_id: UUID) -> DeliveryProject:
        project = self._session.get(DeliveryProject, project_id)
        if project is None:
            raise ValidationAppError(
                "Project not found",
                details={"project_id": str(project_id)},
            )
        return project

    def _task_view(self, task: ProjectTask) -> TaskView:
        return TaskView(
            id=task.id,
            task_key=task.task_key,
            title=task.title,
            status=str(
                task.status.value if isinstance(task.status, ProjectTaskStatus) else task.status
            ),
            depends_on=list(task.depends_on or []),
            is_sensitive=bool(task.is_sensitive),
            verified=bool(task.verified),
            approval_id=task.approval_id,
        )

    def _bump_daily_customers(self) -> None:
        today = utc_now().date()
        row = self._session.scalar(
            select(DailyMetric).where(DailyMetric.metric_date == today)
        )
        if row is None:
            row = DailyMetric(metric_date=today)
            self._session.add(row)
            self._session.flush()
        row.customers = int(row.customers or 0) + 1

    def _find_by_idempotency_key(self, key: str) -> AgentRun | None:
        return self._session.scalar(
            select(AgentRun).where(
                AgentRun.idempotency_key == key,
                AgentRun.agent_name == AGENT_NAME,
            )
        )

    def _result_from_existing(self, run: AgentRun, *, logs: list[str]) -> DeliveryRunResult:
        project = self._session.scalar(
            select(DeliveryProject).where(DeliveryProject.agent_run_id == run.id).limit(1)
        )
        if project is None or run.status != AgentRunStatus.SUCCEEDED:
            return DeliveryRunResult(
                agent_run_id=run.id,
                status="failed" if run.status == AgentRunStatus.FAILED else "succeeded",
                estimated_cost=run.estimated_cost or Decimal("0"),
                idempotent_replay=True,
                error_message=run.error_message,
                logs=logs,
            )
        tasks = list(
            self._session.scalars(
                select(ProjectTask)
                .where(ProjectTask.project_id == project.id)
                .order_by(ProjectTask.sort_order.asc())
            )
        )
        return DeliveryRunResult(
            agent_run_id=run.id,
            status="succeeded",
            customer_id=project.customer_id,
            project_id=project.id,
            tasks=[self._task_view(t) for t in tasks],
            progress=self._compute_progress(project),
            estimated_cost=run.estimated_cost or Decimal("0"),
            idempotent_replay=True,
            logs=logs,
        )
