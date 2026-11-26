"""Optional MiniLM dense baseline and metadata-rerank ablation.

Records `not yet run` unless sentence-transformers is installed and
FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1. No paid embedding API is used.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.retrieval.embeddings import (  # noqa: E402
    EmbeddingEvidenceRetriever,
    LocalSentenceTransformerProvider,
    MetadataBoostReranker,
)
from financial_evidence_engine.retrieval.real_baselines import (  # noqa: E402
    BM25EvidenceRetriever,
    build_retrieval_corpus,
)
from financial_evidence_engine.evaluation import build_seed_task_set, evaluate_run  # noqa: E402
from financial_evidence_engine.retrieval.dense_lsa import (  # noqa: E402
    METRICS_OMITTED_NOTE,
    REPORTED_METRICS,
    _RerankedRetriever,
    _evaluation_run,
    _evidence_recall_counts,
)


INSTALL_COMMANDS = (
    "python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu",
    'python3 -m pip install "sentence-transformers==6.2.0"',
)
RUN_COMMAND = (
    "FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1 "
    "python3 scripts/run_sentence_transformer_baseline.py "
    "--config configs/dense_sentence_transformer.yaml"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/dense_sentence_transformer.yaml")
    parser.add_argument(
        "--markdown-out",
        default="reports/dense_sentence_transformer/dense_sentence_transformer_rerank_ablation.md",
    )
    parser.add_argument(
        "--json-out",
        default="experiments/dense_sentence_transformer/dense_sentence_transformer_rerank_ablation.json",
    )
    args = parser.parse_args()
    import yaml

    payload = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    model_name = str(payload.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"))
    require_env = str(payload.get("require_env", "FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS"))
    top_k = int(payload.get("top_k", 5))
    multiplier = int(payload.get("candidate_pool_multiplier", 6))
    corpus_mode = str(payload.get("corpus_mode", "benchmark"))
    enabled = os.environ.get(require_env) == "1"
    provider = LocalSentenceTransformerProvider(model_name=model_name, enabled=enabled)
    if corpus_mode != "benchmark":
        raise SystemExit("sentence-transformer baseline supports corpus_mode=benchmark only")
    if not provider.is_available():
        if Path(args.json_out).is_file():
            print(
                "status=not_yet_run "
                f"reason={provider.unavailable_reason()} "
                f"kept_existing_artifact={args.json_out}"
            )
            return
        _write_not_yet_run(Path("reports/dense_sentence_transformer/STATUS.md"), model_name, provider.unavailable_reason())
        print(f"status=not_yet_run reason={provider.unavailable_reason()} markdown=reports/dense_sentence_transformer/STATUS.md")
        return
    try:
        result = _run(provider, model_name, top_k, multiplier)
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
        if not Path(args.json_out).is_file():
            _write_not_yet_run(Path("reports/dense_sentence_transformer/STATUS.md"), model_name, reason)
        print(f"status=not_yet_run reason={reason}")
        return
    json_path = Path(args.json_out)
    markdown_path = Path(args.markdown_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render(result), encoding="utf-8")
    recall = result["reported_metrics"]["dense_minilm"]["evidence_recall_at_k"]
    print(f"status=ran model={model_name} dense_minilm_recall={recall} json={args.json_out}")


def _run(provider: LocalSentenceTransformerProvider, model_name: str, top_k: int, multiplier: int) -> dict:
    task_set = build_seed_task_set()
    corpus = build_retrieval_corpus(task_set)
    dense = EmbeddingEvidenceRetriever(corpus, provider)
    bm25 = BM25EvidenceRetriever(corpus)
    reranker = MetadataBoostReranker()
    retrievers = {
        "bm25": bm25,
        "bm25_metadata_rerank": _RerankedRetriever(bm25, reranker, multiplier),
        "dense_minilm": dense,
        "dense_minilm_metadata_rerank": _RerankedRetriever(dense, reranker, multiplier),
    }
    reported = {}
    hits = {}
    totals = {}
    recall_at_1 = {}
    recall_at_1_hits = {}
    for method, retriever in retrievers.items():
        run = _evaluation_run(task_set.tasks, method, retriever, top_k)
        report = evaluate_run(run, task_set.tasks, evidence_recall_k=top_k)
        reported[method] = {name: str(report.metrics[name]) for name in REPORTED_METRICS}
        hit_count, total_count = _evidence_recall_counts(task_set.tasks, run, top_k)
        hits[method] = hit_count
        totals[method] = total_count
        report_at_1 = evaluate_run(run, task_set.tasks, evidence_recall_k=1)
        recall_at_1[method] = str(report_at_1.metrics["evidence_recall_at_k"])
        hit_count_at_1, _ignored = _evidence_recall_counts(task_set.tasks, run, 1)
        recall_at_1_hits[method] = hit_count_at_1
    import importlib.metadata as importlib_metadata

    return {
        "experiment_id": "dense_sentence_transformer_rerank_ablation",
        "status": "ran",
        "setup": {
            "corpus_mode": "benchmark",
            "task_set_id": task_set.task_set_id,
            "task_count": len(task_set.tasks),
            "corpus_document_count": len(corpus.documents),
            "top_k": top_k,
            "candidate_pool_multiplier": multiplier,
            "candidate_pool_size_cap": top_k * multiplier,
            "model_name": model_name,
            "provider_id": provider.provider_id,
            "sentence_transformers_version": importlib_metadata.version("sentence_transformers"),
            "torch_version": importlib_metadata.version("torch"),
            "device": "cpu",
            "embedding": (
                "sentence-transformers encode with normalize_embeddings=True, "
                "then cosine retrieval through EmbeddingEvidenceRetriever. "
                "Metadata rerank uses the existing MetadataBoostReranker on up to "
                "top_k * candidate_pool_multiplier candidates. "
                "Not the published verdict-accuracy benchmark."
            ),
            "corpus_construction": (
                "Same constructed benchmark corpus as the published verdict benchmark: "
                "gold evidence specifications plus known distractors. Claim text is "
                "copied into both gold and distractor document text."
            ),
            "weights": "Downloaded at run time from the model id above. Weights are not committed.",
        },
        "method_order": list(retrievers),
        "reported_metrics": reported,
        "evidence_recall_at_1": recall_at_1,
        "evidence_recall_at_1_hits": recall_at_1_hits,
        "evidence_recall_hits": hits,
        "evidence_recall_total": totals,
        "metrics_omitted_note": METRICS_OMITTED_NOTE,
        "command": RUN_COMMAND,
    }


def _render(result: dict) -> str:
    setup = result["setup"]
    lines = [
        "# Dense sentence-transformer baseline",
        "",
        "Status: `ran`",
        "",
        "```bash",
        result["command"],
        "```",
        "",
        f"- Model: `{setup['model_name']}`",
        f"- sentence-transformers: `{setup['sentence_transformers_version']}`",
        f"- torch: `{setup['torch_version']}`",
        f"- Device: `{setup['device']}`",
        f"- Tasks: `{setup['task_count']}`",
        f"- Documents: `{setup['corpus_document_count']}`",
        f"- top_k: `{setup['top_k']}`",
        f"- Rerank candidate pool: up to `{setup['candidate_pool_size_cap']}`",
        f"- Embedding: {setup['embedding']}",
        f"- Corpus: {setup['corpus_construction']}",
        f"- Weights: {setup['weights']}",
        "",
        result["metrics_omitted_note"],
        "",
        "Citation exactness equals evidence recall in this run because every retrieved row is marked cited.",
        "",
        "| Method | Evidence recall@5 | Evidence recall@1 | Citation exactness | Fiscal-period correctness | Entity correctness |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for method in result["method_order"]:
        metrics = result["reported_metrics"][method]
        hits = result["evidence_recall_hits"][method]
        total = result["evidence_recall_total"][method]
        hits_at_1 = result["evidence_recall_at_1_hits"][method]
        lines.append(
            "| {method} | {hits}/{total} = `{recall}` | {hits_at_1}/{total} = `{recall_at_1}` | `{citation}` | `{period}` | `{entity}` |".format(
                method=method,
                hits=hits,
                total=total,
                recall=metrics["evidence_recall_at_k"],
                hits_at_1=hits_at_1,
                recall_at_1=result["evidence_recall_at_1"][method],
                citation=metrics["citation_exactness"],
                period=metrics["fiscal_period_correctness"],
                entity=metrics["entity_correctness"],
            )
        )
    from decimal import Decimal

    lines.extend(
        [
            "",
            "## Rerank deltas",
            "",
            "Differences of the ratios above. A zero difference means the metric did not move.",
            "",
        ]
    )
    for left, right in (
        ("bm25_metadata_rerank", "bm25"),
        ("dense_minilm_metadata_rerank", "dense_minilm"),
    ):
        for label, left_value, right_value in (
            (
                "evidence recall@5",
                result["reported_metrics"][left]["evidence_recall_at_k"],
                result["reported_metrics"][right]["evidence_recall_at_k"],
            ),
            (
                "evidence recall@1",
                result["evidence_recall_at_1"][left],
                result["evidence_recall_at_1"][right],
            ),
            (
                "entity correctness",
                result["reported_metrics"][left]["entity_correctness"],
                result["reported_metrics"][right]["entity_correctness"],
            ),
        ):
            difference = Decimal(left_value) - Decimal(right_value)
            rendered = "0" if difference == 0 else format(difference, "f")
            lines.append(f"- `{left}` {label} minus `{right}` {label} = `{rendered}`")
    lines.append("")
    return "\n".join(lines)


def _write_not_yet_run(path: Path, model_name: str, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "# Dense sentence-transformer baseline",
                "",
                "Status: `not yet run`",
                "",
                f"Model: `{model_name}`",
                f"Reason: {reason}",
                "",
                "This run was not executed. No recall number is reported.",
                "",
                "Exact commands:",
                "",
                "```bash",
                *INSTALL_COMMANDS,
                RUN_COMMAND,
                "```",
                "",
                "CPU torch is enough. Do not point this script at a paid embedding API.",
                "The script writes retrieval ratios only after the model encodes the",
                "benchmark corpus. Until then the status stays `not yet run`.",
                "",
            )
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
