"""Smoke check for Phase 9 portfolio case-study artifacts."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.case_studies import build_portfolio_case_studies, write_case_study_artifacts
from financial_evidence_engine.evaluation import build_seed_task_set
from financial_evidence_engine.retrieval import REAL_RETRIEVAL_METHODS


def main() -> None:
    case_studies = build_portfolio_case_studies(build_seed_task_set())
    manifest = write_case_study_artifacts(case_studies)
    print(
        f"case_studies={len(case_studies)} "
        f"methods={len(REAL_RETRIEVAL_METHODS)} "
        f"json_artifacts={len(manifest.json_artifacts)} "
        f"markdown_artifacts={len(manifest.markdown_artifacts)} "
        f"summary={manifest.summary_markdown}"
    )


if __name__ == "__main__":
    main()
