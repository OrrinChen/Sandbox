"""Pluggable embedding and reranking backend for local retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple

from financial_evidence_engine.evaluation.metrics import EvaluationReport, EvaluationRun, evaluate_run
from financial_evidence_engine.evaluation.task_set import DueDiligenceTask, DueDiligenceTaskSet
from financial_evidence_engine.retrieval.real_baselines import (
    BM25EvidenceRetriever,
    GraphEvidenceRetriever,
    RetrievalCorpus,
    RetrievalResult,
    _build_run,
    _select_corpus,
)


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
EMBEDDING_INDEX_CREATED_AT = datetime(2026, 5, 2, 12, 30, tzinfo=timezone.utc)
_SENTENCE_TRANSFORMER_CACHE: Dict[str, object] = {}


class EmbeddingBackendUnavailable(RuntimeError):
    """Raised when an optional embedding backend is not available."""


class EmbeddingProvider(Protocol):
    """Embedding provider interface used by retrieval indexes."""

    provider_id: str
    backend_kind: str
    dimension: int

    def is_available(self) -> bool:
        """Return whether this provider can embed text in the current environment."""

    def unavailable_reason(self) -> str:
        """Explain why the provider is unavailable."""

    def embed_texts(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        """Embed texts into fixed-width vectors."""


@dataclass(frozen=True)
class DeterministicTokenEmbeddingProvider:
    """Offline deterministic token-vector embedding provider."""

    provider_id: str = "deterministic-token-v1"
    backend_kind: str = "proxy"
    dimension: int = 64

    def is_available(self) -> bool:
        return True

    def unavailable_reason(self) -> str:
        return ""

    def embed_texts(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        return tuple(_embed_deterministic(text, self.dimension) for text in texts)


@dataclass(frozen=True)
class LocalSentenceTransformerProvider:
    """Optional local sentence-transformers adapter, disabled by default."""

    model_name: str
    enabled: bool = False
    dimension: int = 384
    backend_kind: str = "real"

    @property
    def provider_id(self) -> str:
        return f"local-sentence-transformer:{self.model_name}"

    def is_available(self) -> bool:
        return self.enabled and importlib.util.find_spec("sentence_transformers") is not None

    def unavailable_reason(self) -> str:
        if not self.enabled:
            return "Local sentence-transformer backend is disabled by default."
        if importlib.util.find_spec("sentence_transformers") is None:
            return "sentence_transformers is not installed."
        return ""

    def embed_texts(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        if not self.is_available():
            raise EmbeddingBackendUnavailable(self.unavailable_reason())
        model = _load_sentence_transformer(self.model_name)
        vectors = model.encode(list(texts), normalize_embeddings=True)
        return tuple(tuple(float(value) for value in vector) for vector in vectors)


@dataclass(frozen=True)
class OpenAIEmbeddingProvider:
    """Optional live OpenAI embedding adapter, disabled unless explicitly enabled."""

    model: str = "text-embedding-3-small"
    api_key_env: str = "OPENAI_API_KEY"
    enabled: bool = False
    dimension: int = 1536
    backend_kind: str = "real"

    @property
    def provider_id(self) -> str:
        return f"openai:{self.model}"

    def is_available(self) -> bool:
        return (
            self.enabled
            and bool(os.environ.get(self.api_key_env))
            and importlib.util.find_spec("openai") is not None
        )

    def unavailable_reason(self) -> str:
        if not self.enabled:
            return "OpenAI embedding backend is disabled by default."
        if not os.environ.get(self.api_key_env):
            return f"{self.api_key_env} is not set."
        if importlib.util.find_spec("openai") is None:
            return "openai package is not installed."
        return ""

    def embed_texts(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        if not self.is_available():
            raise EmbeddingBackendUnavailable(self.unavailable_reason())
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=os.environ[self.api_key_env])
        response = client.embeddings.create(model=self.model, input=list(texts))
        return tuple(tuple(float(value) for value in item.embedding) for item in response.data)


@dataclass(frozen=True)
class EmbeddingIndexManifest:
    """Manifest for a cached embedding index."""

    provider_id: str
    backend_kind: str
    dimension: int
    vector_count: int
    corpus_document_count: int
    corpus_hash: str
    created_at: datetime
    version_hash: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "backend_kind": self.backend_kind,
            "dimension": self.dimension,
            "vector_count": self.vector_count,
            "corpus_document_count": self.corpus_document_count,
            "corpus_hash": self.corpus_hash,
            "created_at": self.created_at.isoformat(),
            "version_hash": self.version_hash,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EmbeddingIndexManifest":
        return cls(
            provider_id=str(payload["provider_id"]),
            backend_kind=str(payload["backend_kind"]),
            dimension=int(payload["dimension"]),
            vector_count=int(payload["vector_count"]),
            corpus_document_count=int(payload["corpus_document_count"]),
            corpus_hash=str(payload["corpus_hash"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            version_hash=str(payload["version_hash"]),
        )


@dataclass(frozen=True)
class EmbeddingIndex:
    """Cached embedding vectors for a retrieval corpus."""

    manifest: EmbeddingIndexManifest
    document_ids: Tuple[str, ...]
    vectors: Tuple[Tuple[float, ...], ...]

    @classmethod
    def build(cls, corpus: RetrievalCorpus, provider: EmbeddingProvider) -> "EmbeddingIndex":
        if not provider.is_available():
            raise EmbeddingBackendUnavailable(provider.unavailable_reason())
        texts = tuple(document.text for document in corpus.documents)
        vectors = provider.embed_texts(texts)
        dimension = len(vectors[0]) if vectors else provider.dimension
        document_ids = tuple(document.document_id for document in corpus.documents)
        corpus_hash = _corpus_hash(corpus)
        version_hash = _hash(
            "|".join(
                (
                    provider.provider_id,
                    provider.backend_kind,
                    str(dimension),
                    corpus_hash,
                    str(len(vectors)),
                )
            )
        )
        manifest = EmbeddingIndexManifest(
            provider_id=provider.provider_id,
            backend_kind=provider.backend_kind,
            dimension=dimension,
            vector_count=len(vectors),
            corpus_document_count=len(corpus.documents),
            corpus_hash=corpus_hash,
            created_at=EMBEDDING_INDEX_CREATED_AT,
            version_hash=version_hash,
        )
        return cls(manifest=manifest, document_ids=document_ids, vectors=tuple(vectors))

    def save(self, cache_dir: Path) -> Path:
        cache_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = cache_dir / "embedding_manifest.json"
        embeddings_path = cache_dir / "embeddings.json"
        manifest_path.write_text(json.dumps(self.manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        embeddings_path.write_text(
            json.dumps(
                {
                    "document_ids": list(self.document_ids),
                    "vectors": [list(vector) for vector in self.vectors],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return manifest_path

    @classmethod
    def load(cls, cache_dir: Path) -> "EmbeddingIndex":
        manifest = EmbeddingIndexManifest.from_dict(
            json.loads((cache_dir / "embedding_manifest.json").read_text(encoding="utf-8"))
        )
        payload = json.loads((cache_dir / "embeddings.json").read_text(encoding="utf-8"))
        return cls(
            manifest=manifest,
            document_ids=tuple(str(document_id) for document_id in payload["document_ids"]),
            vectors=tuple(tuple(float(value) for value in vector) for vector in payload["vectors"]),
        )

    def vector_for_document_id(self, document_id: str) -> Tuple[float, ...]:
        index = self.document_ids.index(document_id)
        return self.vectors[index]


class EmbeddingEvidenceRetriever:
    """Embedding retriever backed by a pluggable provider and cached index."""

    def __init__(
        self,
        corpus: RetrievalCorpus,
        provider: EmbeddingProvider,
        embedding_index: Optional[EmbeddingIndex] = None,
    ) -> None:
        self._corpus = corpus
        self._provider = provider
        self._index = embedding_index or EmbeddingIndex.build(corpus, provider)

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        query_vector = self._provider.embed_texts((_query_text(task),))[0]
        results = [
            RetrievalResult(document=document, score=_decimal_score(_cosine(query_vector, vector)))
            for document, vector in zip(self._corpus.documents, self._index.vectors)
        ]
        return _top_results(results, top_k)


class EmbeddingHybridEvidenceRetriever:
    """Hybrid BM25 + embedding retriever with metadata reranking."""

    def __init__(
        self,
        corpus: RetrievalCorpus,
        provider: EmbeddingProvider,
        embedding_index: Optional[EmbeddingIndex] = None,
        reranker: Optional["Reranker"] = None,
    ) -> None:
        self._bm25 = BM25EvidenceRetriever(corpus)
        self._embedding = EmbeddingEvidenceRetriever(corpus, provider, embedding_index)
        self._reranker = reranker or MetadataBoostReranker()

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        bm25_results = self._bm25.retrieve(task, top_k=top_k * 6)
        embedding_results = self._embedding.retrieve(task, top_k=top_k * 6)
        bm25_by_id = {result.document.document_id: result for result in bm25_results}
        embedding_by_id = {result.document.document_id: result for result in embedding_results}
        max_bm25 = max((result.score for result in bm25_results), default=Decimal("0")) or Decimal("1")
        max_embedding = max((result.score for result in embedding_results), default=Decimal("0")) or Decimal("1")
        results: List[RetrievalResult] = []
        for document_id in set(bm25_by_id) | set(embedding_by_id):
            bm25_result = bm25_by_id.get(document_id)
            embedding_result = embedding_by_id.get(document_id)
            document = bm25_result.document if bm25_result is not None else embedding_result.document
            assert document is not None
            bm25_score = (bm25_result.score / max_bm25) if bm25_result is not None else Decimal("0")
            embedding_score = (embedding_result.score / max_embedding) if embedding_result is not None else Decimal("0")
            results.append(
                RetrievalResult(
                    document=document,
                    score=(bm25_score * Decimal("0.45")) + (embedding_score * Decimal("0.35")),
                )
            )
        return self._reranker.rerank(task, results)[:top_k]


class Reranker(Protocol):
    """Reranker interface for retrieval results."""

    def rerank(self, task: DueDiligenceTask, results: Sequence[RetrievalResult]) -> Tuple[RetrievalResult, ...]:
        """Return reranked results."""


class MetadataBoostReranker:
    """Rerank results by company, period, source-type, and metric compatibility."""

    def rerank(self, task: DueDiligenceTask, results: Sequence[RetrievalResult]) -> Tuple[RetrievalResult, ...]:
        return self.rerank_metadata(results, task.company_tickers, task.fiscal_periods,
                                    task.allowed_source_types, _task_metrics(task))

    def rerank_metadata(self, results: Sequence[RetrievalResult], companies: Sequence[str],
                        periods: Sequence[str], source_types: Sequence[str],
                        metrics: Sequence[Optional[str]]) -> Tuple[RetrievalResult, ...]:
        boosted = [
            RetrievalResult(document=result.document, score=result.score + _metadata_boost(
                result.document, companies, periods, source_types, metrics))
            for result in results
        ]
        return _top_results(boosted, len(boosted))


@dataclass(frozen=True)
class EmbeddingRetrievalEvaluationResult:
    """Phase 12 retrieval report that separates proxy and optional real embeddings."""

    task_count: int
    corpus_mode: str
    corpus_document_count: int
    raw_chunk_count: int
    reports: Mapping[str, EvaluationReport]
    runs: Mapping[str, EvaluationRun]
    skipped_methods: Mapping[str, str]
    method_notes: Mapping[str, str]
    embedding_index_manifest: EmbeddingIndexManifest

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_count": self.task_count,
            "corpus_mode": self.corpus_mode,
            "corpus_document_count": self.corpus_document_count,
            "raw_chunk_count": self.raw_chunk_count,
            "reports": {method: report.to_dict() for method, report in self.reports.items()},
            "runs": {method: run.to_dict() for method, run in self.runs.items()},
            "skipped_methods": dict(self.skipped_methods),
            "method_notes": dict(self.method_notes),
            "embedding_index_manifest": self.embedding_index_manifest.to_dict(),
        }


EMBEDDING_METHOD_NOTES: Mapping[str, str] = {
    "bm25": "BM25 over the selected retrieval corpus.",
    "dense_proxy": "DeterministicTokenEmbeddingProvider; offline proxy, no neural model or API key.",
    "dense_real": "Optional real embedding provider when a local or live backend is explicitly enabled.",
    "hybrid_proxy": "BM25 plus deterministic embedding proxy with metadata reranking.",
    "hybrid_real": "BM25 plus optional real embedding provider with metadata reranking.",
    "graph": "Metadata-constrained graph retrieval over the selected corpus.",
    "full_engine": "Graph retrieval with validator-like verdict rules over the selected corpus.",
}


def run_embedding_retrieval_evaluation(
    task_set: DueDiligenceTaskSet,
    top_k: int = 5,
    corpus_mode: str = "benchmark",
    raw_corpus: object = None,
    proxy_provider: Optional[EmbeddingProvider] = None,
    real_embedding_provider: Optional[EmbeddingProvider] = None,
) -> EmbeddingRetrievalEvaluationResult:
    """Run Phase 12 retrieval evaluation with proxy and optional real embeddings."""

    corpus, raw_chunk_count = _select_corpus(task_set, corpus_mode, raw_corpus)
    proxy = proxy_provider or DeterministicTokenEmbeddingProvider()
    proxy_index = EmbeddingIndex.build(corpus, proxy)
    reranker = MetadataBoostReranker()
    runs = {
        "bm25": _build_run(task_set.tasks, "bm25", BM25EvidenceRetriever(corpus), top_k),
        "dense_proxy": _build_run(
            task_set.tasks,
            "dense_proxy",
            EmbeddingEvidenceRetriever(corpus, proxy, proxy_index),
            top_k,
        ),
        "hybrid_proxy": _build_run(
            task_set.tasks,
            "hybrid_proxy",
            EmbeddingHybridEvidenceRetriever(corpus, proxy, proxy_index, reranker),
            top_k,
        ),
        "graph": _build_run(task_set.tasks, "graph", GraphEvidenceRetriever(corpus), top_k),
        "full_engine": _build_run(task_set.tasks, "full_engine", GraphEvidenceRetriever(corpus), top_k),
    }
    skipped_methods: Dict[str, str] = {}
    if real_embedding_provider is not None and real_embedding_provider.is_available():
        real_index = EmbeddingIndex.build(corpus, real_embedding_provider)
        runs["dense_real"] = _build_run(
            task_set.tasks,
            "dense_real",
            EmbeddingEvidenceRetriever(corpus, real_embedding_provider, real_index),
            top_k,
        )
        runs["hybrid_real"] = _build_run(
            task_set.tasks,
            "hybrid_real",
            EmbeddingHybridEvidenceRetriever(corpus, real_embedding_provider, real_index, reranker),
            top_k,
        )
    else:
        reason = (
            "No real embedding provider configured."
            if real_embedding_provider is None
            else real_embedding_provider.unavailable_reason()
        )
        skipped_methods["dense_real"] = reason
        skipped_methods["hybrid_real"] = reason
    reports = {
        method: evaluate_run(run, task_set.tasks, evidence_recall_k=top_k)
        for method, run in runs.items()
    }
    return EmbeddingRetrievalEvaluationResult(
        task_count=len(task_set.tasks),
        corpus_mode=corpus_mode,
        corpus_document_count=len(corpus.documents),
        raw_chunk_count=raw_chunk_count,
        reports=reports,
        runs=runs,
        skipped_methods=skipped_methods,
        method_notes=EMBEDDING_METHOD_NOTES,
        embedding_index_manifest=proxy_index.manifest,
    )


def _load_sentence_transformer(model_name: str) -> object:
    cached = _SENTENCE_TRANSFORMER_CACHE.get(model_name)
    if cached is not None:
        return cached
    from sentence_transformers import SentenceTransformer  # type: ignore

    model = SentenceTransformer(model_name)
    _SENTENCE_TRANSFORMER_CACHE[model_name] = model
    return model


def _embed_deterministic(text: str, dimension: int) -> Tuple[float, ...]:
    vector = [0.0] * dimension
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(round(value / norm, 8) for value in vector)


def _tokenize(text: str) -> Tuple[str, ...]:
    return tuple(match.group(0).lower() for match in TOKEN_PATTERN.finditer(text.replace("_", " ")))


def _query_text(task: DueDiligenceTask) -> str:
    return " ".join((task.claim_text, task.question, " ".join(task.company_tickers), " ".join(task.fiscal_periods)))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _metadata_boost(document, companies: Sequence[str], periods: Sequence[str],
                    source_types: Sequence[str], metrics: Sequence[Optional[str]]) -> Decimal:
    score = Decimal("0")
    if document.company_ticker in companies:
        score += Decimal("0.15")
    if document.fiscal_period in periods:
        score += Decimal("0.15")
    if document.source_type in source_types:
        score += Decimal("0.12")
    if document.metric in metrics:
        score += Decimal("0.12")
    return score


def _task_metrics(task: DueDiligenceTask) -> Tuple[Optional[str], ...]:
    metrics = [requirement.metric for requirement in task.expected_evidence]
    metrics.extend(check.metric for check in task.numeric_checks)
    return tuple(metrics)


def _top_results(results: Iterable[RetrievalResult], top_k: int) -> Tuple[RetrievalResult, ...]:
    positive_results = [result for result in results if result.score > Decimal("0")]
    return tuple(
        sorted(
            positive_results,
            key=lambda result: (
                result.score,
                not result.document.is_distractor,
                result.document.evidence_key,
            ),
            reverse=True,
        )[:top_k]
    )


def _decimal_score(score: float) -> Decimal:
    return Decimal(str(round(score, 8)))


def _corpus_hash(corpus: RetrievalCorpus) -> str:
    return _hash("|".join(f"{document.document_id}:{document.text}" for document in corpus.documents))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
