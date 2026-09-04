"""Search cost estimation helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def estimate_search_cost(cost_per_request: Decimal, *, requests: int = 1) -> Decimal:
    if requests <= 0:
        return Decimal("0")
    cost = Decimal(requests) * cost_per_request
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
