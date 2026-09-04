"""Add notification_records table.

Revision ID: 0013_notifications
Revises: 0012_business_reports
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_notifications"
down_revision: Union[str, None] = "0012_business_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_notification_records_idempotency_key",
        ),
    )
    op.create_index("ix_notification_records_status", "notification_records", ["status"])
    op.create_index("ix_notification_records_priority", "notification_records", ["priority"])
    op.create_index("ix_notification_records_category", "notification_records", ["category"])
    op.create_index("ix_notification_records_created_at", "notification_records", ["created_at"])
    op.create_index("ix_notification_records_sent_at", "notification_records", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_records_sent_at", table_name="notification_records")
    op.drop_index("ix_notification_records_created_at", table_name="notification_records")
    op.drop_index("ix_notification_records_category", table_name="notification_records")
    op.drop_index("ix_notification_records_priority", table_name="notification_records")
    op.drop_index("ix_notification_records_status", table_name="notification_records")
    op.drop_table("notification_records")
