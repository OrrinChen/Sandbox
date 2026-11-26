from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


FIXTURE_PDF = Path("tests/fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf")


def _deck_metadata():
    from financial_evidence_engine.extraction import DeckDocumentMetadata

    return DeckDocumentMetadata(
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


def _xbrl_reference_unit():
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


def test_investor_deck_pdf_fixture_extracts_page_and_chart_evidence():
    from financial_evidence_engine.extraction import extract_deck_chart_evidence

    result = extract_deck_chart_evidence(_deck_metadata(), FIXTURE_PDF)

    assert FIXTURE_PDF.exists()
    assert FIXTURE_PDF.suffix == ".pdf"
    assert len(result.pages) == 1
    assert result.pages[0].page_number == 1
    assert "Data Center Revenue" in result.pages[0].text
    assert len(result.chart_evidence) == 1

    chart = result.chart_evidence[0]
    assert chart.company_ticker == "NVDA"
    assert chart.fiscal_period == "FY2024"
    assert chart.metric == "revenue"
    assert chart.numeric_value == Decimal("47.5")
    assert chart.unit == "billions"
    assert chart.currency == "USD"
    assert chart.page_number == 1
    assert chart.source_span.start < chart.source_span.end
    assert "47.5" in chart.extracted_text


def test_chart_evidence_converts_to_traceable_evidence_unit():
    from financial_evidence_engine.extraction import extract_deck_chart_evidence

    chart = extract_deck_chart_evidence(_deck_metadata(), FIXTURE_PDF).chart_evidence[0]
    evidence_unit = chart.to_evidence_unit()

    assert evidence_unit.document_id == chart.document_id
    assert evidence_unit.ticker == "NVDA"
    assert evidence_unit.modality == "chart"
    assert evidence_unit.page_or_section == "Page 1 / Data Center Revenue"
    assert evidence_unit.normalized_metric == "revenue"
    assert evidence_unit.numeric_value == Decimal("47.5")
    assert evidence_unit.unit == "billions"
    assert evidence_unit.source_span.label == "page:1:chart:Data Center Revenue"


def test_chart_reconciliation_compares_deck_value_against_xbrl_reference():
    from financial_evidence_engine.extraction import extract_deck_chart_evidence, reconcile_chart_evidence

    chart = extract_deck_chart_evidence(_deck_metadata(), FIXTURE_PDF).chart_evidence[0]
    row = reconcile_chart_evidence(chart, (_xbrl_reference_unit(),))[0]

    assert row.company_ticker == "NVDA"
    assert row.metric == "revenue"
    assert row.fiscal_period == "FY2024"
    assert row.chart_value == Decimal("47.5")
    assert row.reference_value == Decimal("47500000000")
    assert row.normalized_chart_value == Decimal("47500000000.0")
    assert row.status == "pass"
    assert row.verdict == "support"
    assert row.difference == Decimal("0.0")


def test_deck_chart_verification_returns_insufficient_without_chart_evidence():
    from financial_evidence_engine.extraction import (
        ChartExtractionResult,
        build_deck_chart_gap_task,
        verify_deck_chart_claim,
    )

    task = build_deck_chart_gap_task()
    empty_result = ChartExtractionResult(deck=_deck_metadata(), pages=(), chart_evidence=(), issues=())
    verification = verify_deck_chart_claim(
        claim_text=task.claim_text,
        extraction_result=empty_result,
        reference_evidence=(_xbrl_reference_unit(),),
    )

    assert task.family == "chart_gap"
    assert any(requirement.source_type == "investor_deck" for requirement in task.expected_evidence)
    assert verification.final_verdict == "insufficient"
    assert verification.text_only_failure_reason
    assert verification.issues[0].issue_type == "missing_chart_evidence"


def test_deck_chart_verification_supports_reconciled_chart_claim():
    from financial_evidence_engine.extraction import extract_deck_chart_evidence, verify_deck_chart_claim

    extraction = extract_deck_chart_evidence(_deck_metadata(), FIXTURE_PDF)
    verification = verify_deck_chart_claim(
        claim_text="NVIDIA FY2024 Data Center revenue was $47.5 billion.",
        extraction_result=extraction,
        reference_evidence=(_xbrl_reference_unit(),),
    )

    assert verification.final_verdict == "support"
    assert verification.reconciliation_rows[0].status == "pass"
    assert verification.text_only_failure_reason == ""
