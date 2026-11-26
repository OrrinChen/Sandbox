"""Smoke check for Phase 15 adversarial / red-team evaluation."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import (
    FailureModeTaxonomy,
    build_adversarial_evaluation_report,
    write_adversarial_evaluation_artifacts,
)


def main() -> None:
    taxonomy = FailureModeTaxonomy.default()
    report = build_adversarial_evaluation_report()
    manifest = write_adversarial_evaluation_artifacts(report)
    print(
        f"adversarial_tasks={report.task_count} "
        f"failure_modes={report.failure_mode_count} "
        f"taxonomy_entries={len(taxonomy.entries)} "
        f"validators={len(report.validator_coverage_matrix)} "
        f"full_engine_accuracy={report.full_engine_accuracy} "
        f"explainable_failure_rate={report.explainable_failure_rate} "
        f"perfect_accuracy_required={report.perfect_accuracy_required} "
        f"json_artifact={manifest.json_artifact} "
        f"markdown_artifact={manifest.markdown_artifact}"
    )


if __name__ == "__main__":
    main()
