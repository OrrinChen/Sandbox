"""Evidence selection over the local evidence graph."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Tuple

from financial_evidence_engine.evidence_graph import EvidenceGraph
from financial_evidence_engine.evidence_graph.nodes import NodeType
from financial_evidence_engine.reasoning.models import EvidenceReference, Subclaim


class EvidenceSelector:
    """Select graph evidence for one subclaim without inventing missing sources."""

    def select(self, graph: EvidenceGraph, subclaim: Subclaim) -> Tuple[EvidenceReference, ...]:
        if subclaim.metric:
            candidates = graph.evidence_for_metric(subclaim.company_ticker, subclaim.metric)
        else:
            candidates = tuple(node for node in graph.nodes if node.node_type == NodeType.EVIDENCE_UNIT)

        selected = []
        for node in candidates:
            reference = evidence_reference_from_node(node)
            if reference.company_ticker.upper() != subclaim.company_ticker.upper():
                continue
            if reference.fiscal_period != subclaim.fiscal_period:
                continue
            if subclaim.required_terms and not _contains_required_terms(reference, subclaim.required_terms):
                continue
            selected.append(reference)

        return tuple(selected)


def evidence_reference_from_node(node) -> EvidenceReference:
    properties = node.properties
    return EvidenceReference(
        evidence_id=_required_str(properties, "evidence_id"),
        document_id=_required_str(properties, "document_id"),
        company_ticker=_required_str(properties, "ticker"),
        fiscal_period=_required_str(properties, "fiscal_period"),
        page_or_section=_required_str(properties, "page_or_section"),
        raw_text=_required_str(properties, "raw_text"),
        source_span_label=_required_str(properties, "source_span_label"),
        normalized_metric=_optional_str(properties, "normalized_metric"),
        numeric_value=_optional_decimal(properties, "numeric_value"),
        unit=_optional_str(properties, "unit"),
        currency=_optional_str(properties, "currency"),
    )


def _contains_required_terms(evidence: EvidenceReference, terms: Iterable[str]) -> bool:
    searchable = f"{evidence.raw_text} {evidence.normalized_metric or ''}".lower()
    return all(term.lower() in searchable for term in terms)


def _required_str(properties, key: str) -> str:
    value = properties.get(key)
    if value is None:
        return ""
    return str(value)


def _optional_str(properties, key: str):
    value = properties.get(key)
    return str(value) if value is not None else None


def _optional_decimal(properties, key: str):
    value = properties.get(key)
    return Decimal(str(value)) if value is not None else None
