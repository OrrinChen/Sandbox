"""Fiscal and calendar period normalization."""

from __future__ import annotations

from datetime import date
import re
from typing import Optional

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.normalization.models import FiscalPeriod


class FiscalPeriodParseError(ValueError):
    """Raised when a reporting period label cannot be parsed."""


class FiscalPeriodMismatchError(ValueError):
    """Raised when two period contexts should not be compared."""


class FiscalPeriodResolver:
    """Resolve period labels and document metadata into canonical periods."""

    _annual_pattern = re.compile(
        r"^(?P<basis>FY|CY|FISCAL\s+YEAR|CALENDAR\s+YEAR)\s*(?P<year>\d{4})$",
        re.IGNORECASE,
    )
    _quarter_patterns = (
        re.compile(r"^(?P<quarter>Q[1-4])\s*(?P<basis>FY|CY)?\s*(?P<year>\d{4})$", re.IGNORECASE),
        re.compile(r"^(?P<basis>FY|CY)?\s*(?P<year>\d{4})\s*(?P<quarter>Q[1-4])$", re.IGNORECASE),
    )

    def parse(self, raw_period: str, period_end_date: Optional[date] = None) -> FiscalPeriod:
        label = " ".join(raw_period.strip().upper().replace("-", " ").split())
        if not label:
            raise FiscalPeriodParseError("period label must not be empty")

        annual_match = self._annual_pattern.match(label)
        if annual_match:
            return FiscalPeriod(
                year=int(annual_match.group("year")),
                period="FY",
                basis=_normalize_basis(annual_match.group("basis")),
                period_end_date=period_end_date,
            )

        for pattern in self._quarter_patterns:
            quarter_match = pattern.match(label)
            if quarter_match:
                return FiscalPeriod(
                    year=int(quarter_match.group("year")),
                    period=quarter_match.group("quarter").upper(),
                    basis=_normalize_basis(quarter_match.group("basis") or "FY"),
                    period_end_date=period_end_date,
                )

        raise FiscalPeriodParseError(f"unsupported period label: {raw_period}")

    def from_document(self, document: DocumentMetadata) -> FiscalPeriod:
        return FiscalPeriod(
            year=document.fiscal_year,
            period=document.fiscal_quarter.upper(),
            basis="fiscal",
            period_end_date=document.period_end_date,
        )

    def period_end_date(self, document: DocumentMetadata) -> date:
        return document.period_end_date

    def ensure_same_period(self, left: FiscalPeriod, right: FiscalPeriod) -> None:
        if left.basis != right.basis:
            raise FiscalPeriodMismatchError(f"period basis mismatch: {left.basis} != {right.basis}")
        if left.frequency != right.frequency:
            raise FiscalPeriodMismatchError(f"period frequency mismatch: {left.frequency} != {right.frequency}")
        if left.year != right.year or left.period != right.period:
            raise FiscalPeriodMismatchError(
                f"period mismatch: {left.basis} {left.year} {left.period} != "
                f"{right.basis} {right.year} {right.period}"
            )
        if (
            left.period_end_date is not None
            and right.period_end_date is not None
            and left.period_end_date != right.period_end_date
        ):
            raise FiscalPeriodMismatchError(
                f"period end date mismatch: {left.period_end_date.isoformat()} != "
                f"{right.period_end_date.isoformat()}"
            )


def _normalize_basis(raw_basis: str) -> str:
    basis = " ".join(raw_basis.upper().split())
    if basis in {"FY", "FISCAL YEAR"}:
        return "fiscal"
    if basis in {"CY", "CALENDAR YEAR"}:
        return "calendar"
    raise FiscalPeriodParseError(f"unsupported period basis: {raw_basis}")
