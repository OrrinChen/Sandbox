from pathlib import Path

import pytest


FIXTURE_PATH = Path("tests/fixtures/llm_decompositions/recorded_claim_decompositions.json")


def test_recorded_llm_decomposer_loads_schema_validated_complex_claims():
    from financial_evidence_engine.reasoning import RecordedLLMClaimDecomposer

    decomposer = RecordedLLMClaimDecomposer(FIXTURE_PATH)
    traces = decomposer.decompose_all()
    msft_trace = decomposer.decompose(
        claim_id="complex:msft_cloud_offset",
        text="Microsoft's FY2024 cloud growth was strong enough to offset weakness in other segments.",
        company_ticker="MSFT",
        fiscal_period="FY2024",
    )

    assert FIXTURE_PATH.is_file()
    assert len(traces) >= 5
    assert msft_trace.provider == "recorded_llm"
    assert msft_trace.schema_valid is True
    assert msft_trace.accepted is True
    assert len(msft_trace.claim.subclaims) == 4
    assert [subclaim.metric for subclaim in msft_trace.claim.subclaims] == [
        "cloud_revenue",
        "segment_weakness",
        "offset_relationship",
        "causal_attribution",
    ]
    assert all(check.status == "pass" for check in msft_trace.validator_checks)


def test_recorded_llm_decomposer_rejects_malformed_schema(tmp_path):
    from financial_evidence_engine.reasoning import DecompositionSchemaError, RecordedLLMClaimDecomposer

    bad_fixture = tmp_path / "bad.json"
    bad_fixture.write_text('[{"claim_id": "bad", "text": "Missing subclaims."}]', encoding="utf-8")

    with pytest.raises(DecompositionSchemaError, match="subclaims"):
        RecordedLLMClaimDecomposer(bad_fixture).decompose_all()


def test_validator_gate_rejects_hallucinated_entity_metric_and_period():
    from financial_evidence_engine.reasoning import DecompositionCandidate, ValidatorGate

    gate = ValidatorGate()
    candidates = (
        DecompositionCandidate(
            text="UnknownCo FY2035 quantum EBITDA expanded.",
            company_ticker="ZZZZ",
            fiscal_period="FY2035",
            metric="quantum_ebitda",
        ),
    )

    result = gate.validate(claim_id="bad:hallucination", text="UnknownCo FY2035 quantum EBITDA expanded.", candidates=candidates)

    assert result.accepted is False
    assert result.claim.subclaims == ()
    assert {check.name for check in result.validator_checks} == {
        "entity_validation",
        "period_validation",
        "metric_validation",
    }
    assert all(check.status == "fail" for check in result.validator_checks)


def test_rule_based_and_recorded_llm_report_compare_complex_claim_coverage(tmp_path):
    from financial_evidence_engine.reasoning import (
        build_decomposition_comparison_report,
        write_decomposition_comparison_artifacts,
    )

    report = build_decomposition_comparison_report(FIXTURE_PATH)
    markdown = report.to_markdown()
    payload = report.to_dict()

    assert report.complex_claim_count >= 5
    assert report.recorded_llm_provider == "recorded_llm"
    assert report.rule_based_provider == "rule_based"
    assert report.llm_subclaim_count > report.rule_based_subclaim_count
    assert report.rejected_subclaim_count == 0
    assert payload["examples"][0]["rule_based_subclaims"] >= 1
    assert payload["examples"][0]["llm_subclaims"] >= 3
    assert "Validator-Gated LLM Claim Decomposition" in markdown
    assert "recorded_llm" in markdown

    manifest = write_decomposition_comparison_artifacts(
        report,
        experiments_dir=tmp_path / "experiments",
        reports_dir=tmp_path / "reports",
    )
    assert manifest.json_artifact.is_file()
    assert manifest.markdown_artifact.is_file()


def test_optional_live_llm_decomposer_is_disabled_by_default():
    from financial_evidence_engine.reasoning import LiveLLMUnavailable, OptionalLiveLLMClaimDecomposer

    decomposer = OptionalLiveLLMClaimDecomposer()

    assert not decomposer.is_available()
    assert "disabled" in decomposer.unavailable_reason().lower()
    with pytest.raises(LiveLLMUnavailable):
        decomposer.decompose(
            claim_id="live:disabled",
            text="Microsoft FY2024 cloud growth offset segment weakness.",
            company_ticker="MSFT",
            fiscal_period="FY2024",
        )
