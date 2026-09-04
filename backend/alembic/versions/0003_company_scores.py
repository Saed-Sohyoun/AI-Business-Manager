"""Add company_scores table for deterministic lead scoring.

Revision ID: 0003_company_scores
Revises: 0002_research_memory
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_company_scores"
down_revision: Union[str, None] = "0002_research_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(length=32), nullable=False),
        sa.Column("website_quality", sa.Integer(), nullable=False),
        sa.Column("online_presence", sa.Integer(), nullable=False),
        sa.Column("lead_capture_process", sa.Integer(), nullable=False),
        sa.Column("automation_potential", sa.Integer(), nullable=False),
        sa.Column("commercial_potential", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("scoring_version", sa.String(length=32), nullable=False),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_scores_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_scores")),
    )
    op.create_index("ix_company_scores_band", "company_scores", ["band"])
    op.create_index("ix_company_scores_company_id", "company_scores", ["company_id"])
    op.create_index("ix_company_scores_scored_at", "company_scores", ["scored_at"])
    op.create_index("ix_company_scores_version", "company_scores", ["scoring_version"])


def downgrade() -> None:
    op.drop_index("ix_company_scores_version", table_name="company_scores")
    op.drop_index("ix_company_scores_scored_at", table_name="company_scores")
    op.drop_index("ix_company_scores_company_id", table_name="company_scores")
    op.drop_index("ix_company_scores_band", table_name="company_scores")
    op.drop_table("company_scores")
