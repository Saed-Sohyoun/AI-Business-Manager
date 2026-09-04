"""Add business_reports table for ReportAgent.

Revision ID: 0012_business_reports
Revises: 0011_finance_ledger
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_business_reports"
down_revision: Union[str, None] = "0011_finance_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("facts_snapshot", sa.JSON(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_business_reports_idempotency_key"),
    )
    op.create_index("ix_business_reports_period_type", "business_reports", ["period_type"])
    op.create_index("ix_business_reports_period_start", "business_reports", ["period_start"])
    op.create_index("ix_business_reports_period_end", "business_reports", ["period_end"])
    op.create_index("ix_business_reports_status", "business_reports", ["status"])
    op.create_index("ix_business_reports_generated_at", "business_reports", ["generated_at"])


def downgrade() -> None:
    op.drop_index("ix_business_reports_generated_at", table_name="business_reports")
    op.drop_index("ix_business_reports_status", table_name="business_reports")
    op.drop_index("ix_business_reports_period_end", table_name="business_reports")
    op.drop_index("ix_business_reports_period_start", table_name="business_reports")
    op.drop_index("ix_business_reports_period_type", table_name="business_reports")
    op.drop_table("business_reports")
