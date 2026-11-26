from datetime import date, datetime, timezone
from decimal import Decimal

from financial_evidence_engine.data.models import DocumentMetadata


def _document(
    document_id="AAPL:sec_filing:10-K:2024:000032019324000123",
    source_type="sec_filing",
    filing_type="10-K",
) -> DocumentMetadata:
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
        source_url="https://example.com/aapl-20240928.htm",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def _companyfacts_payload():
    return {
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
                                "val": 391035000000,
                                "accn": "0000320193-24-000123",
                            }
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "end": "2024-09-28",
                                "val": 123216000000,
                                "accn": "0000320193-24-000123",
                            }
                        ]
                    }
                },
            }
        }
    }


def test_10k_text_is_chunked_by_sec_item_sections():
    from financial_evidence_engine.extraction.text_extractor import extract_10k_sections

    filing_html = """
    <html><body>
      <h1>Item 1. Business</h1>
      <p>Apple designs products and services.</p>
      <h1>Item 1A. Risk Factors</h1>
      <p>Supply constraints can affect revenue.</p>
      <h1>Item 7. Management's Discussion and Analysis</h1>
      <p>Net sales increased because of iPhone demand.</p>
      <h1>Item 8. Financial Statements and Supplementary Data</h1>
      <p>The consolidated statements follow.</p>
    </body></html>
    """

    sections = extract_10k_sections(_document(), filing_html)

    assert [section.page_or_section for section in sections] == [
        "Item 1 - Business",
        "Item 1A - Risk Factors",
        "Item 7 - MD&A",
        "Item 8 - Financial Statements",
    ]
    assert all(section.document_id == _document().document_id for section in sections)
    assert all(section.fiscal_period == "2024-FY" for section in sections)
    assert all(section.modality == "text" for section in sections)
    assert sections[2].raw_text == "Net sales increased because of iPhone demand."
    assert sections[2].source_span.start < sections[2].source_span.end


def test_xbrl_facts_map_to_standard_metric_evidence_units():
    from financial_evidence_engine.extraction.xbrl_extractor import extract_xbrl_facts

    document = _document(
        document_id="AAPL:sec_xbrl_companyfacts:2024:FY",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
    )

    facts = extract_xbrl_facts(document, _companyfacts_payload())

    assert [(fact.normalized_metric, fact.numeric_value) for fact in facts] == [
        ("revenue", Decimal("391035000000")),
        ("operating_income", Decimal("123216000000")),
    ]
    assert all(fact.modality == "xbrl" for fact in facts)
    assert all(fact.unit == "USD" for fact in facts)
    assert all(fact.currency == "USD" for fact in facts)
    assert facts[0].source_span.label == "us-gaap:Revenues:USD:0"


def test_transcripts_split_by_speaker_and_section():
    from financial_evidence_engine.extraction.transcript_parser import extract_transcript_sections

    transcript = """
    Prepared Remarks
    Tim Cook - Chief Executive Officer
    We set a September quarter revenue record.
    Luca Maestri - Chief Financial Officer
    Gross margin improved sequentially.

    Question and Answer
    Analyst - Morgan Stanley
    What drove Services growth?
    Tim Cook - Chief Executive Officer
    Paid subscriptions reached a new high.
    """

    units = extract_transcript_sections(
        _document(document_id="AAPL:transcript:2024:Q4", source_type="transcript", filing_type="Transcript"),
        transcript,
    )

    assert [unit.page_or_section for unit in units] == [
        "Prepared Remarks / Tim Cook - Chief Executive Officer",
        "Prepared Remarks / Luca Maestri - Chief Financial Officer",
        "Question and Answer / Analyst - Morgan Stanley",
        "Question and Answer / Tim Cook - Chief Executive Officer",
    ]
    assert [unit.modality for unit in units] == ["transcript"] * 4
    assert units[0].raw_text == "We set a September quarter revenue record."
    assert units[-1].raw_text == "Paid subscriptions reached a new high."


def test_markdown_tables_produce_normalized_numeric_evidence():
    from financial_evidence_engine.extraction.table_extractor import extract_markdown_table

    markdown_table = """
    | Metric | FY2024 | Unit |
    | --- | ---: | --- |
    | Revenue | 391.035 | USD billions |
    | Operating income | 123.216 | USD billions |
    """

    units = extract_markdown_table(_document(), markdown_table, page_or_section="Item 8 table")

    assert [(unit.normalized_metric, unit.numeric_value) for unit in units] == [
        ("revenue", Decimal("391.035")),
        ("operating_income", Decimal("123.216")),
    ]
    assert all(unit.modality == "table" for unit in units)
    assert all(unit.unit == "billions" for unit in units)
    assert all(unit.currency == "USD" for unit in units)
    assert units[0].page_or_section == "Item 8 table"
