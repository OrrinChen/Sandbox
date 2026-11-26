"""Unit and scale normalization for financial amounts."""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional

from financial_evidence_engine.normalization.currency_normalizer import CurrencyNormalizer
from financial_evidence_engine.normalization.models import NormalizedAmount


SCALE_MULTIPLIERS: Dict[str, Decimal] = {
    "ones": Decimal("1"),
    "thousands": Decimal("1000"),
    "millions": Decimal("1000000"),
    "billions": Decimal("1000000000"),
}


class UnitNormalizationError(ValueError):
    """Raised when a unit label cannot be normalized safely."""


class UnitNormalizer:
    """Normalize financial numeric values into base currency units."""

    def __init__(self, currency_normalizer: Optional[CurrencyNormalizer] = None):
        self._currency_normalizer = currency_normalizer or CurrencyNormalizer()

    def normalize(self, value: Decimal, raw_unit: str) -> NormalizedAmount:
        raw_unit = raw_unit.strip()
        if not raw_unit:
            raise UnitNormalizationError("unit label must not be empty")

        scale = _detect_scale(raw_unit)
        multiplier = SCALE_MULTIPLIERS[scale]
        return NormalizedAmount(
            original_value=value,
            value=value * multiplier,
            currency=self._currency_normalizer.normalize(raw_unit),
            scale=scale,
            raw_unit=raw_unit,
        )


def _detect_scale(raw_unit: str) -> str:
    lowered = raw_unit.lower()
    if "billion" in lowered:
        return "billions"
    if "million" in lowered:
        return "millions"
    if "thousand" in lowered:
        return "thousands"
    return "ones"
