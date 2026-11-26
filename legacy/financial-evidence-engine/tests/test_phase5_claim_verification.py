from datetime import date, datetime, timezone
from decimal import Decimal

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph import build_evidence_graph
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


def _document(
    ticker="AAPL",
    company="Apple Inc.",
    cik="0000320193",
    document_id="AAPL:sec_xbrl_companyfacts:2024:FY",
) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=document_id,
        company=company,
        ticker=ticker,
        cik=cik,
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 9, 28),
        publication_date=date(2024, 11, 1),
        filing_date=date(2024, 11, 1),
        source_url=f"https://example.com/{document_id}.json",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def _evidence(document: DocumentMetadata, metric="revenue", value=Decimal("391035000000")) -> EvidenceUnit:
    return EvidenceUnit.from_document(
        document=document,
        modality="xbrl",
        page_or_section=f"{metric} fact",
        raw_text=f"{metric} 2024 FY = {value} USD",
        source_span=SourceSpan(start=3, end=4, label=f"us-gaap:{metric}:USD:0"),
        normalized_metric=metric,
        numeric_value=value,
        unit="USD",
        currency="USD",
    )


def test_claim_verifier_supports_numeric_claim_with_validator_readable_output():
    from financial_evidence_engine.reasoning import ClaimDecomposer, ClaimVerifier, Verdict

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
    payload = result.to_dict()

    assert result.verdict == Verdict.SUPPORT
    assert result.subclaim_results[0].verdict == Verdict.SUPPORT
    assert result.subclaim_results[0].evidence[0].evidence_id == evidence.evidence_id
    assert [(check.name, check.status) for check in result.subclaim_results[0].checks] == [
        ("evidence_selection", "pass"),
        ("citation_validation", "pass"),
        ("fiscal_period_validation", "pass"),
        ("source_consistency_validation", "pass"),
        ("numeric_reconciliation", "pass"),
    ]
    assert payload["verdict"] == "support"
    assert payload["subclaims"][0]["checks"][-1]["name"] == "numeric_reconciliation"
    assert payload["subclaims"][0]["evidence"][0]["document_id"] == document.document_id


def test_claim_verifier_returns_insufficient_without_inventing_evidence():
    from financial_evidence_engine.reasoning import Claim, ClaimVerifier, Subclaim, Verdict

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

    result = ClaimVerifier().verify(claim, graph)

    assert result.verdict == Verdict.INSUFFICIENT
    assert result.subclaim_results[0].evidence == ()
    assert result.subclaim_results[0].checks[0].name == "evidence_selection"
    assert result.subclaim_results[0].checks[0].status == "fail"


def test_claim_verifier_marks_numeric_mismatch_as_contradiction():
    from financial_evidence_engine.reasoning import Claim, ClaimVerifier, Subclaim, Verdict

    document = _document()
    evidence = _evidence(document, value=Decimal("390000000000"))
    graph = build_evidence_graph(documents=(document,), evidence_units=(evidence,))
    claim = Claim(
        claim_id="claim:aapl_wrong_revenue",
        text="Apple FY2024 revenue was $391.035 billion.",
        subclaims=(
            Subclaim(
                subclaim_id="claim:aapl_wrong_revenue:1",
                text="Apple FY2024 revenue was $391.035 billion.",
                company_ticker="AAPL",
                fiscal_period="2024-FY",
                metric="revenue",
                expected_value=Decimal("391035000000"),
                expected_currency="USD",
            ),
        ),
    )

    result = ClaimVerifier().verify(claim, graph)

    assert result.verdict == Verdict.CONTRADICT
    assert result.subclaim_results[0].verdict == Verdict.CONTRADICT
    assert result.subclaim_results[0].checks[-1].name == "numeric_reconciliation"
    assert result.subclaim_results[0].checks[-1].status == "fail"


def test_evidence_selector_does_not_use_other_company_evidence():
    from financial_evidence_engine.reasoning import Claim, ClaimVerifier, Subclaim, Verdict

    msft_document = _document(
        ticker="MSFT",
        company="Microsoft Corporation",
        cik="0000789019",
        document_id="MSFT:sec_xbrl_companyfacts:2024:FY",
    )
    msft_evidence = _evidence(msft_document, value=Decimal("245122000000"))
    graph = build_evidence_graph(documents=(msft_document,), evidence_units=(msft_evidence,))
    claim = Claim(
        claim_id="claim:aapl_revenue_not_msft",
        text="Apple FY2024 revenue was $391.035 billion.",
        subclaims=(
            Subclaim(
                subclaim_id="claim:aapl_revenue_not_msft:1",
                text="Apple FY2024 revenue was $391.035 billion.",
                company_ticker="AAPL",
                fiscal_period="2024-FY",
                metric="revenue",
                expected_value=Decimal("391035000000"),
                expected_currency="USD",
            ),
        ),
    )

    result = ClaimVerifier().verify(claim, graph)

    assert result.verdict == Verdict.INSUFFICIENT
    assert result.subclaim_results[0].evidence == ()
