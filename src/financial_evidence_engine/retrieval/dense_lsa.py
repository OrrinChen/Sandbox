"""CPU dense retrieval baseline: corpus TF-IDF SVD and a metadata-rerank ablation.

The published 60-task verdict numbers are not computed here. This module
measures evidence-retrieval ratios for BM25, the existing token-hash dense
proxy, and a corpus-fit TF-IDF singular-vector embedding, each with and
without the existing metadata reranker where noted.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from financial_evidence_engine.evaluation.metrics import (
    EvaluationRun,
    TaskPrediction,
    _matched_requirements,
    evaluate_run,
)
from financial_evidence_engine.evaluation.task_set import DueDiligenceTask, DueDiligenceTaskSet
from financial_evidence_engine.retrieval.embeddings import (
    DeterministicTokenEmbeddingProvider,
    EmbeddingEvidenceRetriever,
    MetadataBoostReranker,
    _query_text,
    _tokenize,
)
from financial_evidence_engine.retrieval.real_baselines import (
    BM25EvidenceRetriever,
    RetrievalCorpus,
    RetrievalResult,
    _decimal_score,
    _top_results,
    build_retrieval_corpus,
)


REPORTED_METRICS: Tuple[str, ...] = (
    "evidence_recall_at_k",
    "citation_exactness",
    "fiscal_period_correctness",
    "entity_correctness",
)

METRIC_LABELS: Mapping[str, str] = {
    "evidence_recall_at_k": "Evidence recall@k",
    "citation_exactness": "Citation exactness",
    "fiscal_period_correctness": "Fiscal-period correctness",
    "entity_correctness": "Entity correctness",
}

METRICS_OMITTED_NOTE = (
    "This ablation does not report verdict accuracy, numeric correctness, "
    "contradiction detection, unsupported-claim rate, answer faithfulness, "
    "memo usefulness, latency, or cost. Predictions are marked not_scored. "
    "The published full-engine 83.3% and BM25 66.7% figures are verdict "
    "accuracies from the existing benchmark, not outputs of this run."
)

TF_FORMULA = "1 + ln(term_count) for term_count > 0"
IDF_FORMULA = "ln((document_count + 1) / (document_frequency + 1)) + 1"


@dataclass(frozen=True)
class DenseLsaConfig:
    """Configuration for the CPU TF-IDF SVD retrieval experiment."""

    experiment_id: str = "dense_lsa_rerank_ablation"
    corpus_mode: str = "benchmark"
    top_k: int = 5
    candidate_pool_multiplier: int = 6
    dimension: int = 32
    max_features: int = 2000
    min_df: int = 2
    subspace_iterations: int = 15
    provider_id: str = "corpus-tfidf-svd-subspace-v1"
    proxy_dimension: int = 64

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "DenseLsaConfig":
        lsa = payload.get("lsa") or {}
        if not isinstance(lsa, Mapping):
            raise ValueError("lsa config section must be a mapping")
        return cls(
            experiment_id=str(payload.get("experiment_id", "dense_lsa_rerank_ablation")),
            corpus_mode=str(payload.get("corpus_mode", "benchmark")),
            top_k=int(payload.get("top_k", 5)),
            candidate_pool_multiplier=int(payload.get("candidate_pool_multiplier", 6)),
            dimension=int(lsa.get("dimension", 32)),
            max_features=int(lsa.get("max_features", 2000)),
            min_df=int(lsa.get("min_df", 2)),
            subspace_iterations=int(lsa.get("subspace_iterations", 15)),
            provider_id=str(lsa.get("provider_id", "corpus-tfidf-svd-subspace-v1")),
            proxy_dimension=int(payload.get("proxy_dimension", 64)),
        )


def load_dense_lsa_config(path: Path) -> DenseLsaConfig:
    """Load the dense LSA experiment config from YAML."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("dense LSA config must be a mapping")
    return DenseLsaConfig.from_mapping(payload)


