"""Smoke check for the Phase 6 due-diligence task set."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import build_seed_task_set


def main() -> None:
    task_set = build_seed_task_set()
    summary = task_set.summary()
    print(
        f"tasks={summary['task_count']} "
        f"families={len(summary['families'])} "
        f"verdicts={len(summary['verdicts'])}"
    )


if __name__ == "__main__":
    main()
