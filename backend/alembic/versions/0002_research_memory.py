"""Add research provenance: website_domain, sources, evidence, idempotency_key.

Revision ID: 0002_research_memory
Revises: 0001_initial_schema
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_research_memory"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("website_domain", sa.String(length=255), nullable=True))
        batch.create_index("ix_companies_website_domain", ["website_domain"], unique=False)
        batch.create_unique_constraint("uq_companies_website_domain", ["website_domain"])

    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint("uq_agent_runs_idempotency_key", ["idempotency_key"])

    op.create_table(
        "company_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
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
            name=op.f("fk_company_sources_agent_run_id_agent_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_sources_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_sources")),
        sa.UniqueConstraint(
            "company_id",
            "normalized_url",
            name="uq_company_sources_company_id_normalized_url",
        ),
    )
    op.create_index("ix_company_sources_agent_run_id", "company_sources", ["agent_run_id"])
    op.create_index("ix_company_sources_company_id", "company_sources", ["company_id"])

    op.create_table(
        "company_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("field_value", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
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
            name=op.f("fk_company_evidence_agent_run_id_agent_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_evidence_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_evidence")),
    )
    op.create_index("ix_company_evidence_agent_run_id", "company_evidence", ["agent_run_id"])
    op.create_index("ix_company_evidence_company_id", "company_evidence", ["company_id"])
    op.create_index("ix_company_evidence_field_name", "company_evidence", ["field_name"])


def downgrade() -> None:
    op.drop_index("ix_company_evidence_field_name", table_name="company_evidence")
    op.drop_index("ix_company_evidence_company_id", table_name="company_evidence")
    op.drop_index("ix_company_evidence_agent_run_id", table_name="company_evidence")
    op.drop_table("company_evidence")

    op.drop_index("ix_company_sources_company_id", table_name="company_sources")
    op.drop_index("ix_company_sources_agent_run_id", table_name="company_sources")
    op.drop_table("company_sources")

    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("uq_agent_runs_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")

    with op.batch_alter_table("companies") as batch:
        batch.drop_constraint("uq_companies_website_domain", type_="unique")
        batch.drop_index("ix_companies_website_domain")
        batch.drop_column("website_domain")
