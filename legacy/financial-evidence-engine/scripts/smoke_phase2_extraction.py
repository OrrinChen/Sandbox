"""Smoke check for Phase 2 extraction into traceable evidence units."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, "src")

from financial_evidence_engine.config import load_company_universe
from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.table_extractor import extract_markdown_table
from financial_evidence_engine.extraction.text_extractor import extract_10k_sections
from financial_evidence_engine.extraction.transcript_parser import extract_transcript_sections
from financial_evidence_engine.extraction.xbrl_extractor import extract_xbrl_facts


def main() -> None:
    company = load_company_universe(Path("configs/companies.yaml"))[0]
    document = DocumentMetadata(
        document_id=f"{company.ticker}:sec_filing:10-K:2024:fixture",
        company=company.name,
        ticker=company.ticker,
        cik=company.cik,
        source_type="sec_filing",
        filing_type="10-K",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 9, 28),
        publication_date=date(2024, 11, 1),
        filing_date=date(2024, 11, 1),
        source_url="fixture://aapl-20240928.htm",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
    )

    sections = extract_10k_sections(
        document,
        """
        <h1>Item 1. Business</h1><p>Apple designs products.</p>
        <h1>Item 1A. Risk Factors</h1><p>Supply constraints can affect revenue.</p>
        <h1>Item 7. Management's Discussion and Analysis</h1><p>Net sales increased.</p>
        <h1>Item 8. Financial Statements</h1><p>Statements follow.</p>
        """,
    )
    xbrl_units = extract_xbrl_facts(
        DocumentMetadata(
            **{
                **document.__dict__,
                "document_id": f"{company.ticker}:sec_xbrl_companyfacts:2024:FY",
                "source_type": "sec_xbrl_companyfacts",
                "filing_type": "XBRL company facts",
            }
        ),
        {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"fy": 2024, "fp": "FY", "form": "10-K", "val": 391035000000}
                            ]
                        }
                    }
                }
            }
        },
    )
    transcript_units = extract_transcript_sections(
        DocumentMetadata(
            **{
                **document.__dict__,
                "document_id": f"{company.ticker}:transcript:2024:Q4",
                "source_type": "transcript",
                "filing_type": "Transcript",
            }
        ),
        """
        Prepared Remarks
        Tim Cook - Chief Executive Officer
        We set a September quarter revenue record.
        """,
    )
    table_units = extract_markdown_table(
        document,
        """
        | Metric | FY2024 | Unit |
        | --- | ---: | --- |
        | Revenue | 391.035 | USD billions |
        """,
        page_or_section="Item 8 table",
    )

    print(
        "sections="
        f"{len(sections)} xbrl={len(xbrl_units)} transcripts={len(transcript_units)} tables={len(table_units)}"
    )


if __name__ == "__main__":
    main()
