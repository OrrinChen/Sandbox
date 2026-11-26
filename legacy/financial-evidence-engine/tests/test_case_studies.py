import json


def test_portfolio_case_studies_cover_required_failure_modes():
    from financial_evidence_engine.case_studies import build_portfolio_case_studies
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import REAL_RETRIEVAL_METHODS

    case_studies = build_portfolio_case_studies(build_seed_task_set())

    assert {case.case_id for case in case_studies} == {
        "fiscal_period_confusion",
        "numeric_unit_mismatch",
        "unsupported_narrative_claim",
    }
    for case in case_studies:
        assert case.claim
        assert case.expected_verdict in {"support", "contradict", "insufficient"}
        assert case.gold_evidence
        assert tuple(case.method_results) == REAL_RETRIEVAL_METHODS
        assert case.final_full_engine_verdict == case.method_results["full_engine_real"].predicted_verdict
        assert case.memo_snippet
        for method_result in case.method_results.values():
            assert method_result.retrieved_evidence
            assert method_result.validator_checks
            assert method_result.failure_reasons


def test_case_study_serialization_and_markdown_include_required_sections():
    from financial_evidence_engine.case_studies import build_portfolio_case_studies
    from financial_evidence_engine.evaluation import build_seed_task_set

    case = build_portfolio_case_studies(build_seed_task_set())[0]
    payload = case.to_dict()
    markdown = case.to_markdown()

    assert payload["claim"] == case.claim
    assert payload["expected_verdict"] == case.expected_verdict
    assert payload["gold_evidence"]
    assert payload["method_results"]["bm25_real"]["retrieved_evidence"]
    assert "## Gold Evidence" in markdown
    assert "## Retrieved Evidence by Method" in markdown
    assert "## Failure Reasons by Method" in markdown
    assert "## Validator Checks Triggered" in markdown
    assert "## Memo Snippet" in markdown


def test_case_study_artifact_writer_outputs_json_and_markdown(tmp_path):
    from financial_evidence_engine.case_studies import build_portfolio_case_studies, write_case_study_artifacts
    from financial_evidence_engine.evaluation import build_seed_task_set

    case_studies = build_portfolio_case_studies(build_seed_task_set())
    manifest = write_case_study_artifacts(
        case_studies,
        experiments_dir=tmp_path / "experiments" / "case_studies",
        reports_dir=tmp_path / "reports" / "case_studies",
    )

    assert len(manifest.json_artifacts) == 3
    assert len(manifest.markdown_artifacts) == 3
    assert manifest.summary_markdown.name == "index.md"

    first_payload = json.loads(manifest.json_artifacts[0].read_text())
    first_markdown = manifest.markdown_artifacts[0].read_text()
    assert first_payload["method_results"]["full_engine_real"]["predicted_verdict"]
    assert "Full engine verdict" in first_markdown


def test_case_study_readme_summary_is_embeddable():
    from financial_evidence_engine.case_studies import build_portfolio_case_studies, render_case_study_summary
    from financial_evidence_engine.evaluation import build_seed_task_set

    summary = render_case_study_summary(build_portfolio_case_studies(build_seed_task_set()))

    assert "| Case | Failure mode | Claim | Full-engine verdict | Artifact |" in summary
    assert "fiscal_period_confusion" in summary
    assert "numeric_unit_mismatch" in summary
    assert "unsupported_narrative_claim" in summary
