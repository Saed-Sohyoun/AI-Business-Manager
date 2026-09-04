"""Add manager orchestration tables: runs, tasks, decisions.

Revision ID: 0005_manager_orchestration
Revises: 0004_company_audits
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_manager_orchestration"
down_revision: Union[str, None] = "0004_company_audits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manager_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("plan_summary", sa.Text(), nullable=True),
        sa.Column("stop_reason", sa.String(length=128), nullable=True),
        sa.Column("target_qualified_leads", sa.Integer(), nullable=True),
        sa.Column("measured_qualified_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_state", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manager_runs_status", "manager_runs", ["status"])
    op.create_index("ix_manager_runs_started_at", "manager_runs", ["started_at"])
    op.create_index("ix_manager_runs_agent_run_id", "manager_runs", ["agent_run_id"])

    op.create_table(
        "manager_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("manager_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manager_run_id"], ["manager_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manager_run_id", "fingerprint", name="uq_manager_tasks_run_fingerprint"),
    )
    op.create_index("ix_manager_tasks_manager_run_id", "manager_tasks", ["manager_run_id"])
    op.create_index("ix_manager_tasks_status", "manager_tasks", ["status"])
    op.create_index("ix_manager_tasks_agent_name", "manager_tasks", ["agent_name"])

    op.create_table(
        "manager_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("manager_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("decision_type", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["manager_run_id"], ["manager_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["manager_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manager_decisions_manager_run_id", "manager_decisions", ["manager_run_id"])
    op.create_index("ix_manager_decisions_decision_type", "manager_decisions", ["decision_type"])
    op.create_index("ix_manager_decisions_created_at", "manager_decisions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_manager_decisions_created_at", table_name="manager_decisions")
    op.drop_index("ix_manager_decisions_decision_type", table_name="manager_decisions")
    op.drop_index("ix_manager_decisions_manager_run_id", table_name="manager_decisions")
    op.drop_table("manager_decisions")

    op.drop_index("ix_manager_tasks_agent_name", table_name="manager_tasks")
    op.drop_index("ix_manager_tasks_status", table_name="manager_tasks")
    op.drop_index("ix_manager_tasks_manager_run_id", table_name="manager_tasks")
    op.drop_table("manager_tasks")

    op.drop_index("ix_manager_runs_agent_run_id", table_name="manager_runs")
    op.drop_index("ix_manager_runs_started_at", table_name="manager_runs")
    op.drop_index("ix_manager_runs_status", table_name="manager_runs")
    op.drop_table("manager_runs")
