"""Small deterministic claim decomposer for MVP financial claims."""

from __future__ import annotations

from decimal import Decimal
import re
from typing import List, Optional

from financial_evidence_engine.normalization.metric_mapper import MetricAliasMapper
from financial_evidence_engine.normalization.unit_normalizer import UnitNormalizer
from financial_evidence_engine.reasoning.models import Claim, Subclaim


class ClaimDecompositionError(ValueError):
    """Raised when a claim cannot be decomposed into verifiable subclaims."""


class ClaimDecomposer:
    """Convert simple financial claims into structured subclaims.

    This is intentionally conservative. It handles the MVP numeric claim
    patterns and leaves broad natural-language decomposition for later phases.
    """

    _currency_money_pattern = re.compile(
        r"\$\s*(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<scale>billion|million|thousand)?",
        re.IGNORECASE,
    )
    _scaled_money_pattern = re.compile(
        r"(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<scale>billion|million|thousand)",
        re.IGNORECASE,
    )

    def __init__(self, metric_mapper: Optional[MetricAliasMapper] = None, unit_normalizer: Optional[UnitNormalizer] = None):
        self._metric_mapper = metric_mapper or MetricAliasMapper()
        self._unit_normalizer = unit_normalizer or UnitNormalizer()

    def decompose(
        self,
        claim_id: str,
        text: str,
        company_ticker: str,
        fiscal_period: str,
    ) -> Claim:
        subclaims = tuple(
            self._subclaim_for_part(
                claim_id=claim_id,
                index=index,
                text=part,
                company_ticker=company_ticker,
                fiscal_period=fiscal_period,
            )
            for index, part in enumerate(_split_claim(text))
        )
        if not subclaims:
            raise ClaimDecompositionError("claim did not produce any subclaims")
        return Claim(claim_id=claim_id, text=text, subclaims=subclaims)

    def _subclaim_for_part(
        self,
        claim_id: str,
        index: int,
        text: str,
        company_ticker: str,
        fiscal_period: str,
    ) -> Subclaim:
        expected_value = self._expected_value_for_text(text)
        return Subclaim(
            subclaim_id=f"{claim_id}:{index + 1}",
            text=text,
            company_ticker=company_ticker,
            fiscal_period=fiscal_period,
            metric=self._metric_for_text(text),
            expected_value=expected_value,
            expected_currency="USD" if "$" in text else None,
            required_evidence_type="numeric" if expected_value is not None else "text",
            required_terms=self._required_terms_for_text(text),
        )

    def _metric_for_text(self, text: str) -> Optional[str]:
        candidates = (
            "total net sales",
            "net sales",
            "revenue",
            "operating income",
            "EBIT",
            "net income",
            "earnings",
            "cash flow from operations",
            "operating cash flow",
        )
        lowered = text.lower()
        for candidate in candidates:
            if candidate.lower() in lowered:
                return self._metric_mapper.normalize(candidate)
        return None

    def _expected_value_for_text(self, text: str) -> Optional[Decimal]:
        match = self._currency_money_pattern.search(text) or self._scaled_money_pattern.search(text)
        if not match:
            return None

        raw_value = Decimal(match.group("value").replace(",", ""))
        scale = match.group("scale")
        raw_unit = f"USD {scale}s" if scale else "USD"
        return self._unit_normalizer.normalize(raw_value, raw_unit).value

    def _required_terms_for_text(self, text: str) -> tuple:
        metric = self._metric_for_text(text)
        return (metric,) if metric else ()


def _split_claim(text: str) -> List[str]:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []
    parts = re.split(r"\s+and\s+|\s+because\s+|\s+rather than\s+", normalized, flags=re.IGNORECASE)
    return [part.strip(" .") + "." for part in parts if part.strip(" .")]
