"""Contradiction detection helpers."""

from __future__ import annotations

from financial_evidence_engine.reasoning.models import CheckStatus, SubclaimVerification, Verdict


class ContradictionDetector:
    """Detect contradiction from failed validator checks."""

    def is_contradiction(self, result: SubclaimVerification) -> bool:
        return result.verdict == Verdict.CONTRADICT or any(
            check.status == CheckStatus.FAIL and check.name == "numeric_reconciliation"
            for check in result.checks
        )
