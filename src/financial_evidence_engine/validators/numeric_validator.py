"""Numeric reconciliation validator."""

from __future__ import annotations

from financial_evidence_engine.reasoning.models import CheckStatus, EvidenceReference, Subclaim, ValidatorCheck


class NumericValidator:
    """Validate numeric evidence against a subclaim expected value."""

    name = "numeric_reconciliation"

    def validate(self, subclaim: Subclaim, evidence: EvidenceReference) -> ValidatorCheck:
        if subclaim.expected_value is None:
            return ValidatorCheck(self.name, CheckStatus.SKIP, "subclaim has no expected numeric value", evidence.evidence_id)
        if evidence.numeric_value is None:
            return ValidatorCheck(self.name, CheckStatus.FAIL, "selected evidence has no numeric value", evidence.evidence_id)
        if subclaim.expected_currency and evidence.currency and subclaim.expected_currency != evidence.currency:
            return ValidatorCheck(
                self.name,
                CheckStatus.FAIL,
                f"currency mismatch: {subclaim.expected_currency} != {evidence.currency}",
                evidence.evidence_id,
            )

        delta = abs(evidence.numeric_value - subclaim.expected_value)
        if delta <= subclaim.tolerance:
            return ValidatorCheck(
                self.name,
                CheckStatus.PASS,
                f"numeric value matches expected {subclaim.expected_value}",
                evidence.evidence_id,
            )
        return ValidatorCheck(
            self.name,
            CheckStatus.FAIL,
            f"numeric mismatch: expected {subclaim.expected_value}, observed {evidence.numeric_value}",
            evidence.evidence_id,
        )
