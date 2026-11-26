"""Source consistency validator."""

from __future__ import annotations

from financial_evidence_engine.evidence_graph import EvidenceGraph
from financial_evidence_engine.evidence_graph.nodes import document_node_id
from financial_evidence_engine.reasoning.models import CheckStatus, EvidenceReference, Subclaim, ValidatorCheck


class SourceConsistencyValidator:
    """Validate that selected evidence belongs to the expected company and graph document."""

    name = "source_consistency_validation"

    def validate(self, graph: EvidenceGraph, subclaim: Subclaim, evidence: EvidenceReference) -> ValidatorCheck:
        if evidence.company_ticker.upper() != subclaim.company_ticker.upper():
            return ValidatorCheck(
                self.name,
                CheckStatus.FAIL,
                f"company mismatch: expected {subclaim.company_ticker}, observed {evidence.company_ticker}",
                evidence.evidence_id,
            )

        document = graph.maybe_node(document_node_id(evidence.document_id))
        if document is None:
            return ValidatorCheck(self.name, CheckStatus.FAIL, "evidence document is missing from graph", evidence.evidence_id)
        if str(document.properties.get("ticker", "")).upper() != subclaim.company_ticker.upper():
            return ValidatorCheck(
                self.name,
                CheckStatus.FAIL,
                "evidence document belongs to a different company",
                evidence.evidence_id,
            )

        return ValidatorCheck(self.name, CheckStatus.PASS, "evidence source matches subclaim company", evidence.evidence_id)
