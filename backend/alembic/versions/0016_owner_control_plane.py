"""Wave 2 — system_control_state + owner_alerts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_owner_control_plane"
down_revision = "0015_security_events_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_control_state",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("control_key", sa.String(length=64), server_default="default", nullable=False),
        sa.Column("system_mode", sa.String(length=32), server_default="normal", nullable=False),
        sa.Column("ai_operations_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("outbound_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("spending_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("browser_automation_enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("safe_mode_reason", sa.Text(), nullable=True),
        sa.Column("safe_mode_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_by", sa.String(length=128), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("last_changed_by", sa.String(length=128), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_control_state_key", "system_control_state", ["control_key"], unique=True)

    op.create_table(
        "owner_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dedupe_key", sa.String(length=191), nullable=False),
        sa.Column("priority", sa.String(length=32), server_default="info", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), server_default="system", nullable=False),
        sa.Column("acknowledged", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_owner_alerts_dedupe_key"),
    )
    op.create_index("ix_owner_alerts_priority", "owner_alerts", ["priority"])
    op.create_index("ix_owner_alerts_acknowledged", "owner_alerts", ["acknowledged"])
    op.create_index("ix_owner_alerts_created_at", "owner_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_owner_alerts_created_at", table_name="owner_alerts")
    op.drop_index("ix_owner_alerts_acknowledged", table_name="owner_alerts")
    op.drop_index("ix_owner_alerts_priority", table_name="owner_alerts")
    op.drop_table("owner_alerts")
    op.drop_index("ix_system_control_state_key", table_name="system_control_state")
    op.drop_table("system_control_state")
