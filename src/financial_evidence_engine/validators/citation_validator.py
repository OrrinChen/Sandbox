"""Citation traceability validator."""

from __future__ import annotations

from financial_evidence_engine.evidence_graph import EvidenceGraph
from financial_evidence_engine.evidence_graph.nodes import document_node_id
from financial_evidence_engine.reasoning.models import CheckStatus, EvidenceReference, ValidatorCheck


class CitationValidator:
    """Validate that selected evidence has traceable citation fields."""

    name = "citation_validation"

    def validate(self, graph: EvidenceGraph, evidence: EvidenceReference) -> ValidatorCheck:
        if not evidence.document_id or not evidence.page_or_section or not evidence.source_span_label:
            return ValidatorCheck(self.name, CheckStatus.FAIL, "evidence is missing citation fields", evidence.evidence_id)
        if graph.maybe_node(document_node_id(evidence.document_id)) is None:
            return ValidatorCheck(self.name, CheckStatus.FAIL, "evidence document is not present in graph", evidence.evidence_id)
        return ValidatorCheck(self.name, CheckStatus.PASS, "evidence has document, section, and source span", evidence.evidence_id)
