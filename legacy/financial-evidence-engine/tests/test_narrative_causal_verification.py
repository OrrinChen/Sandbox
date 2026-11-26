from decimal import Decimal


def test_narrative_causal_task_set_covers_required_claim_types_and_partial_verdicts():
    from financial_evidence_engine.reasoning import (
        ClaimType,
        PartialVerdict,
        build_narrative_causal_task_set,
    )

    task_set = build_narrative_causal_task_set()
    claim_types = {task.claim_type for task in task_set.tasks}
    expected_verdicts = {task.expected_partial_verdict for task in task_set.tasks}

    assert len(task_set.tasks) >= 10
    assert claim_types >= {
        ClaimType.NUMERIC_TREND,
        ClaimType.SEGMENT_CONTRIBUTION,
        ClaimType.CAUSAL_ATTRIBUTION,
        ClaimType.MANAGEMENT_GUIDANCE,
        ClaimType.RISK_FACTOR_CHANGE,
        ClaimType.DECK_NARRATIVE,
    }
    assert expected_verdicts >= {
        PartialVerdict.SUPPORT_NUMERIC_ONLY,
        PartialVerdict.SUPPORT_NARRATIVE,
        PartialVerdict.CONTRADICT_NUMERIC,
        PartialVerdict.CONTRADICT_NARRATIVE,
        PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT,
    }


def test_verifier_partially_supports_numeric_trend_but_rejects_unsupported_causal_attribution():
    from financial_evidence_engine.reasoning import (
        NarrativeCausalVerifier,
        PartialVerdict,
        build_narrative_causal_task_set,
    )

    task = build_narrative_causal_task_set().task_by_id("phase14:nvda:data_center_driver")
    result = NarrativeCausalVerifier().verify(task)

    assert result.final_verdict == PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT
    assert result.numeric_verdict == PartialVerdict.SUPPORT_NUMERIC_ONLY
    assert len(result.evidence_supported_facts) >= 2
    assert result.inferences == ("Data center contribution is a supported inference from segment share evidence.",)
    assert result.unsupported_causal_attributions == (
        "Demand was the primary causal driver, but no direct demand evidence is present.",
    )
    assert result.validator_status("numeric_trend") == "pass"
    assert result.validator_status("segment_contribution") == "pass"
    assert result.validator_status("causal_support") == "fail"


def test_verifier_outputs_match_expected_partial_verdict_labels():
    from financial_evidence_engine.reasoning import NarrativeCausalVerifier, build_narrative_causal_task_set

    verifier = NarrativeCausalVerifier()

    for task in build_narrative_causal_task_set().tasks:
        assert verifier.verify(task).final_verdict == task.expected_partial_verdict


def test_memo_separates_supported_numeric_trend_inference_and_unsupported_causal_attribution():
    from financial_evidence_engine.reasoning import (
        NarrativeCausalVerifier,
        build_narrative_causal_memo,
        build_narrative_causal_task_set,
    )

    results = tuple(NarrativeCausalVerifier().verify(task) for task in build_narrative_causal_task_set().tasks)
    memo = build_narrative_causal_memo(results)
    markdown = memo.to_markdown()
    payload = memo.to_dict()

    assert payload["section_names"] == [
        "Evidence-supported numeric trend",
        "Inference",
        "Unsupported causal attribution",
    ]
    assert payload["unsupported_causal_attributions"]
    assert "## Evidence-supported numeric trend" in markdown
    assert "## Inference" in markdown
    assert "## Unsupported causal attribution" in markdown


def test_report_surfaces_ordinary_rag_overclaim_failure_modes(tmp_path):
    from financial_evidence_engine.reasoning import (
        PartialVerdict,
        build_narrative_causal_report,
        write_narrative_causal_artifacts,
    )

    report = build_narrative_causal_report()
    manifest = write_narrative_causal_artifacts(report, experiments_dir=tmp_path / "experiments", reports_dir=tmp_path / "reports")

    assert report.task_count >= 10
    assert report.partial_verdict_counts[PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT] >= 1
    assert report.ordinary_rag_overclaim_cases >= 4
    assert report.ordinary_rag_overclaim_rate > Decimal("0")
    assert any(example.ordinary_rag_verdict == PartialVerdict.SUPPORT_NARRATIVE for example in report.overclaim_examples)
    assert manifest.json_artifact.is_file()
    assert manifest.markdown_artifact.is_file()
    assert "ordinary RAG overclaims causal narratives" in manifest.markdown_artifact.read_text(encoding="utf-8")
