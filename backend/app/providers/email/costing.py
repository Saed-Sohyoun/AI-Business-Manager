"""Internal email cost accounting."""

from __future__ import annotations

from decimal import Decimal


def estimate_email_cost(cost_per_email: Decimal) -> Decimal:
    return cost_per_email if cost_per_email >= 0 else Decimal("0")
