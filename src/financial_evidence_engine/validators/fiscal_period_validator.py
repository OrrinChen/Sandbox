"""Fiscal-period validator."""

from __future__ import annotations

from financial_evidence_engine.reasoning.models import CheckStatus, EvidenceReference, Subclaim, ValidatorCheck


class FiscalPeriodValidator:
    """Validate that evidence and subclaim fiscal periods match exactly."""

    name = "fiscal_period_validation"

    def validate(self, subclaim: Subclaim, evidence: EvidenceReference) -> ValidatorCheck:
        if evidence.fiscal_period == subclaim.fiscal_period:
            return ValidatorCheck(self.name, CheckStatus.PASS, f"period matches {subclaim.fiscal_period}", evidence.evidence_id)
        return ValidatorCheck(
            self.name,
            CheckStatus.FAIL,
            f"period mismatch: expected {subclaim.fiscal_period}, observed {evidence.fiscal_period}",
            evidence.evidence_id,
        )
