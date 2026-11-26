"""Company/entity resolution helpers."""

from __future__ import annotations

import re
from typing import Dict

from financial_evidence_engine.config import CompanyUniverseEntry, CompanyUniverseIndex
from financial_evidence_engine.normalization.models import NormalizedCompany


class EntityResolutionError(ValueError):
    """Raised when a company cannot be resolved or companies conflict."""


class EntityResolver:
    """Resolve ticker, CIK, or company name into one configured company."""

    def __init__(self, universe: CompanyUniverseIndex):
        self._by_ticker: Dict[str, CompanyUniverseEntry] = dict(universe.by_ticker)
        self._by_cik: Dict[str, CompanyUniverseEntry] = dict(universe.by_cik)
        self._by_name: Dict[str, CompanyUniverseEntry] = {}
        for company in universe.companies:
            self._by_name[_normalize_name(company.name)] = company

    def resolve(self, identifier: str) -> NormalizedCompany:
        raw_identifier = identifier.strip()
        if not raw_identifier:
            raise EntityResolutionError("company identifier must not be empty")

        company = (
            self._by_ticker.get(raw_identifier.upper())
            or self._by_cik.get(_normalize_cik(raw_identifier))
            or self._by_name.get(_normalize_name(raw_identifier))
        )
        if company is None:
            raise EntityResolutionError(f"unknown company identifier: {identifier}")
        return _to_normalized_company(company)

    def ensure_same_company(self, left: NormalizedCompany, right: NormalizedCompany) -> None:
        if left.cik != right.cik:
            raise EntityResolutionError(f"different companies: {left.ticker} != {right.ticker}")


def _to_normalized_company(company: CompanyUniverseEntry) -> NormalizedCompany:
    return NormalizedCompany(
        ticker=company.ticker.upper(),
        cik=_normalize_cik(company.cik),
        name=company.name,
        sector=company.sector,
    )


def _normalize_cik(raw_cik: str) -> str:
    digits = "".join(character for character in str(raw_cik) if character.isdigit())
    return digits.zfill(10) if digits else ""


def _normalize_name(raw_name: str) -> str:
    normalized = raw_name.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())
