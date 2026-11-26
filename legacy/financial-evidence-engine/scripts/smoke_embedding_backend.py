"""Smoke check for Phase 12 pluggable embedding and reranking backend."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import build_seed_task_set
from financial_evidence_engine.retrieval import (
    DeterministicTokenEmbeddingProvider,
    EmbeddingIndex,
    LocalSentenceTransformerProvider,
    build_retrieval_corpus,
    run_embedding_retrieval_evaluation,
)


def main() -> None:
    task_set = build_seed_task_set()
    corpus = build_retrieval_corpus(task_set)
    provider = DeterministicTokenEmbeddingProvider(dimension=32)
    index = EmbeddingIndex.build(corpus, provider)
    with tempfile.TemporaryDirectory() as cache_directory:
        cache_path = Path(cache_directory)
        manifest_path = index.save(cache_path)
        loaded = EmbeddingIndex.load(cache_path)
    optional_provider = LocalSentenceTransformerProvider(model_name="sentence-transformers/all-MiniLM-L6-v2")
    result = run_embedding_retrieval_evaluation(task_set, proxy_provider=provider)
    print(
        f"methods={','.join(result.reports)} "
        f"skipped={','.join(result.skipped_methods)} "
        f"provider={result.embedding_index_manifest.provider_id} "
        f"cached_vectors={loaded.manifest.vector_count} "
        f"manifest={manifest_path.name} "
        f"optional_available={optional_provider.is_available()}"
    )


if __name__ == "__main__":
    main()
