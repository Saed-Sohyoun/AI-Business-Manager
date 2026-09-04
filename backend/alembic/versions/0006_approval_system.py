"""Expand approvals for fingerprint, expiry, payload, audit events.

Revision ID: 0006_approval_system
Revises: 0005_manager_orchestration
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_approval_system"
down_revision: Union[str, None] = "0005_manager_orchestration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("approvals") as batch:
        batch.add_column(sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""))
        batch.add_column(sa.Column("action_payload", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("resolution_note", sa.Text(), nullable=True))
        batch.add_column(sa.Column("manager_run_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("manager_task_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("agent_run_id", sa.Uuid(), nullable=True))
        batch.create_index("ix_approvals_fingerprint", ["fingerprint"], unique=False)
        batch.create_index("ix_approvals_expires_at", ["expires_at"], unique=False)
        batch.create_foreign_key(
            "fk_approvals_agent_run_id_agent_runs",
            "agent_runs",
            ["agent_run_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "approval_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_events_approval_id", "approval_events", ["approval_id"])
    op.create_index("ix_approval_events_event_type", "approval_events", ["event_type"])
    op.create_index("ix_approval_events_created_at", "approval_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_approval_events_created_at", table_name="approval_events")
    op.drop_index("ix_approval_events_event_type", table_name="approval_events")
    op.drop_index("ix_approval_events_approval_id", table_name="approval_events")
    op.drop_table("approval_events")

    with op.batch_alter_table("approvals") as batch:
        batch.drop_constraint("fk_approvals_agent_run_id_agent_runs", type_="foreignkey")
        batch.drop_index("ix_approvals_expires_at")
        batch.drop_index("ix_approvals_fingerprint")
        batch.drop_column("agent_run_id")
        batch.drop_column("manager_task_id")
        batch.drop_column("manager_run_id")
        batch.drop_column("resolution_note")
        batch.drop_column("expires_at")
        batch.drop_column("action_payload")
        batch.drop_column("fingerprint")
