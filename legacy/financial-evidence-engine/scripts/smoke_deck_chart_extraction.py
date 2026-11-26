"""Smoke check for Phase 10 investor-deck chart extraction."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction import (
    DeckDocumentMetadata,
    SourceSpan,
    build_deck_chart_gap_task,
    extract_deck_chart_evidence,
    verify_deck_chart_claim,
)
from financial_evidence_engine.extraction.models import EvidenceUnit


FIXTURE_PDF = Path("tests/fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf")


def main() -> None:
    deck = DeckDocumentMetadata(
        document_id="NVDA:investor_deck:FY2024:data_center_fixture",
        company="NVIDIA Corporation",
        ticker="NVDA",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 1, 28),
        publication_date=date(2024, 2, 21),
        source_url="fixture://nvda_fy2024_data_center_chart.pdf",
        retrieved_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        version_hash="1" * 64,
        deck_title="NVIDIA FY2024 Investor Presentation",
    )
    reference = _xbrl_reference_unit()
    extraction = extract_deck_chart_evidence(deck, FIXTURE_PDF)
    task = build_deck_chart_gap_task()
    verification = verify_deck_chart_claim(task.claim_text, extraction, (reference,))
    print(
        f"deck_pages={len(extraction.pages)} "
        f"chart_evidence={len(extraction.chart_evidence)} "
        f"chart_tasks=1 "
        f"reconciliation_rows={len(verification.reconciliation_rows)} "
        f"verdict={verification.final_verdict}"
    )


def _xbrl_reference_unit() -> EvidenceUnit:
    document = DocumentMetadata(
        document_id="NVDA:sec_xbrl_companyfacts:2024:FY",
        company="NVIDIA Corporation",
        ticker="NVDA",
        cik="0001045810",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 1, 28),
        publication_date=date(2024, 2, 21),
        filing_date=date(2024, 2, 21),
        source_url="fixture://nvda-companyfacts-2024.json",
        retrieved_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        version_hash="2" * 64,
        accession_number="0001045810-24-000029",
    )
    return EvidenceUnit.from_document(
        document=document,
        modality="xbrl",
        page_or_section="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        raw_text="Data Center revenue FY2024 = 47500000000 USD",
        source_span=SourceSpan(start=0, end=1, label="us-gaap:DataCenterRevenue:USD:0"),
        normalized_metric="revenue",
        numeric_value=Decimal("47500000000"),
        unit="USD",
        currency="USD",
    )


if __name__ == "__main__":
    main()
