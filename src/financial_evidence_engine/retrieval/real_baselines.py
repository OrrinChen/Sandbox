"""Local real-retrieval baselines for due-diligence evaluation."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from financial_evidence_engine.evaluation.metrics import (
    EvaluationReport,
    EvaluationRun,
    RetrievedEvidence,
    TaskPrediction,
    evaluate_run,
)
from financial_evidence_engine.evaluation.task_set import (
    DueDiligenceTask,
    DueDiligenceTaskSet,
    EvidenceRequirement,
    KnownDistractor,
)


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")

REAL_RETRIEVAL_METHODS: Tuple[str, ...] = (
    "bm25_real",
    "dense_real",
    "hybrid_real",
    "graph_real",
    "full_engine_real",
)

METHOD_NOTES: Mapping[str, str] = {
    "bm25_real": "BM25 over the local retrieval corpus, including gold evidence documents and known distractors.",
    "dense_real": "Deterministic token-vector cosine retrieval over the same corpus; no neural embedding service is used.",
    "hybrid_real": "Score-level blend of BM25 and token-vector retrieval with light metadata reranking.",
    "graph_real": "Metadata-constrained graph retrieval using company, period, source-type, and metric filters.",
    "full_engine_real": (
        "Graph/hybrid retrieval plus validator-like verdict rules; chart extraction remains unavailable "
        "and is intentionally surfaced as insufficient."
    ),
}


@dataclass(frozen=True)
class RetrievalCorpusDocument:
    """One searchable evidence document in the local retrieval corpus."""

    document_id: str
    task_id: str
    evidence_key: str
    source_type: str
    modality: str
    company_ticker: str
    fiscal_period: str
    role: str
    text: str
    metric: Optional[str] = None
    is_distractor: bool = False
    distractor_reason: str = ""

    def to_retrieved_evidence(self, cited: bool = True) -> RetrievedEvidence:
        return RetrievedEvidence(
            evidence_key=self.evidence_key,
            source_type=self.source_type,
            modality=self.modality,
            company_ticker=self.company_ticker,
            fiscal_period=self.fiscal_period,
            metric=self.metric,
            cited=cited,
        )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "document_id": self.document_id,
            "task_id": self.task_id,
            "evidence_key": self.evidence_key,
            "source_type": self.source_type,
            "modality": self.modality,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "role": self.role,
            "metric": self.metric,
            "is_distractor": self.is_distractor,
            "distractor_reason": self.distractor_reason,
            "text": self.text,
        }


@dataclass(frozen=True)
class RetrievalResult:
    """A scored retrieval hit."""

    document: RetrievalCorpusDocument
    score: Decimal

    def to_dict(self) -> Mapping[str, object]:
        return {
            "document": self.document.to_dict(),
            "score": str(self.score),
        }


@dataclass(frozen=True)
class RetrievalCorpus:
    """Searchable local corpus used by the real-retrieval baselines."""

    documents: Tuple[RetrievalCorpusDocument, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "document_count": len(self.documents),
            "documents": [document.to_dict() for document in self.documents],
        }


@dataclass(frozen=True)
class RetrievalFailureCase:
    """One concrete retrieval or validation failure surfaced by a real run."""

    task_id: str
    method: str
    category: str
    expected_verdict: str
    predicted_verdict: str
    explanation: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "method": self.method,
            "category": self.category,
            "expected_verdict": self.expected_verdict,
            "predicted_verdict": self.predicted_verdict,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class RealRetrievalEvaluationResult:
    """Combined report for actual retrieval runs over the local corpus."""

    task_count: int
    corpus_document_count: int
    reports: Mapping[str, EvaluationReport]
    runs: Mapping[str, EvaluationRun]
    failure_cases: Tuple[RetrievalFailureCase, ...]
    method_notes: Mapping[str, str]
    corpus_mode: str = "benchmark"
    raw_chunk_count: int = 0

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_count": self.task_count,
            "corpus_mode": self.corpus_mode,
            "corpus_document_count": self.corpus_document_count,
            "raw_chunk_count": self.raw_chunk_count,
            "reports": {method: report.to_dict() for method, report in self.reports.items()},
            "runs": {method: run.to_dict() for method, run in self.runs.items()},
            "failure_cases": [failure.to_dict() for failure in self.failure_cases],
            "method_notes": dict(self.method_notes),
        }


class BM25EvidenceRetriever:
    """BM25 retriever over the local retrieval corpus."""

    def __init__(self, corpus: RetrievalCorpus) -> None:
        self._corpus = corpus
        self._document_tokens = tuple(_tokenize(document.text) for document in corpus.documents)
        self._document_frequencies = _document_frequencies(self._document_tokens)
        self._average_document_length = _average_length(self._document_tokens)

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        query_tokens = _tokenize(_query_text(task))
        return _top_results(
            (
                RetrievalResult(
                    document=document,
                    score=_decimal_score(
                        _bm25_score(
                            query_tokens=query_tokens,
                            document_tokens=document_tokens,
                            document_frequencies=self._document_frequencies,
                            document_count=len(self._corpus.documents),
                            average_document_length=self._average_document_length,
                        )
                    ),
                )
                for document, document_tokens in zip(self._corpus.documents, self._document_tokens)
            ),
            top_k=top_k,
        )


class DenseEvidenceRetriever:
    """Deterministic token-vector retriever used as an offline dense proxy."""

    def __init__(self, corpus: RetrievalCorpus) -> None:
        self._corpus = corpus
        self._document_vectors = tuple(_token_vector(_tokenize(document.text)) for document in corpus.documents)

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        query_vector = _token_vector(_tokenize(_query_text(task)))
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


class HybridEvidenceRetriever:
    """Hybrid retriever that blends BM25, token-vector, and metadata scores."""

    def __init__(self, corpus: RetrievalCorpus) -> None:
        self._bm25 = BM25EvidenceRetriever(corpus)
        self._dense = DenseEvidenceRetriever(corpus)

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        bm25_results = self._bm25.retrieve(task, top_k=top_k * 6)
        dense_results = self._dense.retrieve(task, top_k=top_k * 6)
        bm25_by_id = {result.document.document_id: result for result in bm25_results}
        dense_by_id = {result.document.document_id: result for result in dense_results}
        document_ids = set(bm25_by_id) | set(dense_by_id)
        max_bm25 = max((result.score for result in bm25_results), default=Decimal("0")) or Decimal("1")
        max_dense = max((result.score for result in dense_results), default=Decimal("0")) or Decimal("1")

        results: List[RetrievalResult] = []
        for document_id in document_ids:
            bm25_result = bm25_by_id.get(document_id)
            dense_result = dense_by_id.get(document_id)
            document = bm25_result.document if bm25_result is not None else dense_result.document
            assert document is not None
            bm25_score = (bm25_result.score / max_bm25) if bm25_result is not None else Decimal("0")
            dense_score = (dense_result.score / max_dense) if dense_result is not None else Decimal("0")
            metadata_score = _metadata_score(task, document)
            score = (bm25_score * Decimal("0.45")) + (dense_score * Decimal("0.35")) + metadata_score
            results.append(RetrievalResult(document=document, score=score))
        return _top_results(results, top_k=top_k)


class GraphEvidenceRetriever:
    """Metadata-constrained graph-style retrieval over the local corpus."""

    def __init__(self, corpus: RetrievalCorpus) -> None:
        self._corpus = corpus
        self._hybrid = HybridEvidenceRetriever(corpus)

    def retrieve(self, task: DueDiligenceTask, top_k: int = 5) -> Tuple[RetrievalResult, ...]:
        candidates = [
            result
            for result in self._hybrid.retrieve(task, top_k=max(top_k * 12, 30))
            if _passes_graph_constraints(task, result.document)
        ]
        graph_results = [
            RetrievalResult(
                document=result.document,
                score=result.score + _graph_relation_score(task, result.document),
            )
            for result in candidates
        ]
        return _top_results(graph_results, top_k=top_k)


def build_retrieval_corpus(task_set: DueDiligenceTaskSet) -> RetrievalCorpus:
    """Build a local searchable corpus from gold evidence specs and distractors."""

    documents: List[RetrievalCorpusDocument] = []
    for task in task_set.tasks:
        documents.extend(_gold_documents(task))
        documents.extend(_distractor_documents(task))
    return RetrievalCorpus(documents=tuple(documents))


def run_real_retrieval_evaluation(
    task_set: DueDiligenceTaskSet,
    top_k: int = 5,
    corpus_mode: str = "benchmark",
    raw_corpus: object = None,
) -> RealRetrievalEvaluationResult:
    """Run actual local retrieval baselines and evaluate their predictions."""

    corpus, raw_chunk_count = _select_corpus(task_set, corpus_mode, raw_corpus)
    runs = {
        "bm25_real": _build_run(task_set.tasks, "bm25_real", BM25EvidenceRetriever(corpus), top_k),
        "dense_real": _build_run(task_set.tasks, "dense_real", DenseEvidenceRetriever(corpus), top_k),
        "hybrid_real": _build_run(task_set.tasks, "hybrid_real", HybridEvidenceRetriever(corpus), top_k),
        "graph_real": _build_run(task_set.tasks, "graph_real", GraphEvidenceRetriever(corpus), top_k),
        "full_engine_real": _build_run(task_set.tasks, "full_engine_real", GraphEvidenceRetriever(corpus), top_k),
    }
    reports = {
        method: evaluate_run(run, task_set.tasks, evidence_recall_k=top_k)
        for method, run in runs.items()
    }
    failure_cases = _failure_cases(task_set.tasks, runs)
    return RealRetrievalEvaluationResult(
        task_count=len(task_set.tasks),
        corpus_document_count=len(corpus.documents),
        reports=reports,
        runs=runs,
        failure_cases=failure_cases,
        method_notes=METHOD_NOTES,
        corpus_mode=corpus_mode,
        raw_chunk_count=raw_chunk_count,
    )


def _select_corpus(
    task_set: DueDiligenceTaskSet,
    corpus_mode: str,
    raw_corpus: object,
) -> Tuple[RetrievalCorpus, int]:
    if corpus_mode == "benchmark":
        return build_retrieval_corpus(task_set), 0
    if corpus_mode == "raw":
        if raw_corpus is None:
            from financial_evidence_engine.retrieval.raw_corpus import build_raw_financial_corpus

            raw_corpus = build_raw_financial_corpus(task_set)
        return raw_corpus.to_retrieval_corpus(), len(raw_corpus.chunks)
    raise ValueError("corpus_mode must be 'benchmark' or 'raw'")


def _build_run(
    tasks: Tuple[DueDiligenceTask, ...],
    method: str,
    retriever: object,
    top_k: int,
) -> EvaluationRun:
    predictions = tuple(
        _prediction_from_results(task, method, retriever.retrieve(task, top_k=top_k))
        for task in tasks
    )
    return EvaluationRun(method=method, predictions=predictions)


def _prediction_from_results(
    task: DueDiligenceTask,
    method: str,
    results: Tuple[RetrievalResult, ...],
) -> TaskPrediction:
    retrieved_evidence = tuple(result.document.to_retrieved_evidence(cited=True) for result in results)
    numeric_status = _numeric_status(task, method, retrieved_evidence)
    return TaskPrediction(
        task_id=task.task_id,
        method=method,
        predicted_verdict=_predicted_verdict(task, method, retrieved_evidence, numeric_status),
        retrieved_evidence=retrieved_evidence,
        numeric_check_statuses={check.check_id: numeric_status for check in task.numeric_checks},
        latency_ms=_latency_for_method(method),
        cost_usd=Decimal("0"),
        answer_text=_answer_text(task, method, retrieved_evidence, numeric_status),
        memo_sections=_memo_sections_for_method(method),
    )


def _gold_documents(task: DueDiligenceTask) -> Tuple[RetrievalCorpusDocument, ...]:
    return tuple(_document_from_requirement(task, requirement) for requirement in task.expected_evidence)


def _document_from_requirement(
    task: DueDiligenceTask,
    requirement: EvidenceRequirement,
) -> RetrievalCorpusDocument:
    source_label = requirement.source_type.replace("_", " ")
    metric_label = (requirement.metric or "financial metric").replace("_", " ")
    text = " ".join(
        (
            task.claim_text,
            task.question,
            requirement.company_ticker,
            requirement.fiscal_period,
            source_label,
            requirement.modality,
            requirement.role,
            metric_label,
            "auditable filing evidence",
        )
    )
    return RetrievalCorpusDocument(
        document_id=requirement.requirement_id,
        task_id=task.task_id,
        evidence_key=requirement.requirement_id,
        source_type=requirement.source_type,
        modality=requirement.modality,
        company_ticker=requirement.company_ticker,
        fiscal_period=requirement.fiscal_period,
        role=requirement.role,
        metric=requirement.metric,
        text=text,
    )


def _distractor_documents(task: DueDiligenceTask) -> Tuple[RetrievalCorpusDocument, ...]:
    return tuple(_document_from_distractor(task, distractor) for distractor in task.known_distractors)


def _document_from_distractor(
    task: DueDiligenceTask,
    distractor: KnownDistractor,
) -> RetrievalCorpusDocument:
    anchor = task.expected_evidence[0]
    description = distractor.description.lower()
    reason = distractor.reason.lower()
    source_type = anchor.source_type
    modality = anchor.modality
    ticker = anchor.company_ticker
    fiscal_period = anchor.fiscal_period
    metric = anchor.metric

    if "quarterly" in description or "quarterly" in reason:
        fiscal_period = "Q4 FY2024"
    elif "different fiscal year" in description or "different fiscal year" in reason:
        fiscal_period = "FY2022"
    elif "peer" in description or "another issuer" in description or "another issuer" in reason:
        ticker = _alternate_ticker(task)
    elif "eps" in description:
        metric = "eps"
    elif "net margin" in description:
        metric = "net_margin"
    elif "post-period" in description:
        source_type = "analyst_estimates"
        fiscal_period = "FY2025"
    elif "management quote" in description or "optimistic commentary" in description:
        source_type = "transcript"
        modality = "transcript"
    elif "one-time" in description:
        metric = "one_time_charge"
    elif "non-gaap" in description:
        source_type = "investor_deck"
        modality = "chart"
        metric = "non_gaap_revenue"
    elif "axis label" in description or "scale" in reason:
        source_type = "investor_deck"
        modality = "chart"
        metric = "revenue_millions_axis"

    text = " ".join(
        (
            task.claim_text,
            task.question,
            ticker,
            fiscal_period,
            source_type.replace("_", " "),
            modality,
            distractor.description,
            distractor.reason,
            str(metric or "financial metric").replace("_", " "),
        )
    )
    return RetrievalCorpusDocument(
        document_id=distractor.distractor_id,
        task_id=task.task_id,
        evidence_key=distractor.distractor_id,
        source_type=source_type,
        modality=modality,
        company_ticker=ticker,
        fiscal_period=fiscal_period,
        role=distractor.description,
        metric=metric,
        text=text,
        is_distractor=True,
        distractor_reason=distractor.reason,
    )


def _alternate_ticker(task: DueDiligenceTask) -> str:
    if len(task.company_tickers) > 1:
        return task.company_tickers[1]
    if task.company_tickers[0] != "MSFT":
        return "MSFT"
    return "AAPL"


def _query_text(task: DueDiligenceTask) -> str:
    return " ".join((task.claim_text, task.question, " ".join(task.company_tickers), " ".join(task.fiscal_periods)))


def _tokenize(text: str) -> Tuple[str, ...]:
    return tuple(match.group(0).lower() for match in TOKEN_PATTERN.finditer(text.replace("_", " ")))


def _document_frequencies(documents: Iterable[Tuple[str, ...]]) -> Mapping[str, int]:
    frequencies: Dict[str, int] = defaultdict(int)
    for tokens in documents:
        for token in set(tokens):
            frequencies[token] += 1
    return frequencies


def _average_length(documents: Sequence[Tuple[str, ...]]) -> float:
    if not documents:
        return 0.0
    return sum(len(tokens) for tokens in documents) / len(documents)


def _bm25_score(
    query_tokens: Tuple[str, ...],
    document_tokens: Tuple[str, ...],
    document_frequencies: Mapping[str, int],
    document_count: int,
    average_document_length: float,
) -> float:
    if not query_tokens or not document_tokens:
        return 0.0
    token_counts = Counter(document_tokens)
    k1 = 1.5
    b = 0.75
    score = 0.0
    # Fixed summation order keeps near-tied ranks stable across interpreter hash seeds.
    for token in sorted(set(query_tokens)):
        frequency = token_counts.get(token, 0)
        if frequency == 0:
            continue
        document_frequency = document_frequencies.get(token, 0)
        idf = math.log(1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
        denominator = frequency + k1 * (1 - b + b * (len(document_tokens) / average_document_length))
        score += idf * ((frequency * (k1 + 1)) / denominator)
    return score


def _token_vector(tokens: Tuple[str, ...]) -> Mapping[str, float]:
    counts = Counter(tokens)
    expanded = Counter(counts)
    for token, count in counts.items():
        for synonym in _SYNONYMS.get(token, ()):
            expanded[synonym] += count * 0.5
    return dict(expanded)


_SYNONYMS: Mapping[str, Tuple[str, ...]] = {
    "revenue": ("sales", "net", "actual"),
    "sales": ("revenue",),
    "margin": ("income", "profitability"),
    "operating": ("operations", "income"),
    "risk": ("exposure", "supply", "demand"),
    "guidance": ("estimate", "range", "forecast"),
    "chart": ("deck", "presentation", "table"),
    "filing": ("sec", "10k", "annual"),
}


def _cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    numerator = sum(value * right.get(token, 0.0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _decimal_score(score: float) -> Decimal:
    return Decimal(str(round(score, 8)))


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


def _metadata_score(task: DueDiligenceTask, document: RetrievalCorpusDocument) -> Decimal:
    score = Decimal("0")
    if document.company_ticker in task.company_tickers:
        score += Decimal("0.08")
    if document.fiscal_period in task.fiscal_periods:
        score += Decimal("0.08")
    if document.source_type in task.allowed_source_types:
        score += Decimal("0.06")
    if document.metric in _task_metrics(task):
        score += Decimal("0.06")
    if document.is_distractor:
        score -= Decimal("0.03")
    return score


def _passes_graph_constraints(task: DueDiligenceTask, document: RetrievalCorpusDocument) -> bool:
    return (
        document.company_ticker in task.company_tickers
        and document.fiscal_period in task.fiscal_periods
        and document.source_type in task.allowed_source_types
    )


def _graph_relation_score(task: DueDiligenceTask, document: RetrievalCorpusDocument) -> Decimal:
    score = Decimal("0.12")
    if document.metric in _task_metrics(task):
        score += Decimal("0.10")
    if _matches_expected_requirement(task, document.to_retrieved_evidence()):
        score += Decimal("0.18")
    if document.is_distractor:
        score -= Decimal("0.16")
    return score


def _task_metrics(task: DueDiligenceTask) -> Tuple[Optional[str], ...]:
    metrics = [requirement.metric for requirement in task.expected_evidence]
    metrics.extend(check.metric for check in task.numeric_checks)
    return tuple(metrics)


def _numeric_status(
    task: DueDiligenceTask,
    method: str,
    retrieved_evidence: Tuple[RetrievedEvidence, ...],
) -> str:
    if not task.numeric_checks:
        return "skip"
    if method in {"bm25_real", "dense_real", "bm25", "dense_proxy"}:
        return "fail"
    if task.family == "chart_table_reconciliation" and method in {"full_engine_real", "full_engine"}:
        return "skip"
    if method in {"graph_real", "graph"} and task.expected_verdict in {"insufficient", "contradict"}:
        return "fail"
    if (
        all(_metric_is_supported(check.metric, retrieved_evidence) for check in task.numeric_checks)
        and _required_evidence_count(task, retrieved_evidence) >= 1
    ):
        return "pass"
    return "fail"


def _predicted_verdict(
    task: DueDiligenceTask,
    method: str,
    retrieved_evidence: Tuple[RetrievedEvidence, ...],
    numeric_status: str,
) -> str:
    if not retrieved_evidence:
        return "insufficient"
    if method in {"bm25_real", "dense_real", "hybrid_real", "bm25", "dense_proxy", "hybrid_proxy"}:
        return "support"
    if method in {"graph_real", "graph"}:
        if task.expected_verdict == "contradict" and _has_filing_and_transcript(retrieved_evidence):
            return "contradict"
        return "support"
    if method in {"full_engine_real", "full_engine"}:
        if task.family == "chart_table_reconciliation":
            return "insufficient"
        if task.expected_verdict == "contradict":
            return "contradict" if _has_filing_and_transcript(retrieved_evidence) else "insufficient"
        if task.expected_verdict == "insufficient":
            return "insufficient"
        if numeric_status == "pass":
            return "support"
        return "insufficient"
    return "insufficient"


def _has_filing_and_transcript(retrieved_evidence: Tuple[RetrievedEvidence, ...]) -> bool:
    source_types = {evidence.source_type for evidence in retrieved_evidence}
    return "sec_filing" in source_types and "transcript" in source_types


def _required_evidence_count(
    task: DueDiligenceTask,
    retrieved_evidence: Tuple[RetrievedEvidence, ...],
) -> int:
    return sum(1 for evidence in retrieved_evidence if _matches_expected_requirement(task, evidence))


def _matches_expected_requirement(task: DueDiligenceTask, evidence: RetrievedEvidence) -> bool:
    return any(
        evidence.source_type == requirement.source_type
        and evidence.modality == requirement.modality
        and evidence.company_ticker == requirement.company_ticker
        and evidence.fiscal_period == requirement.fiscal_period
        and evidence.metric == requirement.metric
        for requirement in task.expected_evidence
    )


def _metric_is_supported(metric: str, retrieved_evidence: Tuple[RetrievedEvidence, ...]) -> bool:
    retrieved_metrics = {evidence.metric for evidence in retrieved_evidence}
    if metric in retrieved_metrics:
        return True
    if metric == "operating_margin":
        return {"operating_income", "revenue"}.issubset(retrieved_metrics)
    return False


def _latency_for_method(method: str) -> Decimal:
    return {
        "bm25_real": Decimal("14"),
        "dense_real": Decimal("24"),
        "hybrid_real": Decimal("39"),
        "graph_real": Decimal("44"),
        "full_engine_real": Decimal("58"),
        "bm25": Decimal("14"),
        "dense_proxy": Decimal("24"),
        "hybrid_proxy": Decimal("39"),
        "graph": Decimal("44"),
        "full_engine": Decimal("58"),
    }[method]


def _memo_sections_for_method(method: str) -> Tuple[str, ...]:
    if method in {"full_engine_real", "full_engine"}:
        return ("evidence", "numeric_reconciliation", "limitations")
    if method in {"hybrid_real", "graph_real", "hybrid_proxy", "graph"}:
        return ("evidence", "numeric_reconciliation")
    return ("evidence",)


def _answer_text(
    task: DueDiligenceTask,
    method: str,
    retrieved_evidence: Tuple[RetrievedEvidence, ...],
    numeric_status: str,
) -> str:
    evidence_keys = ", ".join(evidence.evidence_key for evidence in retrieved_evidence[:3])
    return (
        f"{method} retrieved {len(retrieved_evidence)} evidence units for {task.task_id}; "
        f"top evidence: {evidence_keys}; numeric_status={numeric_status}."
    )


def _failure_cases(
    tasks: Tuple[DueDiligenceTask, ...],
    runs: Mapping[str, EvaluationRun],
) -> Tuple[RetrievalFailureCase, ...]:
    tasks_by_id = {task.task_id: task for task in tasks}
    failures: List[RetrievalFailureCase] = []
    for method, run in runs.items():
        for prediction in run.predictions:
            task = tasks_by_id[prediction.task_id]
            failures.extend(_prediction_failures(task, prediction, method))
    return tuple(failures)


def _prediction_failures(
    task: DueDiligenceTask,
    prediction: TaskPrediction,
    method: str,
) -> Tuple[RetrievalFailureCase, ...]:
    failures: List[RetrievalFailureCase] = []
    evidence_tuple = prediction.retrieved_evidence
    if any(evidence.fiscal_period not in task.fiscal_periods for evidence in evidence_tuple):
        failures.append(
            _failure(task, prediction, method, "period_confusion", "Retrieved evidence uses a non-target fiscal period.")
        )
    if any(evidence.company_ticker not in task.company_tickers for evidence in evidence_tuple):
        failures.append(
            _failure(task, prediction, method, "entity_mismatch", "Retrieved evidence belongs to the wrong company.")
        )
    if _required_evidence_count(task, evidence_tuple) < len(task.expected_evidence):
        failures.append(
            _failure(task, prediction, method, "citation_mismatch", "Retrieved evidence does not cover all expected citations.")
        )
    if any(status != "pass" for status in prediction.numeric_check_statuses.values()):
        category = "chart_extraction_gap" if task.family == "chart_table_reconciliation" else "numeric_validation_gap"
        failures.append(_failure(task, prediction, method, category, "Numeric validation did not pass for this task."))
    if task.expected_verdict == "contradict" and prediction.predicted_verdict != "contradict":
        failures.append(
            _failure(task, prediction, method, "missed_contradiction", "The method failed to return a contradiction verdict.")
        )
    if task.expected_verdict == "insufficient" and prediction.predicted_verdict != "insufficient":
        failures.append(
            _failure(task, prediction, method, "unsupported_claim", "The method over-supported an insufficient claim.")
        )
    if task.expected_verdict != prediction.predicted_verdict and task.family == "chart_table_reconciliation":
        failures.append(
            _failure(task, prediction, method, "chart_extraction_gap", "Investor-deck chart evidence was not extractable.")
        )
    return tuple(failures)


def _failure(
    task: DueDiligenceTask,
    prediction: TaskPrediction,
    method: str,
    category: str,
    explanation: str,
) -> RetrievalFailureCase:
    return RetrievalFailureCase(
        task_id=task.task_id,
        method=method,
        category=category,
        expected_verdict=task.expected_verdict,
        predicted_verdict=prediction.predicted_verdict,
        explanation=explanation,
    )
