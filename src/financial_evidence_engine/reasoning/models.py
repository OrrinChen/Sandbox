"""Claim verification models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Tuple


class Verdict:
    """Stable verdict labels for claim verification."""

    SUPPORT = "support"
    CONTRADICT = "contradict"
    INSUFFICIENT = "insufficient"


class CheckStatus:
    """Stable validator check statuses."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class Claim:
    """A financial claim decomposed into validator-readable subclaims."""

    claim_id: str
    text: str
    subclaims: Tuple["Subclaim", ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "subclaims": [subclaim.to_dict() for subclaim in self.subclaims],
        }


@dataclass(frozen=True)
class Subclaim:
    """One verifiable unit within a financial claim."""

    subclaim_id: str
    text: str
    company_ticker: str
    fiscal_period: str
    metric: Optional[str] = None
    expected_value: Optional[Decimal] = None
    expected_currency: Optional[str] = None
    tolerance: Decimal = Decimal("0")
    required_evidence_type: Optional[str] = None
    required_terms: Tuple[str, ...] = ()

    def to_dict(self) -> Mapping[str, object]:
        return {
            "subclaim_id": self.subclaim_id,
            "text": self.text,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "metric": self.metric,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
            "expected_currency": self.expected_currency,
            "tolerance": str(self.tolerance),
            "required_evidence_type": self.required_evidence_type,
            "required_terms": list(self.required_terms),
        }


@dataclass(frozen=True)
class EvidenceReference:
    """Evidence selected from the graph, ready for validator checks."""

    evidence_id: str
    document_id: str
    company_ticker: str
    fiscal_period: str
    page_or_section: str
    raw_text: str
    source_span_label: str
    normalized_metric: Optional[str] = None
    numeric_value: Optional[Decimal] = None
    unit: Optional[str] = None
    currency: Optional[str] = None

    def to_dict(self) -> Mapping[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "document_id": self.document_id,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "page_or_section": self.page_or_section,
            "raw_text": self.raw_text,
            "source_span_label": self.source_span_label,
            "normalized_metric": self.normalized_metric,
            "numeric_value": str(self.numeric_value) if self.numeric_value is not None else None,
            "unit": self.unit,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class ValidatorCheck:
    """One validator-readable check result."""

    name: str
    status: str
    message: str
    evidence_id: Optional[str] = None

    def to_dict(self) -> Mapping[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class SubclaimVerification:
    """Verification result for one subclaim."""

    subclaim: Subclaim
    verdict: str
    evidence: Tuple[EvidenceReference, ...]
    checks: Tuple[ValidatorCheck, ...]
    confidence: Decimal

    def to_dict(self) -> Mapping[str, object]:
        return {
            "subclaim": self.subclaim.to_dict(),
            "verdict": self.verdict,
            "evidence": [evidence.to_dict() for evidence in self.evidence],
            "checks": [check.to_dict() for check in self.checks],
            "confidence": str(self.confidence),
        }


@dataclass(frozen=True)
class ClaimVerificationResult:
    """Final claim-level verification output."""

    claim: Claim
    verdict: str
    subclaim_results: Tuple[SubclaimVerification, ...]
    confidence: Decimal

    def to_dict(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim.claim_id,
            "claim_text": self.claim.text,
            "verdict": self.verdict,
            "confidence": str(self.confidence),
            "subclaims": [result.to_dict() for result in self.subclaim_results],
        }
