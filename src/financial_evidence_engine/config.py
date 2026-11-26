"""Configuration loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple, Union

import yaml


@dataclass(frozen=True)
class CompanyUniverseEntry:
    """One company selected for the current evidence-engine universe."""

    ticker: str
    name: str
    cik: str
    sector: str
    fiscal_year: int
    required_documents: Tuple[str, ...]


@dataclass(frozen=True)
class CompanyUniverseIndex:
    """Bidirectional lookup for configured companies."""

    companies: Tuple[CompanyUniverseEntry, ...]
    by_ticker: Dict[str, CompanyUniverseEntry]
    by_cik: Dict[str, CompanyUniverseEntry]

    @classmethod
    def from_companies(cls, companies: Iterable[CompanyUniverseEntry]) -> "CompanyUniverseIndex":
        normalized_companies = tuple(companies)
        by_ticker = {company.ticker.upper(): company for company in normalized_companies}
        by_cik = {_normalize_cik(company.cik): company for company in normalized_companies}

        if len(by_ticker) != len(normalized_companies):
            raise ValueError("company universe contains duplicate tickers")
        if len(by_cik) != len(normalized_companies):
            raise ValueError("company universe contains duplicate CIKs")

        return cls(companies=normalized_companies, by_ticker=by_ticker, by_cik=by_cik)

    def company_for_ticker(self, ticker: str) -> CompanyUniverseEntry:
        return self.by_ticker[ticker.upper()]

    def cik_for_ticker(self, ticker: str) -> str:
        return self.company_for_ticker(ticker).cik

    def ticker_for_cik(self, cik: str) -> str:
        return self.by_cik[_normalize_cik(cik)].ticker


def load_company_universe(path: Union[Path, str]) -> Tuple[CompanyUniverseEntry, ...]:
    """Load and validate the configured company universe."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle)

    if not isinstance(raw_config, dict):
        raise ValueError("company universe config must be a mapping")

    raw_companies = raw_config.get("companies")
    if not isinstance(raw_companies, list) or not raw_companies:
        raise ValueError("company universe must contain at least one company")

    return tuple(_parse_company(raw_company) for raw_company in raw_companies)


def _parse_company(raw_company: object) -> CompanyUniverseEntry:
    if not isinstance(raw_company, dict):
        raise ValueError("each company entry must be a mapping")

    required_fields = ("ticker", "name", "cik", "sector", "fiscal_year", "required_documents")
    missing_fields = [field for field in required_fields if field not in raw_company]
    if missing_fields:
        raise ValueError(f"company entry missing required fields: {', '.join(missing_fields)}")

    ticker = _required_string(raw_company, "ticker")
    name = _required_string(raw_company, "name")
    cik = _required_string(raw_company, "cik")
    sector = _required_string(raw_company, "sector")
    fiscal_year = raw_company["fiscal_year"]
    required_documents = _required_string_sequence(raw_company["required_documents"])

    if not isinstance(fiscal_year, int):
        raise ValueError(f"{ticker} fiscal_year must be an integer")
    if not cik.isdigit() or len(cik) != 10:
        raise ValueError(f"{ticker} cik must be a 10-digit SEC CIK string")

    return CompanyUniverseEntry(
        ticker=ticker,
        name=name,
        cik=cik,
        sector=sector,
        fiscal_year=fiscal_year,
        required_documents=tuple(required_documents),
    )


def _required_string(raw_mapping: dict, field: str) -> str:
    value = raw_mapping[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _required_string_sequence(value: object) -> Tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("required_documents must be a non-empty list")

    values: Iterable[object] = value
    normalized = tuple(item.strip() for item in values if isinstance(item, str) and item.strip())
    if len(normalized) != len(value):
        raise ValueError("required_documents must contain only non-empty strings")
    return normalized


def _normalize_cik(cik: str) -> str:
    digits = "".join(character for character in str(cik) if character.isdigit())
    if not digits:
        raise ValueError("CIK must contain digits")
    return digits.zfill(10)
