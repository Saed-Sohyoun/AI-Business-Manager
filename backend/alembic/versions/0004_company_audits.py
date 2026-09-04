"""Add company_audits table for Audit Agent.

Revision ID: 0004_company_audits
Revises: 0003_company_scores
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_company_audits"
down_revision: Union[str, None] = "0003_company_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("audit_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommended_solution", sa.Text(), nullable=True),
        sa.Column("website_available", sa.Boolean(), nullable=False),
        sa.Column("estimated_business_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("estimated_business_value_currency", sa.String(length=8), nullable=True),
        sa.Column("estimated_business_value_rationale", sa.Text(), nullable=True),
        sa.Column("problems", sa.JSON(), nullable=False),
        sa.Column("opportunities", sa.JSON(), nullable=False),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("observations", sa.JSON(), nullable=False),
        sa.Column("evidence_catalog", sa.JSON(), nullable=False),
        sa.Column(
            "audited_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_company_audits_agent_run_id_agent_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_audits_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_audits")),
    )
    op.create_index("ix_company_audits_agent_run_id", "company_audits", ["agent_run_id"])
    op.create_index("ix_company_audits_audited_at", "company_audits", ["audited_at"])
    op.create_index("ix_company_audits_company_id", "company_audits", ["company_id"])
    op.create_index("ix_company_audits_priority", "company_audits", ["priority"])
    op.create_index("ix_company_audits_status", "company_audits", ["status"])
    op.create_index("ix_company_audits_version", "company_audits", ["audit_version"])


def downgrade() -> None:
    op.drop_index("ix_company_audits_version", table_name="company_audits")
    op.drop_index("ix_company_audits_status", table_name="company_audits")
    op.drop_index("ix_company_audits_priority", table_name="company_audits")
    op.drop_index("ix_company_audits_company_id", table_name="company_audits")
    op.drop_index("ix_company_audits_audited_at", table_name="company_audits")
    op.drop_index("ix_company_audits_agent_run_id", table_name="company_audits")
    op.drop_table("company_audits")
