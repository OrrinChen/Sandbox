"""Claim verification orchestration."""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from financial_evidence_engine.evidence_graph import EvidenceGraph
from financial_evidence_engine.reasoning.evidence_selector import EvidenceSelector
from financial_evidence_engine.reasoning.models import (
    CheckStatus,
    Claim,
    ClaimVerificationResult,
    EvidenceReference,
    Subclaim,
    SubclaimVerification,
    ValidatorCheck,
    Verdict,
)
from financial_evidence_engine.validators.citation_validator import CitationValidator
from financial_evidence_engine.validators.fiscal_period_validator import FiscalPeriodValidator
from financial_evidence_engine.validators.numeric_validator import NumericValidator
from financial_evidence_engine.validators.source_consistency_validator import SourceConsistencyValidator
from financial_evidence_engine.validators.unsupported_claim_detector import UnsupportedClaimDetector


class ClaimVerifier:
    """Verify decomposed claims against the evidence graph."""

    def __init__(
        self,
        selector: Optional[EvidenceSelector] = None,
        citation_validator: Optional[CitationValidator] = None,
        fiscal_period_validator: Optional[FiscalPeriodValidator] = None,
        source_consistency_validator: Optional[SourceConsistencyValidator] = None,
        numeric_validator: Optional[NumericValidator] = None,
        unsupported_detector: Optional[UnsupportedClaimDetector] = None,
    ) -> None:
        self._selector = selector or EvidenceSelector()
        self._citation_validator = citation_validator or CitationValidator()
        self._fiscal_period_validator = fiscal_period_validator or FiscalPeriodValidator()
        self._source_consistency_validator = source_consistency_validator or SourceConsistencyValidator()
        self._numeric_validator = numeric_validator or NumericValidator()
        self._unsupported_detector = unsupported_detector or UnsupportedClaimDetector()

    def verify(self, claim: Claim, graph: EvidenceGraph) -> ClaimVerificationResult:
        subclaim_results = tuple(self._verify_subclaim(subclaim, graph) for subclaim in claim.subclaims)
        verdict = _roll_up_verdict(tuple(result.verdict for result in subclaim_results))
        confidence = _roll_up_confidence(subclaim_results)
        return ClaimVerificationResult(
            claim=claim,
            verdict=verdict,
            subclaim_results=subclaim_results,
            confidence=confidence,
        )

    def _verify_subclaim(self, subclaim: Subclaim, graph: EvidenceGraph) -> SubclaimVerification:
        selected_evidence = self._selector.select(graph, subclaim)
        checks: List[ValidatorCheck] = [self._unsupported_detector.validate(selected_evidence)]

        if not selected_evidence:
            return SubclaimVerification(
                subclaim=subclaim,
                verdict=Verdict.INSUFFICIENT,
                evidence=(),
                checks=tuple(checks),
                confidence=Decimal("0"),
            )

        # Keep Phase 5 deterministic: validate the strongest first selected evidence.
        evidence = selected_evidence[0]
        checks.extend(self._checks_for_evidence(graph, subclaim, evidence))
        verdict = _verdict_for_checks(checks)
        return SubclaimVerification(
            subclaim=subclaim,
            verdict=verdict,
            evidence=(evidence,),
            checks=tuple(checks),
            confidence=_confidence_for_verdict(verdict),
        )

    def _checks_for_evidence(
        self,
        graph: EvidenceGraph,
        subclaim: Subclaim,
        evidence: EvidenceReference,
    ) -> Tuple[ValidatorCheck, ...]:
        return (
            self._citation_validator.validate(graph, evidence),
            self._fiscal_period_validator.validate(subclaim, evidence),
            self._source_consistency_validator.validate(graph, subclaim, evidence),
            self._numeric_validator.validate(subclaim, evidence),
        )


def _verdict_for_checks(checks: List[ValidatorCheck]) -> str:
    failing_checks = [check for check in checks if check.status == CheckStatus.FAIL]
    if not failing_checks:
        return Verdict.SUPPORT

    if any(check.name == "numeric_reconciliation" for check in failing_checks):
        return Verdict.CONTRADICT
    if any(check.name == "evidence_selection" for check in failing_checks):
        return Verdict.INSUFFICIENT
    return Verdict.CONTRADICT


def _roll_up_verdict(verdicts: Tuple[str, ...]) -> str:
    if any(verdict == Verdict.CONTRADICT for verdict in verdicts):
        return Verdict.CONTRADICT
    if any(verdict == Verdict.INSUFFICIENT for verdict in verdicts):
        return Verdict.INSUFFICIENT
    return Verdict.SUPPORT


def _confidence_for_verdict(verdict: str) -> Decimal:
    if verdict == Verdict.SUPPORT:
        return Decimal("1.0")
    if verdict == Verdict.CONTRADICT:
        return Decimal("0.9")
    return Decimal("0")


def _roll_up_confidence(results: Tuple[SubclaimVerification, ...]) -> Decimal:
    if not results:
        return Decimal("0")
    return sum((result.confidence for result in results), Decimal("0")) / Decimal(len(results))
