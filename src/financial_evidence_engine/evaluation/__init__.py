"""Evaluation package."""

from .adversarial import (
    ADVERSARIAL_FAILURE_MODES,
    AdversarialArtifactManifest,
    AdversarialTask,
    AdversarialTaskGenerator,
    AdversarialTaskResult,
    AdversarialTaskSet,
    FailureModeTaxonomy,
    FailureModeTaxonomyEntry,
    ValidatorCoverageReport,
    build_adversarial_evaluation_report,
    build_validator_coverage_report,
    write_adversarial_evaluation_artifacts,
)
from .baselines import (
    Phase7EvaluationReport,
    build_phase7_evaluation_report,
    run_ablation_evaluations,
    run_baseline_evaluations,
)
from .gold_builder import build_seed_task_set
from .metrics import EvaluationReport, EvaluationRun, RetrievedEvidence, TaskPrediction, evaluate_run
from .task_set import (
    DueDiligenceTask,
    DueDiligenceTaskSet,
    EvidenceRequirement,
    KnownDistractor,
    NumericCheckSpec,
)

__all__ = [
    "ADVERSARIAL_FAILURE_MODES",
    "AdversarialArtifactManifest",
    "AdversarialTask",
    "AdversarialTaskGenerator",
    "AdversarialTaskResult",
    "AdversarialTaskSet",
    "DueDiligenceTask",
    "DueDiligenceTaskSet",
    "EvidenceRequirement",
    "EvaluationReport",
    "EvaluationRun",
    "FailureModeTaxonomy",
    "FailureModeTaxonomyEntry",
    "KnownDistractor",
    "NumericCheckSpec",
    "Phase7EvaluationReport",
    "RetrievedEvidence",
    "TaskPrediction",
    "ValidatorCoverageReport",
    "build_adversarial_evaluation_report",
    "build_phase7_evaluation_report",
    "build_seed_task_set",
    "build_validator_coverage_report",
    "evaluate_run",
    "run_ablation_evaluations",
    "run_baseline_evaluations",
    "write_adversarial_evaluation_artifacts",
]
