"""Add outreaches table for Sales Agent drafts.

Revision ID: 0007_sales_outreaches
Revises: 0006_approval_system
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_sales_outreaches"
down_revision: Union[str, None] = "0006_approval_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outreaches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("company_score_id", sa.Uuid(), nullable=True),
        sa.Column("company_audit_id", sa.Uuid(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outreach_version", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("cta", sa.String(length=500), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False, server_default="0"),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("personalization_reasons", sa.JSON(), nullable=False),
        sa.Column("evidence_used", sa.JSON(), nullable=False),
        sa.Column("evidence_catalog", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "drafted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_audit_id"], ["company_audits.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_score_id"], ["company_scores.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreaches_company_id", "outreaches", ["company_id"])
    op.create_index("ix_outreaches_lead_id", "outreaches", ["lead_id"])
    op.create_index("ix_outreaches_status", "outreaches", ["status"])
    op.create_index("ix_outreaches_agent_run_id", "outreaches", ["agent_run_id"])
    op.create_index("ix_outreaches_created_at", "outreaches", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_outreaches_created_at", table_name="outreaches")
    op.drop_index("ix_outreaches_agent_run_id", table_name="outreaches")
    op.drop_index("ix_outreaches_status", table_name="outreaches")
    op.drop_index("ix_outreaches_lead_id", table_name="outreaches")
    op.drop_index("ix_outreaches_company_id", table_name="outreaches")
    op.drop_table("outreaches")
