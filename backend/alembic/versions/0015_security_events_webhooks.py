"""Wave 1 — security_events + webhook_nonces for governance/replay protection."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_security_events_webhooks"
down_revision = "0014_workflow_executions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=True),
        sa.Column("tool", sa.String(length=64), nullable=True),
        sa.Column("target", sa.String(length=512), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("contract_version", sa.String(length=32), nullable=True),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_agent_id", "security_events", ["agent_id"])
    op.create_index("ix_security_events_created_at", "security_events", ["created_at"])
    op.create_index("ix_security_events_execution_id", "security_events", ["execution_id"])

    op.create_table(
        "webhook_nonces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("signature_prefix", sa.String(length=16), server_default="", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "nonce", name="uq_webhook_nonces_source_nonce"),
    )
    op.create_index("ix_webhook_nonces_expires_at", "webhook_nonces", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_nonces_expires_at", table_name="webhook_nonces")
    op.drop_table("webhook_nonces")
    op.drop_index("ix_security_events_execution_id", table_name="security_events")
    op.drop_index("ix_security_events_created_at", table_name="security_events")
    op.drop_index("ix_security_events_agent_id", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_table("security_events")
