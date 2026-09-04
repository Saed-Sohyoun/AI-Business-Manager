"""Score band mapping for company lead scores."""

from __future__ import annotations

from app.models.enums import ScoreBand
from app.scoring.schemas import ScoreBandLiteral


def band_for_total(total: int) -> ScoreBand:
    if total < 0 or total > 100:
        raise ValueError(f"total score out of range: {total}")
    if total <= 49:
        return ScoreBand.LOW
    if total <= 69:
        return ScoreBand.MEDIUM
    if total <= 84:
        return ScoreBand.GOOD
    return ScoreBand.HIGH


def band_literal(band: ScoreBand) -> ScoreBandLiteral:
    return band.value  # type: ignore[return-value]
