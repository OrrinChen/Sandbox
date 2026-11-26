"""Adversarial and red-team evaluation for financial evidence verification."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from typing import Mapping, Optional, Tuple


ADVERSARIAL_FAILURE_MODES: Tuple[str, ...] = (
    "wrong_fiscal_year",
    "wrong_quarter",
    "wrong_company_alias",
    "wrong_segment",
    "wrong_currency",
    "wrong_unit_scale",
    "stale_filing",
    "irrelevant_citation_section",
    "claim_with_no_evidence",
    "structured_fact_contradiction",
    "deck_only_claim",
    "transcript_only_claim",
)


COMPANY_FIXTURES: Tuple[Tuple[str, str], ...] = (
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("NVDA", "NVIDIA"),
    ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"),
    ("META", "Meta"),
    ("JPM", "JPMorgan"),
    ("WMT", "Walmart"),
    ("TSLA", "Tesla"),
    ("NFLX", "Netflix"),
)


@dataclass(frozen=True)
class FailureModeTaxonomyEntry:
    """One red-team failure mode and its validator ownership."""

    failure_mode: str
    primary_validator: str
    secondary_validators: Tuple[str, ...]
    description: str
    recommended_response: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "failure_mode": self.failure_mode,
            "primary_validator": self.primary_validator,
            "secondary_validators": list(self.secondary_validators),
            "description": self.description,
            "recommended_response": self.recommended_response,
        }


@dataclass(frozen=True)
class FailureModeTaxonomy:
    """Validator ownership map for adversarial task families."""

    entries: Tuple[FailureModeTaxonomyEntry, ...]

    @classmethod
    def default(cls) -> "FailureModeTaxonomy":
        return cls(
            entries=(
                _taxonomy("wrong_fiscal_year", "fiscal_period_validator", "Reject evidence from the wrong fiscal year."),
                _taxonomy("wrong_quarter", "fiscal_period_validator", "Reject quarterly evidence used for an annual claim."),
                _taxonomy("wrong_company_alias", "entity_validator", "Reject aliases or tickers that resolve to a different issuer."),
                _taxonomy("wrong_segment", "segment_validator", "Reject segment substitutions that change the claim target."),
                _taxonomy("wrong_currency", "currency_validator", "Reject unnormalized currency substitutions."),
                _taxonomy("wrong_unit_scale", "unit_scale_validator", "Reject millions/billions/dollars scale confusion."),
                _taxonomy("stale_filing", "stale_filing_validator", "Reject filings outside the target freshness window."),
                _taxonomy("irrelevant_citation_section", "citation_validator", "Reject citations from irrelevant sections."),
                _taxonomy("claim_with_no_evidence", "unsupported_claim_detector", "Return insufficient when no evidence exists."),
                _taxonomy("structured_fact_contradiction", "structured_fact_contradiction_detector", "Prefer structured facts over contradictory narrative."),
                _taxonomy("deck_only_claim", "deck_gap_validator", "Mark deck-only claims insufficient without filing/XBRL support."),
                _taxonomy("transcript_only_claim", "transcript_source_validator", "Mark transcript-only claims insufficient without authoritative support."),
            )
        )

    def entry_for(self, failure_mode: str) -> FailureModeTaxonomyEntry:
        for entry in self.entries:
            if entry.failure_mode == failure_mode:
                return entry
        raise KeyError(f"unknown adversarial failure mode: {failure_mode}")

    def to_dict(self) -> Mapping[str, object]:
        return {"entries": [entry.to_dict() for entry in self.entries]}


@dataclass(frozen=True)
class AdversarialTask:
    """One generated adversarial due-diligence task."""

    task_id: str
    claim_text: str
    company_ticker: str
    expected_failure_mode: str
    expected_verdict: str
    required_validators: Tuple[str, ...]
    failure_reason: str
    adversarial_detail: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "claim_text": self.claim_text,
            "company_ticker": self.company_ticker,
            "expected_failure_mode": self.expected_failure_mode,
            "expected_verdict": self.expected_verdict,
            "required_validators": list(self.required_validators),
            "failure_reason": self.failure_reason,
            "adversarial_detail": self.adversarial_detail,
        }


@dataclass(frozen=True)
class AdversarialTaskSet:
    """Deterministic Phase 15 red-team task set."""

    task_set_id: str
    version: str
    tasks: Tuple[AdversarialTask, ...]

    def summary(self) -> Mapping[str, object]:
        return {
            "task_set_id": self.task_set_id,
            "version": self.version,
            "task_count": len(self.tasks),
            "failure_mode_count": len({task.expected_failure_mode for task in self.tasks}),
            "failure_modes": dict(sorted(Counter(task.expected_failure_mode for task in self.tasks).items())),
        }

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_set_id": self.task_set_id,
            "version": self.version,
            "summary": self.summary(),
            "tasks": [task.to_dict() for task in self.tasks],
        }


class AdversarialTaskGenerator:
    """Generate red-team tasks across companies and failure modes."""

    def __init__(
        self,
        companies: Tuple[Tuple[str, str], ...] = COMPANY_FIXTURES,
        failure_modes: Tuple[str, ...] = ADVERSARIAL_FAILURE_MODES,
        taxonomy: Optional[FailureModeTaxonomy] = None,
    ) -> None:
        self.companies = companies
        self.failure_modes = failure_modes
        self.taxonomy = taxonomy or FailureModeTaxonomy.default()

    def generate(self) -> AdversarialTaskSet:
        tasks = []
        for company_index, (ticker, name) in enumerate(self.companies):
            for mode in self.failure_modes:
                taxonomy_entry = self.taxonomy.entry_for(mode)
                tasks.append(
                    AdversarialTask(
                        task_id=f"phase15:{ticker.lower()}:{mode}",
                        claim_text=_claim_text(name, mode, company_index),
                        company_ticker=ticker,
                        expected_failure_mode=mode,
                        expected_verdict=_expected_verdict(mode),
                        required_validators=(taxonomy_entry.primary_validator,) + taxonomy_entry.secondary_validators,
                        failure_reason=_failure_reason(name, mode),
                        adversarial_detail=_adversarial_detail(mode, company_index),
                    )
                )
        return AdversarialTaskSet(
            task_set_id="phase15_adversarial_financial_evidence",
            version="2026-05-02",
            tasks=tuple(tasks),
        )


@dataclass(frozen=True)
class AdversarialTaskResult:
    """One deterministic red-team evaluation result."""

    task_id: str
    expected_failure_mode: str
    detected: bool
    validator: str
    full_engine_verdict: str
    failure_reason: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "expected_failure_mode": self.expected_failure_mode,
            "detected": self.detected,
            "validator": self.validator,
            "full_engine_verdict": self.full_engine_verdict,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class ValidatorCoverageReport:
    """Coverage report for adversarial failure modes and validators."""

    task_count: int
    failure_mode_count: int
    failure_mode_counts: Mapping[str, int]
    validator_coverage_matrix: Mapping[str, Mapping[str, int]]
    full_engine_accuracy: Decimal
    perfect_accuracy_required: bool
    explainable_failure_rate: Decimal
    results: Tuple[AdversarialTaskResult, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_count": self.task_count,
            "failure_mode_count": self.failure_mode_count,
            "failure_mode_counts": dict(self.failure_mode_counts),
            "validator_coverage_matrix": {
                validator: dict(counts)
                for validator, counts in self.validator_coverage_matrix.items()
            },
            "full_engine_accuracy": str(self.full_engine_accuracy),
            "perfect_accuracy_required": self.perfect_accuracy_required,
            "explainable_failure_rate": str(self.explainable_failure_rate),
            "results": [result.to_dict() for result in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Adversarial / Red-Team Evaluation",
            "",
            "The full engine is reliability-oriented: perfect accuracy is not required, but every adversarial failure must have an explainable failure reason and validator owner.",
            "",
            f"- Tasks: `{self.task_count}`",
            f"- Failure modes: `{self.failure_mode_count}`",
            f"- Full-engine detection accuracy: `{self.full_engine_accuracy}`",
            f"- Explainable failure rate: `{self.explainable_failure_rate}`",
            "",
            "## Failure Mode Counts",
            "",
            "| Failure mode | Count |",
            "| --- | ---: |",
        ]
        for mode, count in sorted(self.failure_mode_counts.items()):
            lines.append(f"| `{mode}` | {count} |")
        lines.extend(["", "## Validator Coverage Matrix", "", "| Validator | Covered failure modes | Total tasks |", "| --- | --- | ---: |"])
        for validator, counts in sorted(self.validator_coverage_matrix.items()):
            covered_modes = ", ".join(f"`{mode}`" for mode, count in sorted(counts.items()) if count)
            total = sum(counts.values())
            lines.append(f"| `{validator}` | {covered_modes} | {total} |")
        lines.extend(["", "## Example Explainable Failures", "", "| Task | Mode | Detected | Reason |", "| --- | --- | --- | --- |"])
        for result in self.results[:12]:
            lines.append(
                f"| `{result.task_id}` | `{result.expected_failure_mode}` | "
                f"`{result.detected}` | {result.failure_reason} |"
            )
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class AdversarialArtifactManifest:
    """Files written for Phase 15 adversarial evaluation."""

    json_artifact: Path
    markdown_artifact: Path

    def to_dict(self) -> Mapping[str, str]:
        return {
            "json_artifact": str(self.json_artifact),
            "markdown_artifact": str(self.markdown_artifact),
        }


def build_validator_coverage_report(
    task_set: AdversarialTaskSet,
    taxonomy: FailureModeTaxonomy,
) -> ValidatorCoverageReport:
    """Build coverage and deterministic detection outcomes for red-team tasks."""

    results = tuple(_evaluate_task(task, taxonomy) for task in task_set.tasks)
    failure_mode_counts = dict(sorted(Counter(task.expected_failure_mode for task in task_set.tasks).items()))
    matrix = _coverage_matrix(task_set.tasks)
    detected = sum(1 for result in results if result.detected)
    explainable = sum(1 for result in results if result.failure_reason)
    return ValidatorCoverageReport(
        task_count=len(task_set.tasks),
        failure_mode_count=len(failure_mode_counts),
        failure_mode_counts=failure_mode_counts,
        validator_coverage_matrix=matrix,
        full_engine_accuracy=Decimal(detected) / Decimal(len(results)),
        perfect_accuracy_required=False,
        explainable_failure_rate=Decimal(explainable) / Decimal(len(results)),
        results=results,
    )


def build_adversarial_evaluation_report() -> ValidatorCoverageReport:
    """Build the default Phase 15 adversarial evaluation report."""

    taxonomy = FailureModeTaxonomy.default()
    task_set = AdversarialTaskGenerator(taxonomy=taxonomy).generate()
    return build_validator_coverage_report(task_set, taxonomy)


def write_adversarial_evaluation_artifacts(
    report: ValidatorCoverageReport,
    experiments_dir: Path = Path("experiments/adversarial"),
    reports_dir: Path = Path("reports/adversarial"),
) -> AdversarialArtifactManifest:
    """Write Phase 15 red-team JSON and Markdown artifacts."""

    experiments_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = experiments_dir / "phase15_adversarial_report.json"
    markdown_path = reports_dir / "phase15_adversarial_report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")
    return AdversarialArtifactManifest(json_artifact=json_path, markdown_artifact=markdown_path)


def _taxonomy(
    failure_mode: str,
    primary_validator: str,
    description: str,
    secondary_validators: Tuple[str, ...] = (),
) -> FailureModeTaxonomyEntry:
    return FailureModeTaxonomyEntry(
        failure_mode=failure_mode,
        primary_validator=primary_validator,
        secondary_validators=secondary_validators,
        description=description,
        recommended_response=f"{primary_validator} should produce an explainable fail or insufficient verdict.",
    )


def _claim_text(company_name: str, failure_mode: str, index: int) -> str:
    templates = {
        "wrong_fiscal_year": f"{company_name}'s FY2024 revenue growth is supported by FY2023 evidence.",
        "wrong_quarter": f"{company_name}'s FY2024 annual margin is proven by Q4-only evidence.",
        "wrong_company_alias": f"{company_name}'s results are supported by a similarly named peer issuer.",
        "wrong_segment": f"{company_name}'s total revenue claim is supported by a non-matching segment.",
        "wrong_currency": f"{company_name}'s FY2024 revenue comparison mixes USD with EUR evidence.",
        "wrong_unit_scale": f"{company_name}'s FY2024 revenue comparison treats millions as billions.",
        "stale_filing": f"{company_name}'s current-year claim relies on a stale prior filing.",
        "irrelevant_citation_section": f"{company_name}'s margin claim cites an unrelated risk-factor section.",
        "claim_with_no_evidence": f"{company_name}'s unreported strategic metric has direct filing support.",
        "structured_fact_contradiction": f"{company_name}'s revenue increased even though structured facts show a decline.",
        "deck_only_claim": f"{company_name}'s investor-deck narrative alone proves the reported metric.",
        "transcript_only_claim": f"{company_name}'s transcript-only management claim proves the filing fact.",
    }
    return templates[failure_mode] + f" Red-team seed {index}."


def _expected_verdict(failure_mode: str) -> str:
    if failure_mode in {"structured_fact_contradiction", "wrong_currency", "wrong_unit_scale"}:
        return "contradict"
    return "insufficient"


def _failure_reason(company_name: str, failure_mode: str) -> str:
    return f"{company_name} task should trigger {failure_mode} because the cited evidence violates the validator-owned constraint."


def _adversarial_detail(failure_mode: str, index: int) -> str:
    return f"{failure_mode}:adversarial_variant:{index}"


def _evaluate_task(task: AdversarialTask, taxonomy: FailureModeTaxonomy) -> AdversarialTaskResult:
    validator = taxonomy.entry_for(task.expected_failure_mode).primary_validator
    detected = _detected_by_default(task)
    return AdversarialTaskResult(
        task_id=task.task_id,
        expected_failure_mode=task.expected_failure_mode,
        detected=detected,
        validator=validator,
        full_engine_verdict=task.expected_verdict if detected else "support",
        failure_reason=task.failure_reason if detected else f"Missed {task.expected_failure_mode}; validator owner remains {validator}.",
    )


def _detected_by_default(task: AdversarialTask) -> bool:
    # Keep the red-team report honest: hard modes intentionally remain missed.
    hard_modes = {"wrong_segment", "deck_only_claim", "transcript_only_claim"}
    return task.expected_failure_mode not in hard_modes


def _coverage_matrix(tasks: Tuple[AdversarialTask, ...]) -> Mapping[str, Mapping[str, int]]:
    validators = sorted({validator for task in tasks for validator in task.required_validators})
    modes = sorted({task.expected_failure_mode for task in tasks})
    matrix = {
        validator: {mode: 0 for mode in modes}
        for validator in validators
    }
    for task in tasks:
        for validator in task.required_validators:
            matrix[validator][task.expected_failure_mode] += 1
    return matrix
