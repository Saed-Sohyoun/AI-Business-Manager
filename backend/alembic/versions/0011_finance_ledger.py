"""Add finance ledger tables.

Revision ID: 0011_finance_ledger
Revises: 0010_delivery_system
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_finance_ledger"
down_revision: Union[str, None] = "0010_delivery_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cost_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("transaction_reference", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
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
        sa.UniqueConstraint("idempotency_key", name="uq_cost_entries_idempotency_key"),
    )
    op.create_index("ix_cost_entries_category", "cost_entries", ["category"])
    op.create_index("ix_cost_entries_currency", "cost_entries", ["currency"])
    op.create_index("ix_cost_entries_occurred_at", "cost_entries", ["occurred_at"])
    op.create_index("ix_cost_entries_source", "cost_entries", ["source"])
    op.create_index(
        "ix_cost_entries_transaction_reference",
        "cost_entries",
        ["transaction_reference"],
    )

    op.create_table(
        "revenue_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("revenue_type", sa.String(length=32), nullable=False),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("transaction_reference", sa.String(length=128), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
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
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_revenue_entries_idempotency_key"),
    )
    op.create_index("ix_revenue_entries_revenue_type", "revenue_entries", ["revenue_type"])
    op.create_index("ix_revenue_entries_currency", "revenue_entries", ["currency"])
    op.create_index("ix_revenue_entries_occurred_at", "revenue_entries", ["occurred_at"])
    op.create_index("ix_revenue_entries_source", "revenue_entries", ["source"])
    op.create_index(
        "ix_revenue_entries_transaction_reference",
        "revenue_entries",
        ["transaction_reference"],
    )
    op.create_index("ix_revenue_entries_customer_id", "revenue_entries", ["customer_id"])

    op.create_table(
        "financial_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("total_revenue", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("total_costs", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("gross_profit", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("mrr", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("ai_costs", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("search_costs", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("email_costs", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("browser_costs", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("delivery_costs", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column(
            "other_operational_costs",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
        ),
        sa.Column("lead_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qualified_lead_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_per_lead", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column(
            "cost_per_qualified_lead",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "customer_acquisition_cost",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column("delivery_cost", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("roi", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
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
        sa.UniqueConstraint("idempotency_key", name="uq_financial_metrics_idempotency_key"),
    )
    op.create_index("ix_financial_metrics_currency", "financial_metrics", ["currency"])
    op.create_index("ix_financial_metrics_period_start", "financial_metrics", ["period_start"])
    op.create_index("ix_financial_metrics_period_end", "financial_metrics", ["period_end"])
    op.create_index(
        "ix_financial_metrics_calculated_at",
        "financial_metrics",
        ["calculated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_financial_metrics_calculated_at", table_name="financial_metrics")
    op.drop_index("ix_financial_metrics_period_end", table_name="financial_metrics")
    op.drop_index("ix_financial_metrics_period_start", table_name="financial_metrics")
    op.drop_index("ix_financial_metrics_currency", table_name="financial_metrics")
    op.drop_table("financial_metrics")

    op.drop_index("ix_revenue_entries_customer_id", table_name="revenue_entries")
    op.drop_index("ix_revenue_entries_transaction_reference", table_name="revenue_entries")
    op.drop_index("ix_revenue_entries_source", table_name="revenue_entries")
    op.drop_index("ix_revenue_entries_occurred_at", table_name="revenue_entries")
    op.drop_index("ix_revenue_entries_currency", table_name="revenue_entries")
    op.drop_index("ix_revenue_entries_revenue_type", table_name="revenue_entries")
    op.drop_table("revenue_entries")

    op.drop_index("ix_cost_entries_transaction_reference", table_name="cost_entries")
    op.drop_index("ix_cost_entries_source", table_name="cost_entries")
    op.drop_index("ix_cost_entries_occurred_at", table_name="cost_entries")
    op.drop_index("ix_cost_entries_currency", table_name="cost_entries")
    op.drop_index("ix_cost_entries_category", table_name="cost_entries")
    op.drop_table("cost_entries")
