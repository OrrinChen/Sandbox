import json


def test_trace_bundle_records_required_reproducibility_fields():
    from financial_evidence_engine.traceability import build_case_study_trace_bundle

    bundle = build_case_study_trace_bundle()

    assert len(bundle.run_manifests) == 3
    assert len(bundle.retrieval_traces) == 3
    assert len(bundle.verification_traces) == 3
    assert len(bundle.evidence_traces) == 3
    assert len(bundle.memo_traces) == 3
    assert len(bundle.artifact_manifests) == 3

    for manifest in bundle.run_manifests:
        assert manifest.run_id.startswith("trace:")
        assert len(manifest.config_hash) == 64
        assert manifest.corpus_version.startswith("benchmark:")
        assert manifest.method == "full_engine_real"
        assert manifest.task_id
        assert manifest.runtime_ms > 0
        assert manifest.artifact_paths

    for trace in bundle.retrieval_traces:
        assert trace.retrieved_chunks
        assert trace.method == "full_engine_real"

    for trace in bundle.verification_traces:
        assert trace.validator_results
        assert trace.final_verdict in {"support", "contradict", "insufficient"}


def test_trace_store_persists_sqlite_records_and_integrity_summary(tmp_path):
    from financial_evidence_engine.traceability import TraceStore, build_case_study_trace_bundle

    bundle = build_case_study_trace_bundle()
    db_path = tmp_path / "phase16_trace.sqlite"
    store = TraceStore(db_path)
    store.write_bundle(bundle)

    summary = store.integrity_summary()

    assert db_path.exists()
    assert summary["run_manifests"] == 3
    assert summary["retrieval_traces"] == 3
    assert summary["verification_traces"] == 3
    assert summary["evidence_traces"] == 3
    assert summary["memo_traces"] == 3
    assert summary["artifact_manifests"] == 3
    assert summary["trace_integrity"] is True
    assert summary["retrieved_chunks"] >= 3
    assert summary["validator_results"] >= 3


def test_trace_artifact_writer_outputs_database_and_manifest_json(tmp_path):
    from financial_evidence_engine.traceability import (
        build_case_study_trace_bundle,
        write_trace_artifacts,
    )

    bundle = build_case_study_trace_bundle()
    manifest = write_trace_artifacts(
        bundle,
        trace_db_path=tmp_path / "experiments" / "traces" / "phase16_trace.sqlite",
        artifact_manifest_path=tmp_path / "reports" / "traces" / "phase16_artifact_manifest.json",
    )

    payload = json.loads(manifest.artifact_manifest_path.read_text())

    assert manifest.trace_db_path.exists()
    assert manifest.artifact_manifest_path.exists()
    assert payload["run_count"] == 3
    assert payload["trace_integrity"] is True
    assert payload["corpus_version"].startswith("benchmark:")
    assert len(payload["runs"]) == 3
    assert payload["runs"][0]["artifact_paths"]


def test_case_studies_can_be_regenerated_from_trace_bundle():
    from financial_evidence_engine.traceability import (
        build_case_study_trace_bundle,
        regenerate_case_studies_from_trace,
    )

    bundle = build_case_study_trace_bundle()
    regenerated = regenerate_case_studies_from_trace(bundle)

    assert len(regenerated) == 3
    assert {case["case_id"] for case in regenerated} == {
        "fiscal_period_confusion",
        "numeric_unit_mismatch",
        "unsupported_narrative_claim",
    }
    for case in regenerated:
        assert case["task_id"]
        assert case["final_verdict"] in {"support", "contradict", "insufficient"}
        assert case["artifact_paths"]
