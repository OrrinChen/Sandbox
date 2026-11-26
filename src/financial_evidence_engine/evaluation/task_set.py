"""Structured due-diligence task set models."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class EvidenceRequirement:
    """Expected evidence needed to verify a task."""

    requirement_id: str
    source_type: str
    modality: str
    company_ticker: str
    fiscal_period: str
    role: str
    metric: Optional[str] = None
    min_count: int = 1

    def to_dict(self) -> Mapping[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "source_type": self.source_type,
            "modality": self.modality,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "role": self.role,
            "metric": self.metric,
            "min_count": self.min_count,
        }


@dataclass(frozen=True)
class NumericCheckSpec:
    """Validator-readable numeric check expected for a task."""

    check_id: str
    company_ticker: str
    fiscal_period: str
    metric: str
    validator: str = "numeric_reconciliation"
    relation: str = "equals"
    expected_value: Optional[Decimal] = None
    expected_unit: Optional[str] = None
    tolerance: Decimal = Decimal("0")

    def to_dict(self) -> Mapping[str, object]:
        return {
            "check_id": self.check_id,
            "validator": self.validator,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "metric": self.metric,
            "relation": self.relation,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
            "expected_unit": self.expected_unit,
            "tolerance": str(self.tolerance),
        }


@dataclass(frozen=True)
class KnownDistractor:
    """Known distractor that an evaluation run should avoid."""

    distractor_id: str
    description: str
    reason: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "distractor_id": self.distractor_id,
            "description": self.description,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DueDiligenceTask:
    """One gold task for claim-level due-diligence evaluation."""

    task_id: str
    family: str
    question: str
    claim_text: str
    company_tickers: Tuple[str, ...]
    fiscal_periods: Tuple[str, ...]
    allowed_source_types: Tuple[str, ...]
    expected_evidence: Tuple[EvidenceRequirement, ...]
    numeric_checks: Tuple[NumericCheckSpec, ...]
    expected_verdict: str
    known_distractors: Tuple[KnownDistractor, ...]
    requires_citation: bool = True

    @property
    def is_multi_hop(self) -> bool:
        return len(self.expected_evidence) >= 2 and bool(self.numeric_checks)

    @property
    def is_multi_document(self) -> bool:
        source_types = {requirement.source_type for requirement in self.expected_evidence}
        modalities = {requirement.modality for requirement in self.expected_evidence}
        return len(source_types) >= 2 and len(modalities) >= 2

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "family": self.family,
            "question": self.question,
            "claim_text": self.claim_text,
            "company_tickers": list(self.company_tickers),
            "fiscal_periods": list(self.fiscal_periods),
            "allowed_source_types": list(self.allowed_source_types),
            "expected_evidence": [requirement.to_dict() for requirement in self.expected_evidence],
            "numeric_checks": [check.to_dict() for check in self.numeric_checks],
            "expected_verdict": self.expected_verdict,
            "known_distractors": [distractor.to_dict() for distractor in self.known_distractors],
            "requires_citation": self.requires_citation,
        }


@dataclass(frozen=True)
class DueDiligenceTaskSet:
    """A reproducible set of due-diligence evaluation tasks."""

    task_set_id: str
    version: str
    tasks: Tuple[DueDiligenceTask, ...]

    def summary(self) -> Mapping[str, object]:
        return {
            "task_set_id": self.task_set_id,
            "version": self.version,
            "task_count": len(self.tasks),
            "families": dict(sorted(Counter(task.family for task in self.tasks).items())),
            "verdicts": dict(sorted(Counter(task.expected_verdict for task in self.tasks).items())),
        }

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_set_id": self.task_set_id,
            "version": self.version,
            "summary": self.summary(),
            "tasks": [task.to_dict() for task in self.tasks],
        }
