"""Smoke check for the Phase 4 evidence graph layer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph import ClaimLink, build_evidence_graph
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


def _document(document_id: str, source_type: str, filing_type: str) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=document_id,
        company="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        source_type=source_type,
        filing_type=filing_type,
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 9, 28),
        publication_date=date(2024, 11, 1),
        filing_date=date(2024, 11, 1),
        source_url=f"https://example.com/{document_id}.htm",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def _evidence(document: DocumentMetadata, modality: str) -> EvidenceUnit:
    return EvidenceUnit.from_document(
        document=document,
        modality=modality,
        page_or_section="FY2024 revenue evidence",
        raw_text="Revenue 2024 FY = 391035000000 USD",
        source_span=SourceSpan(start=1, end=2, label="revenue"),
        normalized_metric="revenue",
        numeric_value=Decimal("391035000000"),
        unit="USD",
        currency="USD",
    )


def main() -> None:
    filing = _document("AAPL:sec_filing:10-K:2024:000032019324000123", "sec_filing", "10-K")
    xbrl = _document("AAPL:sec_xbrl_companyfacts:2024:FY", "sec_xbrl_companyfacts", "XBRL company facts")
    filing_evidence = _evidence(filing, "table")
    xbrl_evidence = _evidence(xbrl, "xbrl")
    claim = ClaimLink(
        claim_id="claim:aapl_fy2024_revenue",
        text="Apple reported FY2024 revenue of about $391.0 billion.",
        supporting_evidence_ids=(filing_evidence.evidence_id, xbrl_evidence.evidence_id),
    )

    graph = build_evidence_graph(
        documents=(filing, xbrl),
        evidence_units=(filing_evidence, xbrl_evidence),
        claims=(claim,),
    )

    print(
        f"nodes={len(graph.nodes)} edges={len(graph.edges)} "
        f"claim_evidence={len(graph.evidence_for_claim(claim.claim_id))} "
        f"metric_evidence={len(graph.evidence_for_metric('AAPL', 'revenue'))}"
    )


if __name__ == "__main__":
    main()
