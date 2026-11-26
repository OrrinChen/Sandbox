def test_demo_state_loads_local_artifacts_and_required_pages():
    from financial_evidence_engine.demo import load_demo_state

    state = load_demo_state()

    assert state.api_key_required is False
    assert state.pages == (
        "Claim verification demo",
        "Case study browser",
        "Retrieval method comparison",
        "Memo view",
    )
    assert len(state.case_studies) == 3
    assert set(state.case_studies) == {
        "fiscal_period_confusion",
        "numeric_unit_mismatch",
        "unsupported_narrative_claim",
    }
    assert len(state.retrieval_methods) == 5
    assert "full_engine_real" in state.retrieval_methods
    assert state.memo_markdown


def test_case_study_replay_surfaces_methods_evidence_validators_and_verdict():
    from financial_evidence_engine.demo import load_demo_state, replay_case_study

    state = load_demo_state()
    replay = replay_case_study(state, "unsupported_narrative_claim")

    assert replay.case_id == "unsupported_narrative_claim"
    assert replay.final_verdict == "insufficient"
    assert len(replay.methods) == 5
    assert replay.retrieved_evidence_by_method["full_engine_real"]
    assert replay.validator_checks_by_method["full_engine_real"]
    assert replay.failure_reasons_by_method["bm25_real"]


def test_new_claim_runs_local_pipeline_without_external_services():
    from financial_evidence_engine.demo import run_local_claim_demo

    result = run_local_claim_demo(
        claim_text="Apple FY2024 revenue was $391.035 billion.",
        company_ticker="AAPL",
        fiscal_period="2024-FY",
    )

    assert result.api_key_required is False
    assert result.verdict == "support"
    assert result.evidence_count >= 1
    assert result.numeric_reconciliation_rows >= 1
    assert "Apple FY2024 Revenue Due-Diligence Memo" in result.memo_markdown


def test_demo_markdown_render_is_embeddable_for_streamlit_fallback():
    from financial_evidence_engine.demo import load_demo_state, render_demo_markdown

    markdown = render_demo_markdown(load_demo_state())

    assert "Claim verification demo" in markdown
    assert "Case study browser" in markdown
    assert "Retrieval method comparison" in markdown
    assert "Memo view" in markdown
