"""Add follow-up sequences/items and lead engagement flags.

Revision ID: 0009_follow_ups
Revises: 0008_outbound_messages
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_follow_ups"
down_revision: Union[str, None] = "0008_outbound_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("opted_out", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "leads",
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "leads",
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "follow_up_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("initial_outreach_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("initial_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("follow_up_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("response_received", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_to_followup_index", sa.Integer(), nullable=True),
        sa.Column("meetings_generated", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initial_outreach_id"], ["outreaches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_follow_up_sequences_idempotency_key"),
        sa.UniqueConstraint("lead_id", name="uq_follow_up_sequences_lead_id"),
    )
    op.create_index("ix_follow_up_sequences_status", "follow_up_sequences", ["status"])
    op.create_index(
        "ix_follow_up_sequences_next_follow_up_at",
        "follow_up_sequences",
        ["next_follow_up_at"],
    )
    op.create_index("ix_follow_up_sequences_company_id", "follow_up_sequences", ["company_id"])
    op.create_index(
        "ix_follow_up_sequences_initial_outreach_id",
        "follow_up_sequences",
        ["initial_outreach_id"],
    )

    op.create_table(
        "follow_up_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("followup_index", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("outreach_id", sa.Uuid(), nullable=True),
        sa.Column("outbound_message_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("skip_reason", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["outbound_message_id"],
            ["outbound_messages.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["outreach_id"], ["outreaches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["sequence_id"],
            ["follow_up_sequences.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_follow_up_items_idempotency_key"),
        sa.UniqueConstraint(
            "sequence_id",
            "followup_index",
            name="uq_follow_up_items_sequence_id_followup_index",
        ),
    )
    op.create_index("ix_follow_up_items_status", "follow_up_items", ["status"])
    op.create_index("ix_follow_up_items_scheduled_for", "follow_up_items", ["scheduled_for"])
    op.create_index("ix_follow_up_items_sequence_id", "follow_up_items", ["sequence_id"])
    op.create_index("ix_follow_up_items_outreach_id", "follow_up_items", ["outreach_id"])


def downgrade() -> None:
    op.drop_index("ix_follow_up_items_outreach_id", table_name="follow_up_items")
    op.drop_index("ix_follow_up_items_sequence_id", table_name="follow_up_items")
    op.drop_index("ix_follow_up_items_scheduled_for", table_name="follow_up_items")
    op.drop_index("ix_follow_up_items_status", table_name="follow_up_items")
    op.drop_table("follow_up_items")

    op.drop_index(
        "ix_follow_up_sequences_initial_outreach_id",
        table_name="follow_up_sequences",
    )
    op.drop_index("ix_follow_up_sequences_company_id", table_name="follow_up_sequences")
    op.drop_index(
        "ix_follow_up_sequences_next_follow_up_at",
        table_name="follow_up_sequences",
    )
    op.drop_index("ix_follow_up_sequences_status", table_name="follow_up_sequences")
    op.drop_table("follow_up_sequences")

    op.drop_column("leads", "last_contacted_at")
    op.drop_column("leads", "replied_at")
    op.drop_column("leads", "blocked")
    op.drop_column("leads", "opted_out")
