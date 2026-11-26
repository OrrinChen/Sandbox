from datetime import date, datetime, timezone
from decimal import Decimal

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph import build_evidence_graph
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


def _sample_memo():
    from financial_evidence_engine.reasoning import ClaimDecomposer, ClaimVerifier
    from financial_evidence_engine.reports import build_due_diligence_memo

    document = DocumentMetadata(
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
    evidence = EvidenceUnit.from_document(
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
    graph = build_evidence_graph(documents=(document,), evidence_units=(evidence,))
    claim = ClaimDecomposer().decompose(
        claim_id="claim:aapl_fy2024_revenue",
        text="Apple FY2024 revenue was $391.035 billion.",
        company_ticker="AAPL",
        fiscal_period="2024-FY",
    )
    result = ClaimVerifier().verify(claim, graph)
    return build_due_diligence_memo(
        memo_id="memo:aapl_revenue",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(result,),
    )


def _final_report_package():
    from financial_evidence_engine.evaluation import build_phase7_evaluation_report, build_seed_task_set
    from financial_evidence_engine.reports import build_final_report_package

    task_set = build_seed_task_set()
    return build_final_report_package(
        phase7_report=build_phase7_evaluation_report(task_set),
        sample_memo=_sample_memo(),
    )


def test_final_report_package_contains_charts_tables_sample_memo_and_resume_bullet():
    package = _final_report_package()

    assert package.title == "Multimodal Financial Due-Diligence Evidence Engine Final Report"
    assert {chart.chart_id for chart in package.charts} == {
        "citation_correctness_by_method",
        "numeric_mismatch_rate_by_method",
        "unsupported_claim_rate_by_method",
        "period_confusion_errors_by_method",
    }
    assert {table.table_id for table in package.tables} == {
        "baseline_metrics",
        "ablation_metrics",
        "reproducibility_commands",
    }
    assert package.sample_memo.memo_id == "memo:aapl_revenue"
    assert "python3 -m pytest" in package.reproducibility_commands
    assert "python3 scripts/smoke_real_retrieval_evaluation.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_case_studies.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_deck_chart_extraction.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_raw_corpus.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_adversarial_evaluation.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_embedding_backend.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_llm_decomposition.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_narrative_causal.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_phase8_memo.py" in package.reproducibility_commands
    assert "python3 scripts/smoke_trace_reproducibility.py" in package.reproducibility_commands
    assert "claim-level verification" in package.resume_bullet_long
    assert "dense-proxy" in package.resume_bullet_long
    assert "GraphRAG" not in package.resume_bullet_long
    assert package.resume_bullet_short.startswith("Built a multimodal financial evidence engine")


def test_final_report_charts_are_derived_from_evaluation_metrics():
    package = _final_report_package()
    charts = {chart.chart_id: chart for chart in package.charts}
    numeric_mismatch = charts["numeric_mismatch_rate_by_method"]
    citation = charts["citation_correctness_by_method"]

    assert numeric_mismatch.values["full_evidence_engine"] == Decimal("0")
    assert numeric_mismatch.values["bm25_rag"] == Decimal("1")
    assert citation.values["full_evidence_engine"] == Decimal("1")
    assert citation.values["bm25_rag"] == Decimal("0")
    assert "validators" in numeric_mismatch.insight


def test_final_report_markdown_includes_required_outline_and_sample_memo():
    package = _final_report_package()
    markdown = package.to_markdown()

    for heading in (
        "## 1. Problem framing: financial AI needs auditable evidence",
        "## 2. Data sources and document registry",
        "## 3. Multimodal extraction pipeline",
        "## 4. Financial normalization layer",
        "## 5. Evidence graph",
        "## 6. Claim decomposition and verification",
        "## 7. Due-diligence task set",
        "## 8. Baselines and ablations",
        "## 9. Main results",
        "## 10. Failure taxonomy",
        "## 11. Example due-diligence memo",
        "## 12. Reproducibility guide",
    ):
        assert heading in markdown
    assert "Apple FY2024 Revenue Due-Diligence Memo" in markdown
    assert "Resume bullet" in markdown
    assert "recorded LLM-assisted decomposition" in markdown
    assert "causal narratives" in markdown
    assert "adversarial red-team tasks" in markdown
    assert "One-command trace reproduction" in markdown
    assert "python3 scripts/smoke_trace_reproducibility.py" in markdown
    assert "python3 scripts/smoke_final_report_package.py" in markdown


def test_final_report_serialization_preserves_tables_and_reproducibility():
    package = _final_report_package()
    payload = package.to_dict()

    assert payload["task_count"] == 60
    assert payload["tables"][0]["table_id"] == "baseline_metrics"
    assert payload["charts"][0]["values"]["full_evidence_engine"] == "1"
    assert payload["sample_memo"]["executive_summary"]["overall_verdict"] == "support"
    assert payload["reproducibility_commands"][-1] == "python3 scripts/smoke_final_report_package.py"
