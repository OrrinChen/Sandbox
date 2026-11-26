"""Guardrails that prevent unsafe financial comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from financial_evidence_engine.normalization.models import FiscalPeriod, NormalizedAmount, NormalizedCompany


class NormalizationGuardrailError(ValueError):
    """Raised when two observations should not be compared."""


@dataclass(frozen=True)
class FinancialObservation:
    """A normalized financial observation ready for validation or reconciliation."""

    company: NormalizedCompany
    fiscal_period: FiscalPeriod
    metric: str
    amount: NormalizedAmount
    source: Optional[str] = None


def ensure_comparable(left: FinancialObservation, right: FinancialObservation) -> None:
    """Raise if two observations would mix company, period, metric, currency, or scale."""

    if left.company.cik != right.company.cik:
        raise NormalizationGuardrailError(f"company mismatch: {left.company.ticker} != {right.company.ticker}")
    if left.metric != right.metric:
        raise NormalizationGuardrailError(f"metric mismatch: {left.metric} != {right.metric}")
    _ensure_same_period(left.fiscal_period, right.fiscal_period)
    _ensure_same_currency(left.amount, right.amount)
    _ensure_scale_reconciled(left.amount, right.amount)


def _ensure_same_period(left: FiscalPeriod, right: FiscalPeriod) -> None:
    if left.basis != right.basis:
        raise NormalizationGuardrailError(f"period basis mismatch: {left.basis} != {right.basis}")
    if left.frequency != right.frequency:
        raise NormalizationGuardrailError(f"period frequency mismatch: {left.frequency} != {right.frequency}")
    if left.year != right.year or left.period != right.period:
        raise NormalizationGuardrailError(
            f"period mismatch: {left.basis} {left.year} {left.period} != "
            f"{right.basis} {right.year} {right.period}"
        )
    if (
        left.period_end_date is not None
        and right.period_end_date is not None
        and left.period_end_date != right.period_end_date
    ):
        raise NormalizationGuardrailError(
            f"period end date mismatch: {left.period_end_date.isoformat()} != {right.period_end_date.isoformat()}"
        )


def _ensure_same_currency(left: NormalizedAmount, right: NormalizedAmount) -> None:
    if left.currency != right.currency:
        raise NormalizationGuardrailError(f"currency mismatch: {left.currency} != {right.currency}")


def _ensure_scale_reconciled(left: NormalizedAmount, right: NormalizedAmount) -> None:
    if left.scale == right.scale:
        return
    if _same_amount(left.value, right.value):
        return
    raise NormalizationGuardrailError(
        f"scale mismatch after normalization: {left.raw_unit} -> {left.value} != {right.raw_unit} -> {right.value}"
    )


def _same_amount(left: Decimal, right: Decimal) -> bool:
    return left == right
