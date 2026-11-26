"""Smoke check for Phase 16 trace and reproducibility artifacts."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.traceability import (
    TraceStore,
    build_case_study_trace_bundle,
    regenerate_case_studies_from_trace,
    write_trace_artifacts,
)


def main() -> None:
    bundle = build_case_study_trace_bundle()
    manifest = write_trace_artifacts(bundle)
    summary = TraceStore(manifest.trace_db_path).integrity_summary()
    regenerated = regenerate_case_studies_from_trace(bundle)
    print(
        f"runs={summary['run_manifests']} "
        f"retrieval_traces={summary['retrieval_traces']} "
        f"verification_traces={summary['verification_traces']} "
        f"evidence_traces={summary['evidence_traces']} "
        f"memo_traces={summary['memo_traces']} "
        f"artifact_records={summary['artifact_manifests']} "
        f"trace_integrity={summary['trace_integrity']} "
        f"case_studies_regenerated={len(regenerated)} "
        f"db={manifest.trace_db_path} "
        f"manifest={manifest.artifact_manifest_path}"
    )


if __name__ == "__main__":
    main()
