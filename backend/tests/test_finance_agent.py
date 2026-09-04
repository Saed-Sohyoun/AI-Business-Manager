"""Phase 14 — FinanceAgent and deterministic Decimal financial math."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.finance import (
    CostRecordRequest,
    FinanceAgent,
    FinanceCalculateRequest,
    RevenueRecordRequest,
)
from app.approvals import ApprovalService
from app.config import Settings
from app.finance.calculations import (
    as_decimal,
    cost_per_unit,
    customer_acquisition_cost,
    gross_profit,
    mrr_from_recurring,
    normalize_currency,
    quantize_money,
    roi,
    sum_amounts,
)
from app.models import FinancialMetric, RevenueEntry
from app.models.enums import CostCategory, RevenueType


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        approval_authorized_resolvers="owner,admin",
        max_single_expense=Decimal("10000"),
        daily_budget_limit=Decimal("100000"),
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def finance_env(db_session):
    cfg = _settings()
    approvals = ApprovalService(db_session, cfg)
    agent = FinanceAgent(session=db_session, settings=cfg, approval_service=approvals)
    return {"session": db_session, "settings": cfg, "agent": agent}


def _ts(days_offset: int = 0) -> datetime:
    return datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=days_offset)


# ---------------------------------------------------------------------------
# Pure calculation unit tests
# ---------------------------------------------------------------------------


def test_revenue_sum_and_quantize():
    assert sum_amounts([Decimal("10.00"), Decimal("2.50")]) == Decimal("12.500000")
    assert quantize_money(Decimal("1.2345674")) == Decimal("1.234567")
    assert quantize_money(Decimal("1.2345675")) == Decimal("1.234568")


def test_cost_and_profit():
    revenue = Decimal("100.00")
    costs = Decimal("40.00")
    assert gross_profit(revenue=revenue, costs=costs) == Decimal("60.000000")


def test_negative_values():
    # Refund / credit support
    assert gross_profit(revenue=Decimal("-10"), costs=Decimal("5")) == Decimal("-15.000000")
    assert sum_amounts([Decimal("-1.25"), Decimal("3.00")]) == Decimal("1.750000")
    assert roi(revenue=Decimal("50"), costs=Decimal("100")) == Decimal("-0.500000")


def test_rounding_half_up():
    assert quantize_money("0.0000014") == Decimal("0.000001")
    assert quantize_money("0.0000015") == Decimal("0.000002")
    assert cost_per_unit(total_costs=Decimal("10"), unit_count=3) == Decimal("3.333333")


def test_currency_normalization():
    assert normalize_currency("usd") == "USD"
    with pytest.raises(ValueError):
        normalize_currency("US")
    with pytest.raises(ValueError):
        normalize_currency("USDD")


def test_reject_float_amounts():
    with pytest.raises(TypeError, match="Floating-point"):
        as_decimal(1.23)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        CostRecordRequest(
            amount=1.5,  # type: ignore[arg-type]
            category=CostCategory.AI,
            source="test",
            idempotency_key="float-bad",
        )


def test_roi_and_unit_costs():
    assert roi(revenue=Decimal("150"), costs=Decimal("100")) == Decimal("0.500000")
    assert roi(revenue=Decimal("50"), costs=Decimal("0")) is None
    assert cost_per_unit(total_costs=Decimal("100"), unit_count=0) is None
    assert customer_acquisition_cost(total_costs=Decimal("200"), customer_count=4) == Decimal(
        "50.000000"
    )
    assert mrr_from_recurring([Decimal("99.00"), Decimal("49.00")]) == Decimal("148.000000")


# ---------------------------------------------------------------------------
# Agent / ledger integration tests
# ---------------------------------------------------------------------------


def test_record_revenue_and_cost(finance_env):
    agent = finance_env["agent"]
    rev = agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("500.00"),
            currency="USD",
            revenue_type=RevenueType.ONE_TIME,
            source="invoice",
            transaction_reference="INV-1",
            occurred_at=_ts(0),
            idempotency_key="rev-1",
            metadata={"channel": "stripe"},
        )
    )
    cost = agent.record_cost(
        CostRecordRequest(
            amount=Decimal("12.345678"),
            currency="usd",
            category=CostCategory.AI,
            source="openai",
            transaction_reference="ai-run-1",
            occurred_at=_ts(0),
            idempotency_key="cost-ai-1",
        )
    )
    assert rev.amount == Decimal("500.000000")
    assert rev.currency == "USD"
    assert rev.transaction_reference == "INV-1"
    assert cost.amount == Decimal("12.345678")
    assert cost.category == CostCategory.AI

    # Idempotent replay
    again = agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("999"),
            source="invoice",
            idempotency_key="rev-1",
        )
    )
    assert again.id == rev.id
    assert again.amount == Decimal("500.000000")


def test_aggregation_and_breakdown(finance_env):
    agent = finance_env["agent"]
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("1.00"),
            category=CostCategory.AI,
            source="ai",
            occurred_at=_ts(1),
            idempotency_key="c-ai",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("2.00"),
            category=CostCategory.SEARCH,
            source="tavily",
            occurred_at=_ts(1),
            idempotency_key="c-search",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("3.00"),
            category=CostCategory.EMAIL,
            source="resend",
            occurred_at=_ts(1),
            idempotency_key="c-email",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("4.00"),
            category=CostCategory.BROWSER,
            source="playwright",
            occurred_at=_ts(1),
            idempotency_key="c-browser",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("5.00"),
            category=CostCategory.DELIVERY,
            source="delivery",
            occurred_at=_ts(1),
            idempotency_key="c-delivery",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("6.00"),
            category=CostCategory.OTHER_OPERATIONAL,
            source="ops",
            occurred_at=_ts(1),
            idempotency_key="c-other",
        )
    )
    agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("100.00"),
            revenue_type=RevenueType.SUBSCRIPTION,
            is_recurring=True,
            source="billing",
            occurred_at=_ts(1),
            idempotency_key="r-sub",
        )
    )
    agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("50.00"),
            revenue_type=RevenueType.ONE_TIME,
            source="billing",
            occurred_at=_ts(1),
            idempotency_key="r-once",
        )
    )

    result = agent.run(
        FinanceCalculateRequest(
            period_start=_ts(0),
            period_end=_ts(2),
            currency="USD",
            lead_count=10,
            qualified_lead_count=5,
            customer_count=2,
            idempotency_key="fin-agg-1",
        )
    )
    assert result.status == "succeeded"
    assert result.metric is not None
    m = result.metric
    assert m.total_costs == Decimal("21.000000")
    assert m.total_revenue == Decimal("150.000000")
    assert m.gross_profit == Decimal("129.000000")
    assert m.mrr == Decimal("100.000000")
    assert m.cost_breakdown.ai == Decimal("1.000000")
    assert m.cost_breakdown.search == Decimal("2.000000")
    assert m.cost_breakdown.email == Decimal("3.000000")
    assert m.cost_breakdown.browser == Decimal("4.000000")
    assert m.cost_breakdown.delivery == Decimal("5.000000")
    assert m.cost_breakdown.other_operational == Decimal("6.000000")
    assert m.delivery_cost == Decimal("5.000000")
    assert m.cost_per_lead == Decimal("2.100000")
    assert m.cost_per_qualified_lead == Decimal("4.200000")
    assert m.customer_acquisition_cost == Decimal("10.500000")
    assert m.roi == Decimal("6.142857")  # 129/21


def test_roi_agent_path(finance_env):
    agent = finance_env["agent"]
    agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("200"),
            source="s",
            occurred_at=_ts(0),
            idempotency_key="roi-r",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("50"),
            category=CostCategory.OTHER_OPERATIONAL,
            source="s",
            occurred_at=_ts(0),
            idempotency_key="roi-c",
        )
    )
    result = agent.run(
        FinanceCalculateRequest(
            period_start=_ts(0),
            period_end=_ts(1),
            lead_count=0,
            customer_count=0,
            idempotency_key="roi-calc",
        )
    )
    assert result.metric is not None
    assert result.metric.roi == Decimal("3.000000")
    assert result.metric.cost_per_lead is None
    assert result.metric.customer_acquisition_cost is None


def test_currency_isolation(finance_env):
    agent = finance_env["agent"]
    agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("10"),
            currency="USD",
            source="s",
            occurred_at=_ts(0),
            idempotency_key="usd-r",
        )
    )
    agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("99"),
            currency="EUR",
            source="s",
            occurred_at=_ts(0),
            idempotency_key="eur-r",
        )
    )
    usd = agent.calculate_metrics(
        FinanceCalculateRequest(
            period_start=_ts(0),
            period_end=_ts(1),
            currency="USD",
            idempotency_key="usd-m",
        )
    )
    eur = agent.calculate_metrics(
        FinanceCalculateRequest(
            period_start=_ts(0),
            period_end=_ts(1),
            currency="EUR",
            idempotency_key="eur-m",
        )
    )
    assert usd.total_revenue == Decimal("10.000000")
    assert eur.total_revenue == Decimal("99.000000")


def test_negative_cost_credit(finance_env):
    agent = finance_env["agent"]
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("10.00"),
            category=CostCategory.EMAIL,
            source="resend",
            occurred_at=_ts(0),
            idempotency_key="email-charge",
        )
    )
    agent.record_cost(
        CostRecordRequest(
            amount=Decimal("-2.50"),
            category=CostCategory.EMAIL,
            source="resend",
            transaction_reference="credit-1",
            occurred_at=_ts(0),
            idempotency_key="email-credit",
            description="provider credit",
        )
    )
    metric = agent.calculate_metrics(
        FinanceCalculateRequest(
            period_start=_ts(0),
            period_end=_ts(1),
            idempotency_key="neg-m",
        )
    )
    assert metric.email_costs == Decimal("7.500000")
    assert metric.total_costs == Decimal("7.500000")


def test_persisted_metric_has_timestamps_and_source(finance_env):
    from sqlalchemy import select

    agent = finance_env["agent"]
    agent.record_revenue(
        RevenueRecordRequest(
            amount=Decimal("1"),
            source="manual",
            occurred_at=_ts(0),
            idempotency_key="meta-r",
            metadata={"note": "seed"},
        )
    )
    result = agent.run(
        FinanceCalculateRequest(
            period_start=_ts(0),
            period_end=_ts(1),
            idempotency_key="meta-run",
        )
    )
    row = finance_env["session"].get(FinancialMetric, result.metric.id)
    assert row.source == "finance_agent"
    assert row.calculated_at is not None
    assert row.created_at is not None
    assert row.extra_metadata.get("calculation") == "deterministic_decimal"
    revenues = list(finance_env["session"].scalars(select(RevenueEntry)))
    assert revenues[0].source == "manual"
    assert revenues[0].extra_metadata.get("note") == "seed"
