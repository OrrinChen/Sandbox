"""Smoke check for real local retrieval evaluation runs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import build_seed_task_set
from financial_evidence_engine.retrieval import build_raw_financial_corpus, run_real_retrieval_evaluation


FIXTURE_DECK = Path("tests/fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", choices=("benchmark", "raw"), default="benchmark")
    args = parser.parse_args()

    task_set = build_seed_task_set()
    raw_corpus = build_raw_financial_corpus(task_set, deck_fixture_path=FIXTURE_DECK) if args.corpus == "raw" else None
    result = run_real_retrieval_evaluation(task_set, corpus_mode=args.corpus, raw_corpus=raw_corpus)
    full = result.reports["full_engine_real"]
    bm25 = result.reports["bm25_real"]
    print(
        f"tasks={result.task_count} "
        f"corpus_mode={result.corpus_mode} "
        f"corpus_documents={result.corpus_document_count} "
        f"raw_chunks={result.raw_chunk_count} "
        f"methods={len(result.reports)} "
        f"bm25_numeric_correctness={bm25.metrics['numeric_correctness']} "
        f"full_verdict_accuracy={full.metrics['verdict_accuracy']} "
        f"failure_cases={len(result.failure_cases)}"
    )


if __name__ == "__main__":
    main()
