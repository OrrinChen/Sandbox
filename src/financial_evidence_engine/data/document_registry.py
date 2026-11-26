"""Build traceable document metadata from SEC submissions and XBRL payloads."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from financial_evidence_engine.config import CompanyUniverseEntry
from financial_evidence_engine.data.cache import stable_json_hash
from financial_evidence_engine.data.models import DocumentMetadata


def build_registry_for_company(
    company: CompanyUniverseEntry,
    submissions_payload: Mapping[str, object],
    companyfacts_payload: Mapping[str, object],
    retrieved_at: datetime,
) -> Tuple[DocumentMetadata, ...]:
    """Build Phase 1 SEC filing and XBRL document metadata for one company."""

    filing = _build_annual_filing_metadata(company, submissions_payload, retrieved_at)
    xbrl = _build_xbrl_metadata(company, companyfacts_payload, retrieved_at)
    return (filing, xbrl)


def align_documents_by_company_period(
    documents: Iterable[DocumentMetadata],
) -> Dict[Tuple[str, int, str], List[DocumentMetadata]]:
    """Group documents so cross-source evidence can align by company and fiscal period."""

    aligned: Dict[Tuple[str, int, str], List[DocumentMetadata]] = defaultdict(list)
    for document in documents:
        aligned[(document.ticker, document.fiscal_year, document.fiscal_quarter)].append(document)
    return dict(aligned)


def _build_annual_filing_metadata(
    company: CompanyUniverseEntry,
    submissions_payload: Mapping[str, object],
    retrieved_at: datetime,
) -> DocumentMetadata:
    filing = _find_filing(submissions_payload, form="10-K", fiscal_year=company.fiscal_year)
    accession_number = _required_string(filing, "accessionNumber")
    primary_document = _required_string(filing, "primaryDocument")
    period_end_date = _parse_date(_required_string(filing, "reportDate"))
    filing_date = _parse_date(_required_string(filing, "filingDate"))
    accession_path = accession_number.replace("-", "")
    cik_path = str(int(company.cik))

    return DocumentMetadata(
        document_id=f"{company.ticker}:sec_filing:10-K:{company.fiscal_year}:{accession_path}",
        company=company.name,
        ticker=company.ticker,
        cik=company.cik,
        source_type="sec_filing",
        filing_type="10-K",
        fiscal_year=company.fiscal_year,
        fiscal_quarter="FY",
        period_end_date=period_end_date,
        publication_date=filing_date,
        filing_date=filing_date,
        source_url=(
            "https://www.sec.gov/Archives/edgar/data/"
            f"{cik_path}/{accession_path}/{primary_document}"
        ),
        retrieved_at=retrieved_at,
        version_hash=stable_json_hash(filing),
        accession_number=accession_number,
    )


def _build_xbrl_metadata(
    company: CompanyUniverseEntry,
    companyfacts_payload: Mapping[str, object],
    retrieved_at: datetime,
) -> DocumentMetadata:
    fact = _find_annual_company_fact(companyfacts_payload, fiscal_year=company.fiscal_year)
    filed = _parse_date(_required_string(fact, "filed"))
    period_end_date = _parse_date(_required_string(fact, "end"))
    accession_number = _optional_string(fact, "accn")

    return DocumentMetadata(
        document_id=f"{company.ticker}:sec_xbrl_companyfacts:{company.fiscal_year}:FY",
        company=company.name,
        ticker=company.ticker,
        cik=company.cik,
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
        fiscal_year=company.fiscal_year,
        fiscal_quarter="FY",
        period_end_date=period_end_date,
        publication_date=filed,
        filing_date=filed,
        source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company.cik}.json",
        retrieved_at=retrieved_at,
        version_hash=stable_json_hash(companyfacts_payload),
        accession_number=accession_number,
    )


def _find_filing(
    submissions_payload: Mapping[str, object],
    form: str,
    fiscal_year: int,
) -> Mapping[str, object]:
    recent = _recent_filings(submissions_payload)
    forms = _required_sequence(recent, "form")
    report_dates = _required_sequence(recent, "reportDate")

    for index, filing_form in enumerate(forms):
        if filing_form != form:
            continue
        report_date = _parse_date(str(report_dates[index]))
        if report_date.year == fiscal_year:
            return {
                key: values[index]
                for key, values in recent.items()
                if isinstance(values, Sequence) and not isinstance(values, (str, bytes)) and index < len(values)
            }

    raise ValueError(f"no {form} filing found for fiscal year {fiscal_year}")


def _find_annual_company_fact(
    companyfacts_payload: Mapping[str, object],
    fiscal_year: int,
) -> Mapping[str, object]:
    facts = companyfacts_payload.get("facts")
    if not isinstance(facts, Mapping):
        raise ValueError("company facts payload missing facts mapping")

    for taxonomy_facts in facts.values():
        if not isinstance(taxonomy_facts, Mapping):
            continue
        for metric in taxonomy_facts.values():
            if not isinstance(metric, Mapping):
                continue
            units = metric.get("units")
            if not isinstance(units, Mapping):
                continue
            for facts_for_unit in units.values():
                if not isinstance(facts_for_unit, list):
                    continue
                for fact in facts_for_unit:
                    if _matches_annual_fact(fact, fiscal_year):
                        return fact

    raise ValueError(f"no annual XBRL company fact found for fiscal year {fiscal_year}")


def _matches_annual_fact(fact: object, fiscal_year: int) -> bool:
    return (
        isinstance(fact, Mapping)
        and fact.get("fy") == fiscal_year
        and fact.get("fp") == "FY"
        and fact.get("form") == "10-K"
        and isinstance(fact.get("filed"), str)
        and isinstance(fact.get("end"), str)
    )


def _recent_filings(submissions_payload: Mapping[str, object]) -> Mapping[str, Sequence[object]]:
    filings = submissions_payload.get("filings")
    if not isinstance(filings, Mapping):
        raise ValueError("submissions payload missing filings mapping")
    recent = filings.get("recent")
    if not isinstance(recent, Mapping):
        raise ValueError("submissions payload missing recent filings mapping")
    return recent


def _required_sequence(mapping: Mapping[str, object], key: str) -> Sequence[object]:
    value = mapping.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} must be a sequence")
    return value


def _required_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(mapping: Mapping[str, object], key: str) -> Optional[str]:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when present")
    return value.strip()


def _parse_date(raw_value: str) -> date:
    return date.fromisoformat(raw_value)
