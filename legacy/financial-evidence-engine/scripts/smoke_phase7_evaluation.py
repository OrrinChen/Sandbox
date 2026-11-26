"""Smoke check for the Phase 7 evaluation and ablation layer."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import build_phase7_evaluation_report, build_seed_task_set


def main() -> None:
    phase7_report = build_phase7_evaluation_report(build_seed_task_set())
    full = phase7_report.baseline_reports["full_evidence_engine"]
    findings = phase7_report.acceptance_findings
    print(
        f"tasks={phase7_report.task_count} "
        f"baselines={len(phase7_report.baseline_reports)} "
        f"ablations={len(phase7_report.ablation_reports)} "
        f"full_verdict_accuracy={full.metrics['verdict_accuracy']} "
        f"validators_matter={findings['validators_matter']} "
        f"naive_rag_fails={findings['naive_rag_fails']}"
    )


if __name__ == "__main__":
    main()
