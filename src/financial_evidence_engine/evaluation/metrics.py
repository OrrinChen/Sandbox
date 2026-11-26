"""Evaluation metrics for due-diligence task runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, Mapping, Optional, Tuple

from .task_set import DueDiligenceTask, EvidenceRequirement


PASS = "pass"


@dataclass(frozen=True)
class RetrievedEvidence:
    """Evidence returned by an evaluation method."""

    evidence_key: str
    source_type: str
    modality: str
    company_ticker: str
    fiscal_period: str
    metric: Optional[str] = None
    cited: bool = True

    @classmethod
    def from_requirement(cls, requirement: EvidenceRequirement, cited: bool = True) -> "RetrievedEvidence":
        return cls(
            evidence_key=requirement.requirement_id,
            source_type=requirement.source_type,
            modality=requirement.modality,
            company_ticker=requirement.company_ticker,
            fiscal_period=requirement.fiscal_period,
            metric=requirement.metric,
            cited=cited,
        )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "evidence_key": self.evidence_key,
            "source_type": self.source_type,
            "modality": self.modality,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "metric": self.metric,
            "cited": self.cited,
        }


@dataclass(frozen=True)
class TaskPrediction:
    """One method prediction for one due-diligence task."""

    task_id: str
    method: str
    predicted_verdict: str
    retrieved_evidence: Tuple[RetrievedEvidence, ...]
    numeric_check_statuses: Mapping[str, str]
    latency_ms: Decimal = Decimal("0")
    cost_usd: Decimal = Decimal("0")
    answer_text: str = ""
    memo_sections: Tuple[str, ...] = ()

    @classmethod
    def from_gold(
        cls,
        task: DueDiligenceTask,
        method: str,
        latency_ms: Decimal = Decimal("0"),
        cost_usd: Decimal = Decimal("0"),
    ) -> "TaskPrediction":
        return cls(
            task_id=task.task_id,
            method=method,
            predicted_verdict=task.expected_verdict,
            retrieved_evidence=tuple(
                RetrievedEvidence.from_requirement(requirement) for requirement in task.expected_evidence
            ),
            numeric_check_statuses={check.check_id: PASS for check in task.numeric_checks},
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            answer_text=f"{task.claim_text} Verdict: {task.expected_verdict}.",
            memo_sections=("evidence", "numeric_reconciliation", "limitations"),
        )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "method": self.method,
            "predicted_verdict": self.predicted_verdict,
            "retrieved_evidence": [evidence.to_dict() for evidence in self.retrieved_evidence],
            "numeric_check_statuses": dict(self.numeric_check_statuses),
            "latency_ms": str(self.latency_ms),
            "cost_usd": str(self.cost_usd),
            "answer_text": self.answer_text,
            "memo_sections": list(self.memo_sections),
        }


@dataclass(frozen=True)
class EvaluationRun:
    """A named collection of task predictions."""

    method: str
    predictions: Tuple[TaskPrediction, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "method": self.method,
            "predictions": [prediction.to_dict() for prediction in self.predictions],
        }


@dataclass(frozen=True)
class EvaluationReport:
    """Metric report for one evaluation method."""

    method: str
    task_count: int
    metrics: Mapping[str, Decimal]
    family_metrics: Mapping[str, Mapping[str, Decimal]]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "method": self.method,
            "task_count": self.task_count,
            "metrics": _decimal_mapping_to_dict(self.metrics),
            "family_metrics": {
                family: _decimal_mapping_to_dict(metrics) for family, metrics in self.family_metrics.items()
            },
        }


def evaluate_run(
    run: EvaluationRun,
    tasks: Iterable[DueDiligenceTask],
    evidence_recall_k: int = 5,
) -> EvaluationReport:
    """Evaluate one run against gold due-diligence task specs."""

    task_tuple = tuple(tasks)
    prediction_by_task_id = {prediction.task_id: prediction for prediction in run.predictions}
    metrics = _calculate_metrics(task_tuple, prediction_by_task_id, evidence_recall_k)
    family_metrics: Dict[str, Mapping[str, Decimal]] = {}
    tasks_by_family: Dict[str, list] = defaultdict(list)
    for task in task_tuple:
        tasks_by_family[task.family].append(task)
    for family, family_tasks in sorted(tasks_by_family.items()):
        family_metrics[family] = _calculate_metrics(tuple(family_tasks), prediction_by_task_id, evidence_recall_k)
    return EvaluationReport(
        method=run.method,
        task_count=len(task_tuple),
        metrics=metrics,
        family_metrics=family_metrics,
    )


def _calculate_metrics(
    tasks: Tuple[DueDiligenceTask, ...],
    prediction_by_task_id: Mapping[str, TaskPrediction],
    evidence_recall_k: int,
) -> Mapping[str, Decimal]:
    expected_evidence_count = sum(len(task.expected_evidence) for task in tasks)
    expected_numeric_count = sum(len(task.numeric_checks) for task in tasks)
    matched_evidence_count = 0
    cited_match_count = 0
    numeric_pass_count = 0
    retrieved_evidence_count = 0
    fiscal_period_match_count = 0
    entity_match_count = 0
    verdict_match_count = 0
    unsupported_total = 0
    unsupported_error_count = 0
    contradiction_total = 0
    contradiction_match_count = 0
    memo_useful_count = 0
    latency_total = Decimal("0")
    cost_total = Decimal("0")

    for task in tasks:
        prediction = prediction_by_task_id.get(task.task_id)
        if prediction is None:
            unsupported_error_count += int(task.expected_verdict == "insufficient")
            unsupported_total += int(task.expected_verdict == "insufficient")
            contradiction_total += int(task.expected_verdict == "contradict")
            continue

        top_evidence = prediction.retrieved_evidence[:evidence_recall_k]
        matched_requirements = _matched_requirements(task.expected_evidence, top_evidence)
        matched_evidence_count += len(matched_requirements)
        cited_match_count += sum(1 for _, evidence in matched_requirements if evidence.cited)
        numeric_pass_count += sum(
            1 for check in task.numeric_checks if prediction.numeric_check_statuses.get(check.check_id) == PASS
        )
        retrieved_evidence_count += len(prediction.retrieved_evidence)
        fiscal_period_match_count += sum(
            1 for evidence in prediction.retrieved_evidence if evidence.fiscal_period in task.fiscal_periods
        )
        entity_match_count += sum(
            1 for evidence in prediction.retrieved_evidence if evidence.company_ticker in task.company_tickers
        )
        verdict_match_count += int(prediction.predicted_verdict == task.expected_verdict)
        if task.expected_verdict == "insufficient":
            unsupported_total += 1
            unsupported_error_count += int(prediction.predicted_verdict != "insufficient")
        if task.expected_verdict == "contradict":
            contradiction_total += 1
            contradiction_match_count += int(prediction.predicted_verdict == "contradict")
        memo_useful_count += int(_has_useful_memo_sections(prediction))
        latency_total += prediction.latency_ms
        cost_total += prediction.cost_usd

    citation_exactness = _ratio(cited_match_count, expected_evidence_count)
    numeric_correctness = _ratio(numeric_pass_count, expected_numeric_count)
    fiscal_period_correctness = _ratio(fiscal_period_match_count, retrieved_evidence_count)
    entity_correctness = _ratio(entity_match_count, retrieved_evidence_count)
    verdict_accuracy = _ratio(verdict_match_count, len(tasks))
    contradiction_accuracy = _ratio(contradiction_match_count, contradiction_total)
    metrics = {
        "evidence_recall_at_k": _ratio(matched_evidence_count, expected_evidence_count),
        "citation_exactness": citation_exactness,
        "numeric_correctness": numeric_correctness,
        "fiscal_period_correctness": fiscal_period_correctness,
        "entity_correctness": entity_correctness,
        "unsupported_claim_rate": _ratio(unsupported_error_count, unsupported_total),
        "contradiction_detection_accuracy": contradiction_accuracy,
        "verdict_accuracy": verdict_accuracy,
        "answer_faithfulness": _average(
            (citation_exactness, numeric_correctness, fiscal_period_correctness, entity_correctness, verdict_accuracy)
        ),
        "memo_usefulness": _ratio(memo_useful_count, len(tasks)),
        "latency_ms": _ratio(latency_total, len(tasks)),
        "cost_usd": _ratio(cost_total, len(tasks)),
    }
    return metrics


def _matched_requirements(
    requirements: Tuple[EvidenceRequirement, ...],
    retrieved_evidence: Tuple[RetrievedEvidence, ...],
) -> Tuple[Tuple[EvidenceRequirement, RetrievedEvidence], ...]:
    remaining = list(retrieved_evidence)
    matches = []
    for requirement in requirements:
        for index, evidence in enumerate(remaining):
            if _matches_requirement(requirement, evidence):
                matches.append((requirement, evidence))
                remaining.pop(index)
                break
    return tuple(matches)


def _matches_requirement(requirement: EvidenceRequirement, evidence: RetrievedEvidence) -> bool:
    return (
        evidence.source_type == requirement.source_type
        and evidence.modality == requirement.modality
        and evidence.company_ticker == requirement.company_ticker
        and evidence.fiscal_period == requirement.fiscal_period
        and evidence.metric == requirement.metric
    )


def _has_useful_memo_sections(prediction: TaskPrediction) -> bool:
    required_sections = {"evidence", "numeric_reconciliation", "limitations"}
    return required_sections.issubset(set(prediction.memo_sections))


def _ratio(numerator: object, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator)


def _average(values: Tuple[Decimal, ...]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _decimal_mapping_to_dict(metrics: Mapping[str, Decimal]) -> Mapping[str, str]:
    return {name: str(value) for name, value in metrics.items()}
