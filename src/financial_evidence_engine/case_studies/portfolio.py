"""Portfolio case studies derived from real retrieval evaluation runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from financial_evidence_engine.evaluation import (
    DueDiligenceTask,
    DueDiligenceTaskSet,
    EvidenceRequirement,
    RetrievedEvidence,
    TaskPrediction,
    build_seed_task_set,
)
from financial_evidence_engine.retrieval import (
    REAL_RETRIEVAL_METHODS,
    RealRetrievalEvaluationResult,
    RetrievalFailureCase,
    run_real_retrieval_evaluation,
)


CASE_DEFINITIONS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "fiscal_period_confusion",
        "Fiscal-Period Confusion",
        "period_confusion",
        "single_company_trend",
    ),
    (
        "numeric_unit_mismatch",
        "Numeric / Unit Mismatch",
        "numeric_validation_gap",
        "cross_company_comparison",
    ),
    (
        "unsupported_narrative_claim",
        "Unsupported Narrative Claim",
        "unsupported_claim",
        "management_claim_verification",
    ),
)


@dataclass(frozen=True)
class EvidenceReference:
    """Serializable evidence reference for case-study artifacts."""

    evidence_key: str
    source_type: str
    modality: str
    company_ticker: str
    fiscal_period: str
    metric: Optional[str]
    role: str = ""
    cited: Optional[bool] = None

    @classmethod
    def from_requirement(cls, requirement: EvidenceRequirement) -> "EvidenceReference":
        return cls(
            evidence_key=requirement.requirement_id,
            source_type=requirement.source_type,
            modality=requirement.modality,
            company_ticker=requirement.company_ticker,
            fiscal_period=requirement.fiscal_period,
            metric=requirement.metric,
            role=requirement.role,
        )

    @classmethod
    def from_retrieved(cls, evidence: RetrievedEvidence) -> "EvidenceReference":
        return cls(
            evidence_key=evidence.evidence_key,
            source_type=evidence.source_type,
            modality=evidence.modality,
            company_ticker=evidence.company_ticker,
            fiscal_period=evidence.fiscal_period,
            metric=evidence.metric,
            cited=evidence.cited,
        )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "evidence_key": self.evidence_key,
            "source_type": self.source_type,
            "modality": self.modality,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "metric": self.metric,
            "role": self.role,
            "cited": self.cited,
        }


@dataclass(frozen=True)
class ValidatorCheck:
    """Validator status surfaced for one method on one case study."""

    validator: str
    status: str
    detail: str

    def to_dict(self) -> Mapping[str, str]:
        return {
            "validator": self.validator,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class MethodCaseResult:
    """One retrieval method's result for a case study."""

    method: str
    predicted_verdict: str
    retrieved_evidence: Tuple[EvidenceReference, ...]
    failure_reasons: Tuple[str, ...]
    validator_checks: Tuple[ValidatorCheck, ...]
    answer_text: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "method": self.method,
            "predicted_verdict": self.predicted_verdict,
            "retrieved_evidence": [evidence.to_dict() for evidence in self.retrieved_evidence],
            "failure_reasons": list(self.failure_reasons),
            "validator_checks": [check.to_dict() for check in self.validator_checks],
            "answer_text": self.answer_text,
        }


