"""Metric and unit normalization helpers for early extraction."""

from __future__ import annotations

from typing import Optional, Tuple

from financial_evidence_engine.normalization.currency_normalizer import CurrencyNormalizer
from financial_evidence_engine.normalization.metric_mapper import DEFAULT_METRIC_ALIASES, MetricAliasMapper

_METRIC_MAPPER = MetricAliasMapper(DEFAULT_METRIC_ALIASES)
_CURRENCY_NORMALIZER = CurrencyNormalizer()


def normalize_metric(raw_metric: str) -> Optional[str]:
    return _METRIC_MAPPER.normalize(raw_metric)


def parse_unit_and_currency(raw_unit: str) -> Tuple[Optional[str], Optional[str]]:
    tokens = raw_unit.strip().split()
    if not tokens:
        return None, None

    currency = _CURRENCY_NORMALIZER.normalize(raw_unit)
    lowered = raw_unit.lower()
    for scale in ("billions", "millions", "thousands"):
        if scale[:-1] in lowered:
            return scale, currency
    if currency:
        unit_tokens = [token for token in tokens if token.upper() != currency and token != "$"]
        unit = " ".join(unit_tokens) or currency
    else:
        unit = raw_unit.strip()
    return unit or None, currency
