"""Smoke check for Phase 1 SEC/XBRL document registry wiring."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, "src")

from financial_evidence_engine.config import load_company_universe
from financial_evidence_engine.data.cache import SourceCache
from financial_evidence_engine.data.document_registry import align_documents_by_company_period
from financial_evidence_engine.data.ingestion import ingest_sec_company


class FixtureSecClient:
    """Offline SEC client fixture for smoke checks without network dependency."""

    def fetch_submissions(self, cik: str) -> dict:
        accession = f"{cik}-24-000001"
        ticker_slug = cik.lstrip("0") or cik
        return {
            "filings": {
                "recent": {
                    "accessionNumber": [accession],
                    "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "form": ["10-K"],
                    "primaryDocument": [f"{ticker_slug}-20240928.htm"],
                }
            }
        }

    def fetch_companyfacts(self, cik: str) -> dict:
        return {
            "cik": int(cik),
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "fy": 2024,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2024-11-01",
                                    "end": "2024-09-28",
                                    "val": 1,
                                    "accn": f"{cik}-24-000001",
                                }
                            ]
                        }
                    }
                }
            },
        }


def main() -> None:
    companies = load_company_universe(Path("configs/companies.yaml"))
    retrieved_at = datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc)

    with tempfile.TemporaryDirectory() as cache_dir:
        cache = SourceCache(cache_dir)
        documents = []
        for company in companies:
            result = ingest_sec_company(
                company=company,
                sec_client=FixtureSecClient(),
                cache=cache,
                retrieved_at=retrieved_at,
            )
            documents.extend(result.documents)

    aligned = align_documents_by_company_period(documents)
    print(f"companies={len(companies)} documents={len(documents)} aligned_periods={len(aligned)}")
    print([company.ticker for company in companies])


if __name__ == "__main__":
    main()
