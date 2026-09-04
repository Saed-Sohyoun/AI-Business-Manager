"""Wave 4 — owners, sessions, owner_executions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_wave4_production_readiness"
down_revision = "0016_owner_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_owner_accounts_email"),
    )
    op.create_index("ix_owner_accounts_email", "owner_accounts", ["email"])

    op.create_table(
        "owner_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_hint", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_owner_sessions_token_hash", "owner_sessions", ["token_hash"], unique=True)
    op.create_index("ix_owner_sessions_owner_id", "owner_sessions", ["owner_id"])
    op.create_index("ix_owner_sessions_expires_at", "owner_sessions", ["expires_at"])

    op.create_table(
        "owner_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("command_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_steps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_steps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_activity", sa.String(length=255), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("needs_attention", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("manager_run_id", sa.Uuid(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_type", "idempotency_key", name="uq_owner_executions_cmd_idem"),
    )
    op.create_index("ix_owner_executions_status", "owner_executions", ["status"])
    op.create_index("ix_owner_executions_started_at", "owner_executions", ["started_at"])
    op.create_index("ix_owner_executions_command_type", "owner_executions", ["command_type"])


def downgrade() -> None:
    op.drop_index("ix_owner_executions_command_type", table_name="owner_executions")
    op.drop_index("ix_owner_executions_started_at", table_name="owner_executions")
    op.drop_index("ix_owner_executions_status", table_name="owner_executions")
    op.drop_table("owner_executions")
    op.drop_index("ix_owner_sessions_expires_at", table_name="owner_sessions")
    op.drop_index("ix_owner_sessions_owner_id", table_name="owner_sessions")
    op.drop_index("ix_owner_sessions_token_hash", table_name="owner_sessions")
    op.drop_table("owner_sessions")
    op.drop_index("ix_owner_accounts_email", table_name="owner_accounts")
    op.drop_table("owner_accounts")