class CorpusTfidfSvdEmbeddingProvider:
    """Dense vectors from corpus TF-IDF and subspace-iteration SVD.

    The first ``embed_texts`` call fits IDF and the singular subspace on that
    batch. Later calls project text into the fitted space. Document text must
    be embedded before queries.
    """

    backend_kind = "lsa"

    def __init__(
        self,
        dimension: int = 32,
        max_features: int = 2000,
        min_df: int = 2,
        subspace_iterations: int = 15,
        provider_id: str = "corpus-tfidf-svd-subspace-v1",
    ) -> None:
        if dimension < 1:
            raise ValueError("dimension must be positive")
        if max_features < 1:
            raise ValueError("max_features must be positive")
        if min_df < 1:
            raise ValueError("min_df must be positive")
        if subspace_iterations < 1:
            raise ValueError("subspace_iterations must be positive")
        self.dimension = dimension
        self.max_features = max_features
        self.min_df = min_df
        self.subspace_iterations = subspace_iterations
        self.provider_id = provider_id
        self._fitted = False
        self.vocabulary_size = 0
        self.fitted_dimension = 0
        self._token_index: Dict[str, int] = {}
        self._idf: Tuple[float, ...] = ()
        self._components: Tuple[Tuple[float, ...], ...] = ()

    def is_available(self) -> bool:
        return True

    def unavailable_reason(self) -> str:
        return ""

    def embed_texts(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        if not self._fitted:
            return self._fit_transform(texts)
        return tuple(self._project_text(text) for text in texts)

    def _fit_transform(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        tokenized = tuple(_tokenize(text) for text in texts)
        document_frequency: Dict[str, int] = {}
        for tokens in tokenized:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1
        eligible = [
            (token, frequency)
            for token, frequency in document_frequency.items()
            if frequency >= self.min_df
        ]
        eligible.sort(key=lambda item: (-item[1], item[0]))
        vocabulary = tuple(token for token, _frequency in eligible[: self.max_features])
        self._token_index = {token: index for index, token in enumerate(vocabulary)}
        document_count = len(tokenized)
        self._idf = tuple(
            math.log((document_count + 1) / (document_frequency[token] + 1)) + 1.0
            for token in vocabulary
        )
        rows = tuple(self._sparse_row(tokens) for tokens in tokenized)
        components = _subspace_components(
            rows=rows,
            vocab_size=len(vocabulary),
            dimension=min(self.dimension, len(vocabulary), max(document_count, 1)),
            iterations=self.subspace_iterations,
        )
        self._components = components
        self.vocabulary_size = len(vocabulary)
        self.fitted_dimension = len(components)
        self._fitted = True
        return tuple(_project_row(row, components) for row in rows)

    def _project_text(self, text: str) -> Tuple[float, ...]:
        return _project_row(self._sparse_row(_tokenize(text)), self._components)

    def _sparse_row(self, tokens: Sequence[str]) -> Dict[int, float]:
        counts: Dict[str, int] = {}
        for token in tokens:
            if token in self._token_index:
                counts[token] = counts.get(token, 0) + 1
        row: Dict[int, float] = {}
        for token, count in counts.items():
            index = self._token_index[token]
            row[index] = (1.0 + math.log(count)) * self._idf[index]
        return row


@dataclass(frozen=True)
class RetrievalAblationResult:
    """Retrieval-metric ablation. Verdict accuracy is intentionally absent."""

    experiment_id: str
    status: str
    setup: Mapping[str, object]
    method_order: Tuple[str, ...]
    reported_metrics: Mapping[str, Mapping[str, str]]
    evidence_recall_hits: Mapping[str, int]
    evidence_recall_total: Mapping[str, int]
    evidence_recall_at_1: Mapping[str, str]
    evidence_recall_at_1_hits: Mapping[str, int]
    method_notes: Mapping[str, str]
    command: str
    metrics_omitted_note: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status,
            "setup": dict(self.setup),
            "method_order": list(self.method_order),
            "reported_metrics": {
                method: dict(metrics) for method, metrics in self.reported_metrics.items()
            },
            "evidence_recall_at_1": dict(self.evidence_recall_at_1),
            "evidence_recall_at_1_hits": dict(self.evidence_recall_at_1_hits),
            "evidence_recall_hits": dict(self.evidence_recall_hits),
            "evidence_recall_total": dict(self.evidence_recall_total),
            "method_notes": dict(self.method_notes),
            "command": self.command,
            "metrics_omitted_note": self.metrics_omitted_note,
        }


def run_dense_lsa_experiment(
    task_set: DueDiligenceTaskSet,
    config: Optional[DenseLsaConfig] = None,
    command: str = "python3 scripts/run_dense_lsa_experiment.py --config configs/dense_lsa.yaml",
) -> RetrievalAblationResult:
    """Run BM25, dense proxy, TF-IDF SVD, and metadata-rerank variants."""

    config = config or DenseLsaConfig()
    if config.corpus_mode != "benchmark":
        raise ValueError("dense LSA experiment supports corpus_mode='benchmark' only")
    corpus = build_retrieval_corpus(task_set)
    provider = CorpusTfidfSvdEmbeddingProvider(
        dimension=config.dimension,
        max_features=config.max_features,
        min_df=config.min_df,
        subspace_iterations=config.subspace_iterations,
        provider_id=config.provider_id,
    )
    dense_retriever = TfidfSvdEvidenceRetriever(corpus, provider)
    proxy_retriever = EmbeddingEvidenceRetriever(
        corpus,
        DeterministicTokenEmbeddingProvider(dimension=config.proxy_dimension),
    )
    bm25_retriever = BM25EvidenceRetriever(corpus)
    reranker = MetadataBoostReranker()
    multiplier = config.candidate_pool_multiplier
    retrievers = {
        "bm25": bm25_retriever,
        "bm25_metadata_rerank": _RerankedRetriever(bm25_retriever, reranker, multiplier),
        "dense_proxy": proxy_retriever,
        "dense_lsa": dense_retriever,
        "dense_lsa_metadata_rerank": _RerankedRetriever(dense_retriever, reranker, multiplier),
    }
    method_order = tuple(retrievers)
    reported: Dict[str, Mapping[str, str]] = {}
    hits: Dict[str, int] = {}
    totals: Dict[str, int] = {}
    recall_at_1: Dict[str, str] = {}
    recall_at_1_hits: Dict[str, int] = {}
    for method, retriever in retrievers.items():
        run = _evaluation_run(task_set.tasks, method, retriever, config.top_k)
        report = evaluate_run(run, task_set.tasks, evidence_recall_k=config.top_k)
        reported[method] = {
            name: str(report.metrics[name]) for name in REPORTED_METRICS
        }
        hit_count, total_count = _evidence_recall_counts(task_set.tasks, run, config.top_k)
        hits[method] = hit_count
        totals[method] = total_count
        ratio = Decimal(hit_count) / Decimal(total_count) if total_count else Decimal("0")
        if str(ratio) != reported[method]["evidence_recall_at_k"]:
            raise RuntimeError("evidence recall counts do not match EvaluationReport")
        report_at_1 = evaluate_run(run, task_set.tasks, evidence_recall_k=1)
        recall_at_1[method] = str(report_at_1.metrics["evidence_recall_at_k"])
        hit_count_at_1, _total_at_1 = _evidence_recall_counts(task_set.tasks, run, 1)
        recall_at_1_hits[method] = hit_count_at_1
        ratio_at_1 = Decimal(hit_count_at_1) / Decimal(total_count) if total_count else Decimal("0")
        if str(ratio_at_1) != recall_at_1[method]:
            raise RuntimeError("evidence recall@1 counts do not match EvaluationReport")
    pool = config.top_k * config.candidate_pool_multiplier
    setup: Dict[str, object] = {
        "corpus_mode": config.corpus_mode,
        "task_set_id": task_set.task_set_id,
        "task_count": len(task_set.tasks),
        "corpus_document_count": len(corpus.documents),
        "top_k": config.top_k,
        "candidate_pool_multiplier": config.candidate_pool_multiplier,
        "candidate_pool_size_cap": pool,
        "provider_id": provider.provider_id,
        "embedding": (
            "Sublinear TF-IDF fit on benchmark document text only, then a "
            f"{config.subspace_iterations}-step subspace iteration toward the "
            "leading right singular vectors. Query and document vectors are the "
            "L2-normalized projections, rounded to 8 decimal places. This is not "
            "a LAPACK SVD and not a neural embedding."
        ),
        "tf_formula": TF_FORMULA,
        "idf_formula": IDF_FORMULA,
        "requested_dimension": config.dimension,
        "fitted_dimension": provider.fitted_dimension,
        "vocabulary_size": provider.vocabulary_size,
        "max_features": config.max_features,
        "min_df": config.min_df,
        "subspace_iterations": config.subspace_iterations,
        "proxy_provider_id": "deterministic-token-v1",
        "proxy_dimension": config.proxy_dimension,
        "reranker": (
            "MetadataBoostReranker adds company +0.15, fiscal period +0.15, "
            "allowed source type +0.12, and metric +0.12 to the base retrieval "
            "score inside the positive-score candidate pool, then truncates to top_k."
        ),
        "corpus_construction": (
            "Same constructed benchmark corpus as the published verdict benchmark: "
            "gold evidence specifications plus known distractors. Claim text is "
            "copied into both gold and distractor document text."
        ),
        "implementation": "Pure Python float arithmetic. No BLAS and no neural model.",
        "recall_at_1_note": (
            "evidence_recall_at_1 is the same ranked list cut to the first hit. "
            "It is a second cutoff, not a separate retrieval system. Recall@5 can "
            "sit near the ceiling because top_k is 5 and the task set has 200 gold "
            "evidence rows across 60 tasks."
        ),
    }
    return RetrievalAblationResult(
        experiment_id=config.experiment_id,
        status="ran",
        setup=setup,
        method_order=method_order,
        reported_metrics=reported,
        evidence_recall_hits=hits,
        evidence_recall_total=totals,
        evidence_recall_at_1=recall_at_1,
        evidence_recall_at_1_hits=recall_at_1_hits,
        method_notes=_method_notes(config),
        command=command,
        metrics_omitted_note=METRICS_OMITTED_NOTE,
    )


def render_ablation_markdown(result: RetrievalAblationResult) -> str:
    """Render the ablation report from measured values only."""

    setup = result.setup
    header = (
        f"# {result.experiment_id}",
        "",
        f"Status: `{result.status}`",
        "",
        "Generated by:",
        "",
        "```bash",
        result.command,
        "```",
        "",
        "## Setup",
        "",
        f"- Tasks: `{setup['task_count']}`",
        f"- Corpus mode: `{setup['corpus_mode']}`",
        f"- Documents: `{setup['corpus_document_count']}`",
        f"- Task set: `{setup['task_set_id']}`",
        f"- top_k: `{setup['top_k']}`",
        f"- Rerank candidate pool: up to `{setup['candidate_pool_size_cap']}` positive-score hits "
        f"(`top_k * {setup['candidate_pool_multiplier']}`)",
        f"- Provider: `{setup['provider_id']}`",
        f"- Embedding: {setup['embedding']}",
        f"- TF: `{setup['tf_formula']}`",
        f"- IDF: `{setup['idf_formula']}`",
        f"- Requested dimension: `{setup['requested_dimension']}`",
        f"- Fitted dimension: `{setup['fitted_dimension']}`",
        f"- Vocabulary size: `{setup['vocabulary_size']}`",
        f"- max_features: `{setup['max_features']}`",
        f"- min_df: `{setup['min_df']}`",
        f"- Subspace iterations: `{setup['subspace_iterations']}`",
        f"- Dense proxy reference: `{setup['proxy_provider_id']}` dimension `{setup['proxy_dimension']}`",
        f"- Reranker: {setup['reranker']}",
        f"- Corpus: {setup['corpus_construction']}",
        f"- Implementation: {setup['implementation']}",
        "",
        result.metrics_omitted_note,
        "",
        str(setup["recall_at_1_note"]),
        "",
        "Citation exactness equals evidence recall in this run because every retrieved row is marked cited.",
        "",
        "## Results",
        "",
        "Exact ratios come from `evaluate_run`. Evidence recall@5 is also shown as hits/total.",
        "",
        "| Method | Evidence recall@5 | Evidence recall@1 | Citation exactness | Fiscal-period correctness | Entity correctness |",
        "| --- | --- | --- | --- | --- | --- |",
    )
    rows = []
    for method in result.method_order:
        metrics = result.reported_metrics[method]
        hits = result.evidence_recall_hits[method]
        total = result.evidence_recall_total[method]
        hits_at_1 = result.evidence_recall_at_1_hits[method]
        rows.append(
            "| {method} | {hits}/{total} = `{recall}` | {hits_at_1}/{total} = `{recall_at_1}` | `{citation}` | `{period}` | `{entity}` |".format(
                method=method,
                hits=hits,
                total=total,
                recall=metrics["evidence_recall_at_k"],
                hits_at_1=hits_at_1,
                recall_at_1=result.evidence_recall_at_1[method],
                citation=metrics["citation_exactness"],
                period=metrics["fiscal_period_correctness"],
                entity=metrics["entity_correctness"],
            )
        )
    notes = ["", "## Method notes", ""]
    for method in result.method_order:
        notes.append(f"- `{method}`: {result.method_notes[method]}")
    deltas = [
        "",
        "## Rerank deltas",
        "",
        "Differences of the ratios above. A zero difference means the metric did not move.",
        "",
    ]
    deltas.extend(_delta_lines(result, "bm25_metadata_rerank", "bm25"))
    deltas.extend(_delta_lines(result, "dense_lsa_metadata_rerank", "dense_lsa"))
    lines = list(header) + rows + notes + deltas + [""]
    return "\n".join(lines)


def write_ablation_artifacts(result: RetrievalAblationResult, json_path: Path, markdown_path: Path) -> None:
    """Write the JSON and Markdown artifacts for one ablation run."""

    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    json_path.write_text(_stable_json(payload), encoding="utf-8")
    markdown_path.write_text(render_ablation_markdown(result), encoding="utf-8")


class TfidfSvdEvidenceRetriever:
    """Cosine retriever over fitted TF-IDF singular-vector embeddings."""

    def __init__(self, corpus: RetrievalCorpus, provider: CorpusTfidfSvdEmbeddingProvider) -> None:
        self._corpus = corpus
        self._provider = provider
        self._document_vectors = provider.embed_texts(tuple(document.text for document in corpus.documents))

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        query_vector = self._provider.embed_texts((_query_text(task),))[0]
        return _top_results(
            (
                RetrievalResult(
                    document=document,
                    score=_decimal_score(_cosine(query_vector, document_vector)),
                )
                for document, document_vector in zip(self._corpus.documents, self._document_vectors)
            ),
            top_k=top_k,
        )


class _RerankedRetriever:
    """Take a wider base pool, apply a reranker, and cut back to top_k."""

    def __init__(self, base: object, reranker: MetadataBoostReranker, multiplier: int) -> None:
        self._base = base
        self._reranker = reranker
        self._multiplier = multiplier

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        candidates = self._base.retrieve(task, top_k=top_k * self._multiplier)
        return self._reranker.rerank(task, candidates)[:top_k]


def _method_notes(config: DenseLsaConfig) -> Mapping[str, str]:
    pool = config.top_k * config.candidate_pool_multiplier
    return {
        "bm25": (
            f"BM25EvidenceRetriever, top_k={config.top_k}, no metadata rerank. "
            "Same retriever class as the published BM25 verdict baseline."
        ),
        "bm25_metadata_rerank": (
            f"BM25 scores on up to {pool} positive-score candidates, then MetadataBoostReranker, "
            f"truncated to top_k={config.top_k}. Boosts are added to raw BM25 scores."
        ),
        "dense_proxy": (
            f"Existing DeterministicTokenEmbeddingProvider dimension {config.proxy_dimension}: "
            "one hashed bucket per token, no IDF. Offline dense proxy, not a neural embedding, "
            "and not the published 66.7% verdict accuracy."
        ),
        "dense_lsa": (
            f"Cosine over corpus TF-IDF singular vectors, dimension requested {config.dimension}, "
            f"{config.subspace_iterations} subspace iterations, no metadata rerank."
        ),
        "dense_lsa_metadata_rerank": (
            f"Same TF-IDF singular-vector cosine scores on up to {pool} candidates, then "
            "MetadataBoostReranker, truncated to top_k. Boosts are added to cosine scores."
        ),
    }


def _evaluation_run(
    tasks: Tuple[DueDiligenceTask, ...],
    method: str,
    retriever: object,
    top_k: int,
) -> EvaluationRun:
    predictions = tuple(
        _prediction(task, method, retriever.retrieve(task, top_k=top_k))
        for task in tasks
    )
    return EvaluationRun(method=method, predictions=predictions)


def _prediction(
    task: DueDiligenceTask,
    method: str,
    results: Tuple[RetrievalResult, ...],
) -> TaskPrediction:
    return TaskPrediction(
        task_id=task.task_id,
        method=method,
        predicted_verdict="not_scored",
        retrieved_evidence=tuple(result.document.to_retrieved_evidence(cited=True) for result in results),
        numeric_check_statuses={check.check_id: "not_scored" for check in task.numeric_checks},
        latency_ms=Decimal("0"),
        cost_usd=Decimal("0"),
        answer_text="",
        memo_sections=(),
    )


def _evidence_recall_counts(
    tasks: Sequence[DueDiligenceTask],
    run: EvaluationRun,
    top_k: int,
) -> Tuple[int, int]:
    by_task_id = {prediction.task_id: prediction for prediction in run.predictions}
    hits = 0
    total = 0
    for task in tasks:
        total += len(task.expected_evidence)
        prediction = by_task_id[task.task_id]
        hits += len(_matched_requirements(task.expected_evidence, prediction.retrieved_evidence[:top_k]))
    return hits, total


def _delta_lines(result: RetrievalAblationResult, left: str, right: str) -> List[str]:
    if left not in result.reported_metrics or right not in result.reported_metrics:
        return []
    lines = []
    for label, left_value, right_value in (
        (
            "evidence recall@5",
            result.reported_metrics[left]["evidence_recall_at_k"],
            result.reported_metrics[right]["evidence_recall_at_k"],
        ),
        (
            "evidence recall@1",
            result.evidence_recall_at_1[left],
            result.evidence_recall_at_1[right],
        ),
        (
            "entity correctness",
            result.reported_metrics[left]["entity_correctness"],
            result.reported_metrics[right]["entity_correctness"],
        ),
    ):
        difference = Decimal(left_value) - Decimal(right_value)
        rendered = "0" if difference == 0 else format(difference, "f")
        lines.append(f"- `{left}` {label} minus `{right}` {label} = `{rendered}`")
    return lines


def _subspace_components(
    rows: Sequence[Mapping[int, float]],
    vocab_size: int,
    dimension: int,
    iterations: int,
) -> Tuple[Tuple[float, ...], ...]:
    if vocab_size == 0 or dimension == 0 or not rows:
        return ()
    raw = []
    for component_index in range(dimension):
        vector = []
        for feature_index in range(vocab_size):
            digest = hashlib.sha256(f"{component_index}:{feature_index}".encode("utf-8")).digest()
            vector.append(1.0 if digest[0] % 2 == 0 else -1.0)
        raw.append(vector)
    components = _gram_schmidt(raw)
    for _iteration in range(iterations):
        projected = _multiply_rows(rows, components)
        updated = _multiply_rows_transpose(rows, projected, vocab_size, len(components))
        components = _gram_schmidt(updated)
    return tuple(tuple(value for value in component) for component in components)


def _multiply_rows(
    rows: Sequence[Mapping[int, float]],
    components: Sequence[Sequence[float]],
) -> List[List[float]]:
    width = len(components)
    projected: List[List[float]] = []
    for row in rows:
        coords = [0.0] * width
        for index in sorted(row):
            value = row[index]
            for component_index in range(width):
                coords[component_index] += value * components[component_index][index]
        projected.append(coords)
    return projected


def _multiply_rows_transpose(
    rows: Sequence[Mapping[int, float]],
    projected: Sequence[Sequence[float]],
    vocab_size: int,
    width: int,
) -> List[List[float]]:
    components = [[0.0] * vocab_size for _component in range(width)]
    for row_index, row in enumerate(rows):
        left = projected[row_index]
        for index in sorted(row):
            value = row[index]
            for component_index in range(width):
                components[component_index][index] += value * left[component_index]
    return components


def _gram_schmidt(vectors: Sequence[Sequence[float]]) -> List[List[float]]:
    orthogonal: List[List[float]] = []
    width = len(vectors[0]) if vectors else 0
    for component_index, vector in enumerate(vectors):
        current = [value for value in vector]
        for previous in orthogonal:
            dot = sum(left * right for left, right in zip(current, previous))
            current = [value - dot * basis for value, basis in zip(current, previous)]
        norm = math.sqrt(sum(value * value for value in current))
        if norm < 1e-12:
            current = [0.0] * width
            current[component_index % width] = 1.0
            for previous in orthogonal:
                dot = sum(left * right for left, right in zip(current, previous))
                current = [value - dot * basis for value, basis in zip(current, previous)]
            norm = math.sqrt(sum(value * value for value in current)) or 1.0
        pivot = 0
        pivot_magnitude = abs(current[0]) if current else 0.0
        for index, value in enumerate(current):
            magnitude = abs(value)
            if magnitude > pivot_magnitude:
                pivot = index
                pivot_magnitude = magnitude
        if current and current[pivot] < 0.0:
            norm = -norm
        orthogonal.append([value / norm for value in current])
    return orthogonal


def _project_row(
    row: Mapping[int, float],
    components: Sequence[Sequence[float]],
) -> Tuple[float, ...]:
    if not components:
        return ()
    coords = [0.0] * len(components)
    for index in sorted(row):
        value = row[index]
        for component_index, component in enumerate(components):
            coords[component_index] += value * component[index]
    return _normalize(coords)


def _normalize(vector: Sequence[float]) -> Tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return tuple(0.0 for _value in vector)
    return tuple(round(value / norm, 8) for value in vector)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _stable_json(payload: Mapping[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
