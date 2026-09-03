"""Initial schema for core business entities.

Revision ID: 20260903_0001
Revises:
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("industry", sa.String(length=50), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
    )
    op.create_index("ix_companies_website_url", "companies", ["website_url"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("website_quality_score", sa.Integer(), nullable=True),
        sa.Column("online_presence_score", sa.Integer(), nullable=True),
        sa.Column("lead_capture_score", sa.Integer(), nullable=True),
        sa.Column("automation_potential_score", sa.Integer(), nullable=True),
        sa.Column("commercial_potential_score", sa.Integer(), nullable=True),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "website_quality_score IS NULL OR (website_quality_score >= 0 AND website_quality_score <= 20)",
            name="ck_leads_website_quality_range",
        ),
        sa.CheckConstraint(
            "online_presence_score IS NULL OR (online_presence_score >= 0 AND online_presence_score <= 20)",
            name="ck_leads_online_presence_range",
        ),
        sa.CheckConstraint(
            "lead_capture_score IS NULL OR (lead_capture_score >= 0 AND lead_capture_score <= 20)",
            name="ck_leads_lead_capture_range",
        ),
        sa.CheckConstraint(
            "automation_potential_score IS NULL OR (automation_potential_score >= 0 AND automation_potential_score <= 20)",
            name="ck_leads_automation_potential_range",
        ),
        sa.CheckConstraint(
            "commercial_potential_score IS NULL OR (commercial_potential_score >= 0 AND commercial_potential_score <= 20)",
            name="ck_leads_commercial_potential_range",
        ),
        sa.CheckConstraint(
            "total_score IS NULL OR (total_score >= 0 AND total_score <= 100)",
            name="ck_leads_total_score_range",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_leads_company_id_companies", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
    )
    op.create_index("ix_leads_company_id", "leads", ["company_id"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_total_score", "leads", ["total_score"])

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_customers_company_id_companies", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name="fk_customers_lead_id_leads", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.UniqueConstraint("lead_id", name="uq_customers_lead_id"),
    )
    op.create_index("ix_customers_company_id", "customers", ["company_id"])
    op.create_index("ix_customers_status", "customers", ["status"])

    op.create_table(
        "delivery_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_delivery_projects_customer_id_customers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_delivery_projects"),
    )
    op.create_index("ix_delivery_projects_customer_id", "delivery_projects", ["customer_id"])
    op.create_index("ix_delivery_projects_status", "delivery_projects", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_name", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_agent_runs_company_id_companies", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name="fk_agent_runs_lead_id_leads", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_agent_runs_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_agent_runs_idempotency_key"),
    )
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("delivery_project_id", sa.Uuid(), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["delivery_project_id"],
            ["delivery_projects.id"],
            name="fk_tasks_delivery_project_id_delivery_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_tasks_agent_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_delivery_project_id", "tasks", ["delivery_project_id"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("requested_by_agent", sa.String(length=50), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], name="fk_approvals_agent_run_id_agent_runs", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name="fk_approvals_lead_id_leads", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_approvals_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_approvals"),
        sa.UniqueConstraint("idempotency_key", name="uq_approvals_idempotency_key"),
    )
    op.create_index("ix_approvals_approval_type", "approvals", ["approval_type"])
    op.create_index("ix_approvals_status", "approvals", ["status"])

    op.create_table(
        "cost_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("incurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], name="fk_cost_entries_agent_run_id_agent_runs", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_cost_entries_customer_id_customers", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_cost_entries"),
    )
    op.create_index("ix_cost_entries_category", "cost_entries", ["category"])

    op.create_table(
        "revenue_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("delivery_project_id", sa.Uuid(), nullable=True),
        sa.Column("recognized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_revenue_entries_customer_id_customers", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["delivery_project_id"],
            ["delivery_projects.id"],
            name="fk_revenue_entries_delivery_project_id_delivery_projects",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_revenue_entries"),
    )
    op.create_index("ix_revenue_entries_customer_id", "revenue_entries", ["customer_id"])

    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("leads_created", sa.Integer(), nullable=False),
        sa.Column("leads_scored", sa.Integer(), nullable=False),
        sa.Column("outreach_sent", sa.Integer(), nullable=False),
        sa.Column("approvals_pending", sa.Integer(), nullable=False),
        sa.Column("new_customers", sa.Integer(), nullable=False),
        sa.Column("revenue_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_daily_metrics"),
        sa.UniqueConstraint("metric_date", name="uq_daily_metrics_metric_date"),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
    )
    op.create_index("ix_reports_report_type", "reports", ["report_type"])

    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_experiments"),
        sa.UniqueConstraint("name", name="uq_experiments_name"),
    )
    op.create_index("ix_experiments_status", "experiments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_table("experiments")
    op.drop_index("ix_reports_report_type", table_name="reports")
    op.drop_table("reports")
    op.drop_table("daily_metrics")
    op.drop_index("ix_revenue_entries_customer_id", table_name="revenue_entries")
    op.drop_table("revenue_entries")
    op.drop_index("ix_cost_entries_category", table_name="cost_entries")
    op.drop_table("cost_entries")
    op.drop_index("ix_approvals_status", table_name="approvals")
    op.drop_index("ix_approvals_approval_type", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_tasks_delivery_project_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_agent_name", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_delivery_projects_status", table_name="delivery_projects")
    op.drop_index("ix_delivery_projects_customer_id", table_name="delivery_projects")
    op.drop_table("delivery_projects")
    op.drop_index("ix_customers_status", table_name="customers")
    op.drop_index("ix_customers_company_id", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_leads_total_score", table_name="leads")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_company_id", table_name="leads")
    op.drop_table("leads")
    op.drop_index("ix_companies_website_url", table_name="companies")
    op.drop_table("companies")
