"""Run the CPU TF-IDF SVD retrieval baseline and metadata-rerank ablation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import build_seed_task_set
from financial_evidence_engine.retrieval.dense_lsa import (
    load_dense_lsa_config,
    run_dense_lsa_experiment,
    write_ablation_artifacts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/dense_lsa.yaml")
    parser.add_argument(
        "--json-out",
        default="experiments/dense_lsa/dense_lsa_rerank_ablation.json",
    )
    parser.add_argument(
        "--markdown-out",
        default="reports/dense_lsa/dense_lsa_rerank_ablation.md",
    )
    args = parser.parse_args()
    config = load_dense_lsa_config(Path(args.config))
    command = (
        "python3 scripts/run_dense_lsa_experiment.py "
        f"--config {args.config} --json-out {args.json_out} --markdown-out {args.markdown_out}"
    )
    result = run_dense_lsa_experiment(build_seed_task_set(), config, command=command)
    write_ablation_artifacts(result, Path(args.json_out), Path(args.markdown_out))
    recall = result.reported_metrics["dense_lsa"]["evidence_recall_at_k"]
    reranked = result.reported_metrics["dense_lsa_metadata_rerank"]["evidence_recall_at_k"]
    print(
        f"status={result.status} "
        f"tasks={result.setup['task_count']} "
        f"docs={result.setup['corpus_document_count']} "
        f"vocab={result.setup['vocabulary_size']} "
        f"dense_lsa_recall={recall} "
        f"dense_lsa_rerank_recall={reranked} "
        f"json={args.json_out}"
    )


if __name__ == "__main__":
    main()
