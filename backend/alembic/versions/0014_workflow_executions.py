"""Add workflow_executions table for n8n orchestration tracking.

Revision ID: 0014_workflow_executions
Revises: 0013_notifications
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_workflow_executions"
down_revision: Union[str, None] = "0013_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_name", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_source", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_workflow_executions_agent_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_name",
            "idempotency_key",
            name="uq_workflow_executions_name_idempotency",
        ),
    )
    op.create_index(
        "ix_workflow_executions_workflow_name",
        "workflow_executions",
        ["workflow_name"],
    )
    op.create_index("ix_workflow_executions_status", "workflow_executions", ["status"])
    op.create_index(
        "ix_workflow_executions_started_at",
        "workflow_executions",
        ["started_at"],
    )
    op.create_index(
        "ix_workflow_executions_idempotency_key",
        "workflow_executions",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_executions_idempotency_key",
        table_name="workflow_executions",
    )
    op.drop_index("ix_workflow_executions_started_at", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_status", table_name="workflow_executions")
    op.drop_index(
        "ix_workflow_executions_workflow_name",
        table_name="workflow_executions",
    )
    op.drop_table("workflow_executions")
