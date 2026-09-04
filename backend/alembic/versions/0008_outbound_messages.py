"""Add outbound_messages table for email send ledger.

Revision ID: 0008_outbound_messages
Revises: 0007_sales_outreaches
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_outbound_messages"
down_revision: Union[str, None] = "0007_sales_outreaches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("outreach_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("to_email", sa.String(length=320), nullable=False),
        sa.Column("to_name", sa.String(length=255), nullable=True),
        sa.Column("from_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("delivery_status", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_followup", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("followup_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sending_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["outreach_id"], ["outreaches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_outbound_messages_idempotency_key"),
    )
    op.create_index("ix_outbound_messages_status", "outbound_messages", ["status"])
    op.create_index("ix_outbound_messages_to_email", "outbound_messages", ["to_email"])
    op.create_index("ix_outbound_messages_outreach_id", "outbound_messages", ["outreach_id"])
    op.create_index("ix_outbound_messages_lead_id", "outbound_messages", ["lead_id"])
    op.create_index("ix_outbound_messages_sent_at", "outbound_messages", ["sent_at"])
    op.create_index("ix_outbound_messages_created_at", "outbound_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbound_messages_created_at", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_sent_at", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_lead_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_outreach_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_to_email", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_status", table_name="outbound_messages")
    op.drop_table("outbound_messages")
