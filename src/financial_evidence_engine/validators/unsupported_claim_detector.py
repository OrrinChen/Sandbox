"""Unsupported-claim detection."""

from __future__ import annotations

from typing import Tuple

from financial_evidence_engine.reasoning.models import CheckStatus, EvidenceReference, ValidatorCheck


class UnsupportedClaimDetector:
    """Detect claims with no selected evidence."""

    name = "evidence_selection"

    def validate(self, evidence: Tuple[EvidenceReference, ...]) -> ValidatorCheck:
        if evidence:
            return ValidatorCheck(self.name, CheckStatus.PASS, f"selected {len(evidence)} evidence unit(s)")
        return ValidatorCheck(self.name, CheckStatus.FAIL, "no evidence selected; claim remains unsupported")
