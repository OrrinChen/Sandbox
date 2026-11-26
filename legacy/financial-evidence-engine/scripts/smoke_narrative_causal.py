"""Smoke check for Phase 14 narrative and causal claim verification."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.reasoning import (
    build_narrative_causal_report,
    build_narrative_causal_task_set,
    write_narrative_causal_artifacts,
)


def main() -> None:
    task_set = build_narrative_causal_task_set()
    report = build_narrative_causal_report(task_set)
    manifest = write_narrative_causal_artifacts(report)
    print(
        f"narrative_tasks={report.task_count} "
        f"claim_types={len(task_set.summary()['claim_types'])} "
        f"partial_verdicts={len(report.partial_verdict_counts)} "
        f"overclaim_cases={report.ordinary_rag_overclaim_cases} "
        f"overclaim_rate={report.ordinary_rag_overclaim_rate} "
        f"unsupported_causal={len(report.memo.unsupported_causal_attributions)} "
        f"json_artifact={manifest.json_artifact} "
        f"markdown_artifact={manifest.markdown_artifact}"
    )


if __name__ == "__main__":
    main()
