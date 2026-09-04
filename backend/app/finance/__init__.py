"""Finance calculation package — deterministic Decimal math only."""

from app.finance.calculations import (
    MONEY_QUANTUM,
    ZERO,
    as_decimal,
    cost_per_unit,
    customer_acquisition_cost,
    gross_profit,
    mrr_from_recurring,
    normalize_currency,
    quantize_money,
    roi,
    sum_amounts,
    sum_by_category,
    total_costs_from_breakdown,
)

__all__ = [
    "MONEY_QUANTUM",
    "ZERO",
    "as_decimal",
    "cost_per_unit",
    "customer_acquisition_cost",
    "gross_profit",
    "mrr_from_recurring",
    "normalize_currency",
    "quantize_money",
    "roi",
    "sum_amounts",
    "sum_by_category",
    "total_costs_from_breakdown",
]
