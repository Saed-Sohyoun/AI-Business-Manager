"""Deterministic financial arithmetic — Decimal only, never float, never AI."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

from app.models.enums import CostCategory

# Internal ledger precision (matches Numeric(18, 6)).
MONEY_QUANTUM = Decimal("0.000001")
ZERO = Decimal("0")


def as_decimal(value: Decimal | int | str) -> Decimal:
    """Coerce to Decimal. Rejects float explicitly."""
    if isinstance(value, float):
        raise TypeError("Floating-point values are not allowed for financial amounts")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid decimal string: {value!r}") from exc
    raise TypeError(f"Unsupported financial type: {type(value).__name__}")


def quantize_money(value: Decimal | int | str) -> Decimal:
    """Round half-up to ledger precision."""
    return as_decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def normalize_currency(code: str) -> str:
    cleaned = (code or "").strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise ValueError(f"currency must be a 3-letter ISO code, got {code!r}")
    return cleaned


def sum_amounts(amounts: list[Decimal] | tuple[Decimal, ...]) -> Decimal:
    total = ZERO
    for amount in amounts:
        total += as_decimal(amount)
    return quantize_money(total)


def gross_profit(*, revenue: Decimal, costs: Decimal) -> Decimal:
    return quantize_money(as_decimal(revenue) - as_decimal(costs))


def cost_per_unit(*, total_costs: Decimal, unit_count: int) -> Decimal | None:
    """Average cost per unit. Undefined when unit_count <= 0."""
    if unit_count <= 0:
        return None
    return quantize_money(as_decimal(total_costs) / Decimal(unit_count))


def customer_acquisition_cost(*, total_costs: Decimal, customer_count: int) -> Decimal | None:
    return cost_per_unit(total_costs=total_costs, unit_count=customer_count)


def roi(*, revenue: Decimal, costs: Decimal) -> Decimal | None:
    """ROI = (revenue - costs) / costs. Undefined when costs == 0."""
    cost_dec = as_decimal(costs)
    if cost_dec == ZERO:
        return None
    profit = as_decimal(revenue) - cost_dec
    return quantize_money(profit / cost_dec)


def sum_by_category(
    entries: Mapping[CostCategory | str, Decimal],
) -> dict[CostCategory, Decimal]:
    """Normalize a category→amount map to every CostCategory with quantized Decimals."""
    result: dict[CostCategory, Decimal] = {cat: ZERO for cat in CostCategory}
    for key, amount in entries.items():
        cat = key if isinstance(key, CostCategory) else CostCategory(str(key))
        result[cat] = quantize_money(result[cat] + as_decimal(amount))
    return result


def total_costs_from_breakdown(breakdown: Mapping[CostCategory, Decimal]) -> Decimal:
    return sum_amounts([as_decimal(v) for v in breakdown.values()])


def mrr_from_recurring(recurring_amounts: list[Decimal] | tuple[Decimal, ...]) -> Decimal:
    """MRR is the sum of recurring subscription amounts in the period (deterministic)."""
    return sum_amounts(list(recurring_amounts))
