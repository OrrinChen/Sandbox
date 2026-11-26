"""Financial metric alias normalization."""

from __future__ import annotations

import re
from typing import Dict, Optional


DEFAULT_METRIC_ALIASES: Dict[str, str] = {
    "revenue": "revenue",
    "revenues": "revenue",
    "sales": "revenue",
    "net sales": "revenue",
    "total net sales": "revenue",
    "total revenue": "revenue",
    "us gaap revenues": "revenue",
    "usgaaprevenues": "revenue",
    "operating income": "operating_income",
    "operating income loss": "operating_income",
    "operatingincomeloss": "operating_income",
    "ebit": "operating_income",
    "earnings before interest and taxes": "operating_income",
    "us gaap operating income loss": "operating_income",
    "usgaapoperatingincomeloss": "operating_income",
    "net income": "net_income",
    "net income loss": "net_income",
    "netincomeloss": "net_income",
    "earnings": "net_income",
    "profit": "net_income",
    "us gaap net income loss": "net_income",
    "usgaapnetincomeloss": "net_income",
    "cash flow from operations": "operating_cash_flow",
    "operating cash flow": "operating_cash_flow",
    "net cash provided by used in operating activities": "operating_cash_flow",
    "netcashprovidedbyusedinoperatingactivities": "operating_cash_flow",
    "us gaap net cash provided by used in operating activities": "operating_cash_flow",
    "usgaapnetcashprovidedbyusedinoperatingactivities": "operating_cash_flow",
}


class MetricAliasError(ValueError):
    """Raised when a required metric alias cannot be normalized."""


class MetricAliasMapper:
    """Map raw financial metric names into stable internal metric IDs."""

    def __init__(self, aliases: Optional[Dict[str, str]] = None):
        raw_aliases = dict(DEFAULT_METRIC_ALIASES)
        if aliases:
            raw_aliases.update(aliases)
        self._aliases = {_normalize_alias(key): value for key, value in raw_aliases.items()}
        self._aliases.update({_compact_alias(key): value for key, value in raw_aliases.items()})

    def normalize(self, raw_metric: str) -> Optional[str]:
        normalized = _normalize_alias(raw_metric)
        return self._aliases.get(normalized) or self._aliases.get(_compact_alias(raw_metric))

    def normalize_required(self, raw_metric: str) -> str:
        metric = self.normalize(raw_metric)
        if metric is None:
            raise MetricAliasError(f"unknown financial metric alias: {raw_metric}")
        return metric


def _normalize_alias(raw_metric: str) -> str:
    normalized = raw_metric.replace(":", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _compact_alias(raw_metric: str) -> str:
    return _normalize_alias(raw_metric).replace(" ", "")