@dataclass(frozen=True)
class PortfolioCaseStudy:
    """Recruiter-facing case study generated from a real retrieval run."""

    case_id: str
    title: str
    failure_mode: str
    task_id: str
    claim: str
    expected_verdict: str
    gold_evidence: Tuple[EvidenceReference, ...]
    method_results: Mapping[str, MethodCaseResult]
    final_full_engine_verdict: str
    memo_snippet: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "failure_mode": self.failure_mode,
            "task_id": self.task_id,
            "claim": self.claim,
            "expected_verdict": self.expected_verdict,
            "gold_evidence": [evidence.to_dict() for evidence in self.gold_evidence],
            "method_results": {
                method: result.to_dict() for method, result in self.method_results.items()
            },
            "final_full_engine_verdict": self.final_full_engine_verdict,
            "memo_snippet": self.memo_snippet,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            f"- Case ID: `{self.case_id}`",
            f"- Task ID: `{self.task_id}`",
            f"- Failure mode: `{self.failure_mode}`",
            f"- Expected verdict: `{self.expected_verdict}`",
            f"- Full engine verdict: `{self.final_full_engine_verdict}`",
            "",
            "## Claim",
            "",
            self.claim,
            "",
            "## Gold Evidence",
            "",
            "| Evidence | Source | Company | Period | Metric | Role |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for evidence in self.gold_evidence:
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"`{evidence.evidence_key}`",
                        f"{evidence.source_type}/{evidence.modality}",
                        evidence.company_ticker,
                        evidence.fiscal_period,
                        evidence.metric or "",
                        evidence.role,
                    )
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## Retrieved Evidence by Method",
                "",
            ]
        )
        for method, result in self.method_results.items():
            lines.extend(
                [
                    f"### {method}",
                    "",
                    f"Predicted verdict: `{result.predicted_verdict}`",
                    "",
                    "| Evidence | Source | Company | Period | Metric |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for evidence in result.retrieved_evidence:
                lines.append(
                    "| "
                    + " | ".join(
                        (
                            f"`{evidence.evidence_key}`",
                            f"{evidence.source_type}/{evidence.modality}",
                            evidence.company_ticker,
                            evidence.fiscal_period,
                            evidence.metric or "",
                        )
                    )
                    + " |"
                )
            lines.append("")
        lines.extend(
            [
                "## Failure Reasons by Method",
                "",
                "| Method | Failure reasons |",
                "| --- | --- |",
            ]
        )
        for method, result in self.method_results.items():
            lines.append(f"| {method} | {'; '.join(result.failure_reasons)} |")
        lines.extend(
            [
                "",
                "## Validator Checks Triggered",
                "",
                "| Method | Validator | Status | Detail |",
                "| --- | --- | --- | --- |",
            ]
        )
        for method, result in self.method_results.items():
            for check in result.validator_checks:
                lines.append(f"| {method} | {check.validator} | {check.status} | {check.detail} |")
        lines.extend(
            [
                "",
                "## Memo Snippet",
                "",
                self.memo_snippet,
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class CaseStudyArtifactManifest:
    """Files written for Phase 9 case-study artifacts."""

    json_artifacts: Tuple[Path, ...]
    markdown_artifacts: Tuple[Path, ...]
    summary_markdown: Path

    def to_dict(self) -> Mapping[str, object]:
        return {
            "json_artifacts": [str(path) for path in self.json_artifacts],
            "markdown_artifacts": [str(path) for path in self.markdown_artifacts],
            "summary_markdown": str(self.summary_markdown),
        }


def build_portfolio_case_studies(
    task_set: Optional[DueDiligenceTaskSet] = None,
    retrieval_result: Optional[RealRetrievalEvaluationResult] = None,
) -> Tuple[PortfolioCaseStudy, ...]:
    """Build the three Phase 9 case studies from a real retrieval run."""

    task_set = task_set or build_seed_task_set()
    retrieval_result = retrieval_result or run_real_retrieval_evaluation(task_set)
    tasks_by_id = {task.task_id: task for task in task_set.tasks}
    predictions_by_method = _predictions_by_method(retrieval_result)
    failures_by_task_method = _failures_by_task_method(retrieval_result.failure_cases)

    selected_task_ids = set()
    case_studies: List[PortfolioCaseStudy] = []
    for case_id, title, failure_category, preferred_family in CASE_DEFINITIONS:
        task = _select_task_for_case(
            tasks_by_id=tasks_by_id,
            failures=retrieval_result.failure_cases,
            failure_category=failure_category,
            preferred_family=preferred_family,
            excluded_task_ids=selected_task_ids,
        )
        selected_task_ids.add(task.task_id)
        method_results = {
            method: _method_case_result(
                task=task,
                prediction=predictions_by_method[method][task.task_id],
                failures=failures_by_task_method.get((task.task_id, method), ()),
            )
            for method in REAL_RETRIEVAL_METHODS
        }
        full_engine = method_results["full_engine_real"]
        case_studies.append(
            PortfolioCaseStudy(
                case_id=case_id,
                title=title,
                failure_mode=failure_category,
                task_id=task.task_id,
                claim=task.claim_text,
                expected_verdict=task.expected_verdict,
                gold_evidence=tuple(
                    EvidenceReference.from_requirement(requirement)
                    for requirement in task.expected_evidence
                ),
                method_results=method_results,
                final_full_engine_verdict=full_engine.predicted_verdict,
                memo_snippet=_memo_snippet(task, full_engine),
            )
        )
    return tuple(case_studies)


def render_case_study_summary(case_studies: Iterable[PortfolioCaseStudy]) -> str:
    """Render a compact Markdown summary suitable for README embedding."""

    lines = [
        "| Case | Failure mode | Claim | Full-engine verdict | Artifact |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in case_studies:
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{case.case_id}`",
                    f"`{case.failure_mode}`",
                    _compact(case.claim),
                    f"`{case.final_full_engine_verdict}`",
                    f"[Markdown](reports/case_studies/{case.case_id}.md)",
                )
            )
            + " |"
        )
    return "\n".join(lines)


def write_case_study_artifacts(
    case_studies: Iterable[PortfolioCaseStudy],
    experiments_dir: Path = Path("experiments/case_studies"),
    reports_dir: Path = Path("reports/case_studies"),
) -> CaseStudyArtifactManifest:
    """Write case-study JSON and Markdown artifacts."""

    case_tuple = tuple(case_studies)
    experiments_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_artifacts = []
    markdown_artifacts = []
    for case in case_tuple:
        json_path = experiments_dir / f"{case.case_id}.json"
        markdown_path = reports_dir / f"{case.case_id}.md"
        json_path.write_text(json.dumps(case.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(case.to_markdown().rstrip() + "\n", encoding="utf-8")
        json_artifacts.append(json_path)
        markdown_artifacts.append(markdown_path)

    summary_path = reports_dir / "index.md"
    summary_path.write_text(
        "# Portfolio Case Studies\n\n" + render_case_study_summary(case_tuple) + "\n",
        encoding="utf-8",
    )
    return CaseStudyArtifactManifest(
        json_artifacts=tuple(json_artifacts),
        markdown_artifacts=tuple(markdown_artifacts),
        summary_markdown=summary_path,
    )


def _select_task_for_case(
    tasks_by_id: Mapping[str, DueDiligenceTask],
    failures: Tuple[RetrievalFailureCase, ...],
    failure_category: str,
    preferred_family: str,
    excluded_task_ids: set,
) -> DueDiligenceTask:
    for failure in failures:
        task = tasks_by_id[failure.task_id]
        if (
            failure.category == failure_category
            and task.family == preferred_family
            and task.task_id not in excluded_task_ids
        ):
            return task
    for failure in failures:
        task = tasks_by_id[failure.task_id]
        if failure.category == failure_category and task.task_id not in excluded_task_ids:
            return task
    raise ValueError(f"No retrieval failure found for category {failure_category}")


def _predictions_by_method(
    retrieval_result: RealRetrievalEvaluationResult,
) -> Mapping[str, Mapping[str, TaskPrediction]]:
    return {
        method: {prediction.task_id: prediction for prediction in run.predictions}
        for method, run in retrieval_result.runs.items()
    }


def _failures_by_task_method(
    failures: Tuple[RetrievalFailureCase, ...],
) -> Mapping[Tuple[str, str], Tuple[RetrievalFailureCase, ...]]:
    failure_map: Dict[Tuple[str, str], List[RetrievalFailureCase]] = {}
    for failure in failures:
        failure_map.setdefault((failure.task_id, failure.method), []).append(failure)
    return {key: tuple(value) for key, value in failure_map.items()}


def _method_case_result(
    task: DueDiligenceTask,
    prediction: TaskPrediction,
    failures: Tuple[RetrievalFailureCase, ...],
) -> MethodCaseResult:
    failure_reasons = tuple(
        f"{failure.category}: {failure.explanation}" for failure in failures
    ) or ("No failure detected for this method on this case.",)
    return MethodCaseResult(
        method=prediction.method,
        predicted_verdict=prediction.predicted_verdict,
        retrieved_evidence=tuple(
            EvidenceReference.from_retrieved(evidence)
            for evidence in prediction.retrieved_evidence
        ),
        failure_reasons=failure_reasons,
        validator_checks=_validator_checks(task, prediction, failures),
        answer_text=prediction.answer_text,
    )


def _validator_checks(
    task: DueDiligenceTask,
    prediction: TaskPrediction,
    failures: Tuple[RetrievalFailureCase, ...],
) -> Tuple[ValidatorCheck, ...]:
    categories = {failure.category for failure in failures}
    numeric_status = _aggregate_numeric_status(prediction)
    return (
        ValidatorCheck(
            validator="numeric_reconciliation",
            status=numeric_status,
            detail=_numeric_detail(prediction),
        ),
        ValidatorCheck(
            validator="fiscal_period_validator",
            status="fail" if "period_confusion" in categories else "pass",
            detail="Checks whether retrieved evidence periods match the target fiscal period.",
        ),
        ValidatorCheck(
            validator="entity_validator",
            status="fail" if "entity_mismatch" in categories else "pass",
            detail="Checks whether retrieved evidence belongs to the target company universe.",
        ),
        ValidatorCheck(
            validator="citation_validator",
            status="fail" if "citation_mismatch" in categories else "pass",
            detail="Checks whether retrieved evidence covers all expected evidence roles.",
        ),
        ValidatorCheck(
            validator="unsupported_claim_detector",
            status="fail" if "unsupported_claim" in categories else _claim_detector_status(task, "insufficient"),
            detail="Checks whether an insufficient claim was over-supported.",
        ),
        ValidatorCheck(
            validator="contradiction_detector",
            status="fail" if "missed_contradiction" in categories else _claim_detector_status(task, "contradict"),
            detail="Checks whether contradiction-labeled tasks receive a contradiction verdict.",
        ),
    )


def _aggregate_numeric_status(prediction: TaskPrediction) -> str:
    statuses = set(prediction.numeric_check_statuses.values())
    if not statuses:
        return "skip"
    if statuses == {"pass"}:
        return "pass"
    if statuses == {"skip"}:
        return "skip"
    return "fail"


def _numeric_detail(prediction: TaskPrediction) -> str:
    if not prediction.numeric_check_statuses:
        return "No numeric checks required."
    return ", ".join(
        f"{check_id}={status}"
        for check_id, status in sorted(prediction.numeric_check_statuses.items())
    )


def _claim_detector_status(task: DueDiligenceTask, target_verdict: str) -> str:
    if task.expected_verdict == target_verdict:
        return "pass"
    return "skip"


def _memo_snippet(task: DueDiligenceTask, full_engine_result: MethodCaseResult) -> str:
    failing_checks = [
        check for check in full_engine_result.validator_checks
        if check.status == "fail"
    ]
    if failing_checks:
        limitation = "; ".join(f"{check.validator}: {check.detail}" for check in failing_checks)
    else:
        limitation = "No validator failure was detected for the full-engine method on this case."
    return (
        f"Full engine verdict: {full_engine_result.predicted_verdict}. "
        f"Expected verdict: {task.expected_verdict}. "
        f"The memo cites {len(full_engine_result.retrieved_evidence)} retrieved evidence units and separates "
        f"retrieval output from validator judgment. Limitation: {limitation}"
    )


def _compact(text: str, max_length: int = 96) -> str:
    clean = text.replace("|", "/").replace("\n", " ").strip()
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 3].rstrip() + "..."
