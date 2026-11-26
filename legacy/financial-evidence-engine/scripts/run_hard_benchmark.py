"""Run the synthetic hard retrieval benchmark.

MiniLM is scored only when sentence-transformers is installed and
FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1. Otherwise those rows stay
`not yet run`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation.hard_benchmark import (  # noqa: E402
    build_hard_benchmark,
    evaluate_hard_benchmark,
    render_hard_benchmark_markdown,
)
from financial_evidence_engine.retrieval.embeddings import LocalSentenceTransformerProvider  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", default="experiments/hard_benchmark/hard_benchmark.json")
    parser.add_argument("--markdown-out", default="reports/hard_benchmark/hard_benchmark.md")
    args = parser.parse_args()
    benchmark = build_hard_benchmark()
    embedder, encoder_note = _minilm_embedder()
    payload = evaluate_hard_benchmark(benchmark, embedder, historical_canonical_boost=True)
    payload["setup"]["dense_encoder"] = encoder_note
    json_path = Path(args.json_out)
    markdown_path = Path(args.markdown_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_hard_benchmark_markdown(payload), encoding="utf-8")
    test_recall = payload["methods"]["bm25"]["test"]["recall_at_5"]
    print(
        f"status=ran docs={payload['provenance']['document_count']} "
        f"tasks={payload['provenance']['task_count']} "
        f"bm25_test_recall_at_5={test_recall} "
        f"minilm={payload['methods']['dense_minilm']['status']} "
        f"json={args.json_out}"
    )


def _minilm_embedder():
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    enabled = os.environ.get("FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS") == "1"
    provider = LocalSentenceTransformerProvider(model_name=model_name, enabled=enabled)
    if not provider.is_available():
        return None, f"not yet run. {provider.unavailable_reason()}"
    import importlib.metadata as importlib_metadata

    note = (
        f"ran {model_name}; sentence-transformers {importlib_metadata.version('sentence_transformers')}; "
        f"torch {importlib_metadata.version('torch')}; device cpu; normalize_embeddings=True. "
        "Weights are not committed."
    )

    def embed(texts):
        return provider.embed_texts(texts)

    return embed, note


if __name__ == "__main__":
    main()
