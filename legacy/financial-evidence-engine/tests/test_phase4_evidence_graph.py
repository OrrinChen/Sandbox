from datetime import date, datetime, timezone
from decimal import Decimal

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


def _document(
    document_id="AAPL:sec_filing:10-K:2024:000032019324000123",
    source_type="sec_filing",
    filing_type="10-K",
    fiscal_year=2024,
    fiscal_quarter="FY",
    period_end_date=date(2024, 9, 28),
) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=document_id,
        company="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        source_type=source_type,
        filing_type=filing_type,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        period_end_date=period_end_date,
        publication_date=date(fiscal_year, 11, 1),
        filing_date=date(fiscal_year, 11, 1),
        source_url=f"https://example.com/{document_id}.htm",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def _evidence(
    document: DocumentMetadata,
    page_or_section="Item 8 - Financial Statements",
    raw_text="Revenue 2024 FY = 391035000000 USD",
    metric="revenue",
    value=Decimal("391035000000"),
    modality="xbrl",
) -> EvidenceUnit:
    return EvidenceUnit.from_document(
        document=document,
        modality=modality,
        page_or_section=page_or_section,
        raw_text=raw_text,
        source_span=SourceSpan(start=1, end=2, label=page_or_section),
        normalized_metric=metric,
        numeric_value=value,
        unit="USD",
        currency="USD",
    )


def test_graph_builder_creates_typed_nodes_and_trace_edges():
    from financial_evidence_engine.evidence_graph import EdgeType, NodeType, build_evidence_graph

    document = _document()
    evidence = _evidence(document)

    graph = build_evidence_graph(documents=(document,), evidence_units=(evidence,))

    assert graph.node("company:AAPL").node_type == NodeType.COMPANY
    assert graph.node(f"document:{document.document_id}").node_type == NodeType.DOCUMENT
    assert graph.node("period:AAPL:2024-FY").node_type == NodeType.FISCAL_PERIOD
    assert graph.node("metric:AAPL:revenue").node_type == NodeType.METRIC
    assert graph.node(f"evidence:{evidence.evidence_id}").node_type == NodeType.EVIDENCE_UNIT
    assert graph.has_edge(
        f"evidence:{evidence.evidence_id}",
        f"document:{document.document_id}",
        EdgeType.REPORTED_IN,
    )
    assert graph.has_edge(f"evidence:{evidence.evidence_id}", "period:AAPL:2024-FY", EdgeType.SAME_PERIOD_AS)
    assert graph.has_edge("metric:AAPL:revenue", f"evidence:{evidence.evidence_id}", EdgeType.SAME_METRIC_AS)


def test_claim_links_to_multiple_supporting_evidence_units():
    from financial_evidence_engine.evidence_graph import ClaimLink, EdgeType, build_evidence_graph

    filing = _document()
    xbrl = _document(
        document_id="AAPL:sec_xbrl_companyfacts:2024:FY",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
    )
    filing_evidence = _evidence(filing, modality="table")
    xbrl_evidence = _evidence(xbrl, modality="xbrl")
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

    linked_evidence = graph.evidence_for_claim("claim:aapl_fy2024_revenue")

    assert graph.node("claim:claim:aapl_fy2024_revenue").node_type == "Claim"
    assert {node.properties["evidence_id"] for node in linked_evidence} == {
        filing_evidence.evidence_id,
        xbrl_evidence.evidence_id,
    }
    assert graph.has_edge(
        "claim:claim:aapl_fy2024_revenue",
        f"evidence:{filing_evidence.evidence_id}",
        EdgeType.SUPPORTS,
    )


def test_metric_links_corresponding_evidence_across_documents():
    from financial_evidence_engine.evidence_graph import build_evidence_graph

    filing = _document()
    xbrl = _document(
        document_id="AAPL:sec_xbrl_companyfacts:2024:FY",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
    )
    filing_evidence = _evidence(filing, modality="table")
    xbrl_evidence = _evidence(xbrl, modality="xbrl")

    graph = build_evidence_graph(documents=(filing, xbrl), evidence_units=(filing_evidence, xbrl_evidence))

    metric_evidence = graph.evidence_for_metric("AAPL", "revenue")

    assert {node.properties["document_id"] for node in metric_evidence} == {
        filing.document_id,
        xbrl.document_id,
    }
    assert graph.evidence_for_company_period("AAPL", "2024-FY") == tuple(metric_evidence)


def test_risk_theme_wording_can_be_tracked_across_years():
    from financial_evidence_engine.evidence_graph import EdgeType, build_evidence_graph

    doc_2023 = _document(
        document_id="AAPL:sec_filing:10-K:2023:000032019323000106",
        fiscal_year=2023,
        period_end_date=date(2023, 9, 30),
    )
    doc_2024 = _document()
    evidence_2023 = _evidence(
        doc_2023,
        page_or_section="Item 1A - Risk Factors",
        raw_text="Supply constraints could materially affect revenue and margins.",
        metric=None,
        value=None,
        modality="text",
    )
    evidence_2024 = _evidence(
        doc_2024,
        page_or_section="Item 1A - Risk Factors",
        raw_text="Supply constraints and component shortages may affect demand fulfillment.",
        metric=None,
        value=None,
        modality="text",
    )

    graph = build_evidence_graph(
        documents=(doc_2023, doc_2024),
        evidence_units=(evidence_2023, evidence_2024),
        risk_themes=("supply constraints",),
    )

    risk_evidence = graph.evidence_for_risk_theme("AAPL", "supply constraints")

    assert [node.properties["fiscal_period"] for node in risk_evidence] == ["2023-FY", "2024-FY"]
    assert graph.has_edge(
        "risk_factor:AAPL:supply-constraints",
        f"evidence:{evidence_2024.evidence_id}",
        EdgeType.RISK_RELATED_TO,
    )
