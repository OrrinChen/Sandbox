"""Shared financial normalization models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class NormalizedCompany:
    """Canonical company identity used before cross-document comparison."""

    ticker: str
    cik: str
    name: str
    sector: str


@dataclass(frozen=True)
class FiscalPeriod:
    """Canonical fiscal or calendar reporting period."""

    year: int
    period: str
    basis: str = "fiscal"
    period_end_date: Optional[date] = None

    @property
    def frequency(self) -> str:
        return "annual" if self.period == "FY" else "quarterly"


@dataclass(frozen=True)
class NormalizedAmount:
    """A numeric amount normalized into base currency units."""

    original_value: Decimal
    value: Decimal
    currency: Optional[str]
    scale: str
    raw_unit: str
