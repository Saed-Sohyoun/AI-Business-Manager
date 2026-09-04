"""Wave 5 — pilot_experiments table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_wave5_pilot_experiment"
down_revision = "0017_wave4_production_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pilot_experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("niche", sa.String(length=255), nullable=False),
        sa.Column("geography", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=32), nullable=False, server_default="en"),
        sa.Column("company_count_cap", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("qualification_threshold", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("audit_cap", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("outreach_cap", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "daily_budget",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
            server_default="3.0000",
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success_criteria", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column(
            "owner_approved_niche",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pilot_experiments_status", "pilot_experiments", ["status"])
    op.create_index("ix_pilot_experiments_start_at", "pilot_experiments", ["start_at"])


def downgrade() -> None:
    op.drop_index("ix_pilot_experiments_start_at", table_name="pilot_experiments")
    op.drop_index("ix_pilot_experiments_status", table_name="pilot_experiments")
    op.drop_table("pilot_experiments")
