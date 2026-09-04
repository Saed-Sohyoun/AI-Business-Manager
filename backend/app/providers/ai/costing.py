"""Token usage and estimated cost helpers for AI providers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple


class ModelPricing(NamedTuple):
    """USD price per 1,000,000 tokens."""

    input_per_million: Decimal
    output_per_million: Decimal


# Approximate public list prices — used for internal cost accounting, not billing.
# Unknown models fall back to a conservative default.
_MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(Decimal("0.15"), Decimal("0.60")),
    "gpt-4o-mini-2024-07-18": ModelPricing(Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": ModelPricing(Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-2024-08-06": ModelPricing(Decimal("2.50"), Decimal("10.00")),
    "gpt-4.1-mini": ModelPricing(Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1": ModelPricing(Decimal("2.00"), Decimal("8.00")),
    "gpt-3.5-turbo": ModelPricing(Decimal("0.50"), Decimal("1.50")),
}

_DEFAULT_PRICING = ModelPricing(Decimal("1.00"), Decimal("3.00"))


def get_model_pricing(model: str) -> ModelPricing:
    if model in _MODEL_PRICING:
        return _MODEL_PRICING[model]
    # Prefix match for dated variants: "gpt-4o-mini-...."
    for known, pricing in _MODEL_PRICING.items():
        if model.startswith(known):
            return pricing
    return _DEFAULT_PRICING


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal:
    """Estimate USD cost from token counts. Missing counts yield 0."""
    in_tokens = max(input_tokens or 0, 0)
    out_tokens = max(output_tokens or 0, 0)
    if in_tokens == 0 and out_tokens == 0:
        return Decimal("0")

    pricing = get_model_pricing(model)
    cost = (
        (Decimal(in_tokens) / Decimal(1_000_000)) * pricing.input_per_million
        + (Decimal(out_tokens) / Decimal(1_000_000)) * pricing.output_per_million
    )
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def total_tokens(input_tokens: int | None, output_tokens: int | None) -> int | None:
    if input_tokens is None and output_tokens is None:
        return None
    return (input_tokens or 0) + (output_tokens or 0)
