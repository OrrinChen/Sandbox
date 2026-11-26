from datetime import date, datetime, timezone
from decimal import Decimal

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph import build_evidence_graph
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


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


def _evidence(document: DocumentMetadata, value=Decimal("391035000000")) -> EvidenceUnit:
    return EvidenceUnit.from_document(
        document=document,
        modality="xbrl",
        page_or_section="us-gaap:Revenues",
        raw_text=f"revenue 2024 FY = {value} USD",
        source_span=SourceSpan(start=3, end=4, label="us-gaap:Revenues:USD:0"),
        normalized_metric="revenue",
        numeric_value=value,
        unit="USD",
        currency="USD",
    )


def _support_result():
    from financial_evidence_engine.reasoning import ClaimDecomposer, ClaimVerifier

    document = _document()
    evidence = _evidence(document)
    graph = build_evidence_graph(documents=(document,), evidence_units=(evidence,))
    claim = ClaimDecomposer().decompose(
        claim_id="claim:aapl_fy2024_revenue",
        text="Apple FY2024 revenue was $391.035 billion.",
        company_ticker="AAPL",
        fiscal_period="2024-FY",
    )
    return ClaimVerifier().verify(claim, graph)


def _insufficient_result():
    from financial_evidence_engine.reasoning import Claim, ClaimVerifier, Subclaim

    graph = build_evidence_graph(documents=(), evidence_units=())
    claim = Claim(
        claim_id="claim:aapl_missing_revenue",
        text="Apple FY2024 revenue was $391.035 billion.",
        subclaims=(
            Subclaim(
                subclaim_id="claim:aapl_missing_revenue:1",
                text="Apple FY2024 revenue was $391.035 billion.",
                company_ticker="AAPL",
                fiscal_period="2024-FY",
                metric="revenue",
                expected_value=Decimal("391035000000"),
                expected_currency="USD",
            ),
        ),
    )
    return ClaimVerifier().verify(claim, graph)


def test_due_diligence_memo_contains_required_audit_sections():
    from financial_evidence_engine.reports import build_due_diligence_memo

    memo = build_due_diligence_memo(
        memo_id="memo:aapl_revenue",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(_support_result(),),
    )

    assert memo.section_names == (
        "Executive summary",
        "Key claims",
        "Evidence table",
        "Numeric reconciliation",
        "Cross-document contradictions",
        "Risk flags",
        "Unsupported or weakly supported claims",
        "Confidence and limitations",
    )
    assert memo.executive_summary["overall_verdict"] == "support"
    assert memo.key_claims[0].verdict == "support"


def test_memo_conclusions_are_traceable_to_source_evidence():
    from financial_evidence_engine.reports import build_due_diligence_memo

    memo = build_due_diligence_memo(
        memo_id="memo:aapl_revenue",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(_support_result(),),
    )
    conclusion = memo.conclusions[0]

    assert conclusion.citation == "AAPL:sec_xbrl_companyfacts:2024:FY#us-gaap:Revenues:USD:0"
    assert conclusion.source_document == "AAPL:sec_xbrl_companyfacts:2024:FY"
    assert conclusion.page_or_section == "us-gaap:Revenues"
    assert conclusion.metric == "revenue"
    assert conclusion.period == "2024-FY"
    assert "numeric_reconciliation:pass" in conclusion.validator_result
    assert conclusion.evidence_summary
    assert conclusion.inference


def test_memo_numeric_reconciliation_rows_are_recomputable():
    from financial_evidence_engine.reports import build_due_diligence_memo

    memo = build_due_diligence_memo(
        memo_id="memo:aapl_revenue",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(_support_result(),),
    )
    row = memo.numeric_reconciliation[0]

    assert row.metric == "revenue"
    assert row.period == "2024-FY"
    assert row.expected_value == Decimal("391035000000")
    assert row.observed_value == Decimal("391035000000")
    assert row.difference == Decimal("0")
    assert row.recomputable
    assert row.validator_result == "numeric_reconciliation:pass"


def test_memo_explicitly_lists_unresolved_issues_without_inventing_evidence():
    from financial_evidence_engine.reports import build_due_diligence_memo

    memo = build_due_diligence_memo(
        memo_id="memo:aapl_missing_revenue",
        title="Apple Missing Revenue Due-Diligence Memo",
        claim_results=(_insufficient_result(),),
    )

    assert memo.executive_summary["overall_verdict"] == "insufficient"
    assert memo.evidence_table == ()
    assert memo.unsupported_or_weakly_supported_claims
    assert memo.unsupported_or_weakly_supported_claims[0].issue_type == "insufficient_evidence"
    assert "No selected evidence" in memo.unsupported_or_weakly_supported_claims[0].description


def test_memo_markdown_separates_evidence_from_inference():
    from financial_evidence_engine.reports import build_due_diligence_memo

    memo = build_due_diligence_memo(
        memo_id="memo:aapl_revenue",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(_support_result(),),
    )
    markdown = memo.to_markdown()

    assert "## Evidence table" in markdown
    assert "## Key claims" in markdown
    assert "Evidence summary:" in markdown
    assert "Inference:" in markdown
    assert markdown.index("## Evidence table") < markdown.index("## Numeric reconciliation")
