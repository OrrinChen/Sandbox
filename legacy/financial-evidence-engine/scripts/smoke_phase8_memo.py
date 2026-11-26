"""Smoke check for the Phase 8 auditable due-diligence memo layer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph import build_evidence_graph
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan
from financial_evidence_engine.reasoning import ClaimDecomposer, ClaimVerifier
from financial_evidence_engine.reports import build_due_diligence_memo


def _document() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="AAPL:sec_xbrl_companyfacts:2024:FY",
        company="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 9, 28),
        publication_date=date(2024, 11, 1),
        filing_date=date(2024, 11, 1),
        source_url="https://example.com/AAPL:sec_xbrl_companyfacts:2024:FY.json",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def _evidence(document: DocumentMetadata) -> EvidenceUnit:
    return EvidenceUnit.from_document(
        document=document,
        modality="xbrl",
        page_or_section="us-gaap:Revenues",
        raw_text="revenue 2024 FY = 391035000000 USD",
        source_span=SourceSpan(start=3, end=4, label="us-gaap:Revenues:USD:0"),
        normalized_metric="revenue",
        numeric_value=Decimal("391035000000"),
        unit="USD",
        currency="USD",
    )


def main() -> None:
    document = _document()
    evidence = _evidence(document)
    graph = build_evidence_graph(documents=(document,), evidence_units=(evidence,))
    claim = ClaimDecomposer().decompose(
        claim_id="claim:aapl_fy2024_revenue",
        text="Apple FY2024 revenue was $391.035 billion.",
        company_ticker="AAPL",
        fiscal_period="2024-FY",
    )
    result = ClaimVerifier().verify(claim, graph)
    memo = build_due_diligence_memo(
        memo_id="memo:aapl_revenue",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(result,),
    )
    print(
        f"verdict={memo.executive_summary['overall_verdict']} "
        f"sections={len(memo.section_names)} "
        f"evidence_rows={len(memo.evidence_table)} "
        f"numeric_rows={len(memo.numeric_reconciliation)} "
        f"unsupported={len(memo.unsupported_or_weakly_supported_claims)}"
    )


if __name__ == "__main__":
    main()
