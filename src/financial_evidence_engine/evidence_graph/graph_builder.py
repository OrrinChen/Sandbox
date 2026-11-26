"""Build an evidence graph from document metadata and evidence units."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph.claim_graph import ClaimLink
from financial_evidence_engine.evidence_graph.edges import EdgeType, GraphEdge
from financial_evidence_engine.evidence_graph.graph import EvidenceGraph
from financial_evidence_engine.evidence_graph.nodes import (
    claim_node,
    company_node,
    document_node,
    document_node_id,
    evidence_node_id,
    evidence_unit_node,
    fiscal_period_node,
    fiscal_period_node_id,
    metric_node,
    risk_factor_node,
    speaker_node,
)
from financial_evidence_engine.extraction.models import EvidenceUnit


def build_evidence_graph(
    documents: Iterable[DocumentMetadata],
    evidence_units: Iterable[EvidenceUnit],
    claims: Iterable[ClaimLink] = (),
    risk_themes: Sequence[str] = (),
) -> EvidenceGraph:
    """Build a deterministic local evidence graph for current MVP artifacts."""

    graph = EvidenceGraph()
    documents_by_id = {document.document_id: document for document in documents}
    evidence_by_id = {evidence.evidence_id: evidence for evidence in evidence_units}

    for document in documents_by_id.values():
        _add_document_context(graph, document)

    for evidence in evidence_by_id.values():
        _add_evidence_context(graph, evidence, documents_by_id, risk_themes)

    for claim in claims:
        _add_claim_links(graph, claim, evidence_by_id)

    return graph


def _add_document_context(graph: EvidenceGraph, document: DocumentMetadata) -> None:
    company = company_node(document)
    source_document = document_node(document)
    period = fiscal_period_node(document)

    graph.add_node(company)
    graph.add_node(source_document)
    graph.add_node(period)
    graph.add_edge(GraphEdge.create(source_document.node_id, company.node_id, EdgeType.REPORTED_IN))
    graph.add_edge(GraphEdge.create(source_document.node_id, period.node_id, EdgeType.SAME_PERIOD_AS))


def _add_evidence_context(
    graph: EvidenceGraph,
    evidence: EvidenceUnit,
    documents_by_id: Mapping[str, DocumentMetadata],
    risk_themes: Sequence[str],
) -> None:
    document = documents_by_id.get(evidence.document_id)
    evidence_node = evidence_unit_node(evidence)
    graph.add_node(evidence_node)

    graph.add_edge(
        GraphEdge.create(
            evidence_node.node_id,
            document_node_id(evidence.document_id),
            EdgeType.REPORTED_IN,
        )
    )
    graph.add_edge(
        GraphEdge.create(
            evidence_node.node_id,
            fiscal_period_node_id(evidence.ticker, evidence.fiscal_period),
            EdgeType.SAME_PERIOD_AS,
        )
    )

    if evidence.normalized_metric:
        metric = metric_node(evidence.ticker, evidence.normalized_metric)
        graph.add_node(metric)
        graph.add_edge(GraphEdge.create(metric.node_id, evidence_node.node_id, EdgeType.SAME_METRIC_AS))

    if evidence.modality == "transcript":
        speaker = _speaker_from_section(evidence.page_or_section)
        if speaker:
            speaker_graph_node = speaker_node(evidence.ticker, speaker)
            graph.add_node(speaker_graph_node)
            graph.add_edge(GraphEdge.create(speaker_graph_node.node_id, evidence_node.node_id, EdgeType.MENTIONS))

    for theme in risk_themes:
        if _text_mentions_theme(evidence.raw_text, theme):
            risk_node = risk_factor_node(evidence.ticker, theme)
            graph.add_node(risk_node)
            graph.add_edge(GraphEdge.create(risk_node.node_id, evidence_node.node_id, EdgeType.RISK_RELATED_TO))

    if document is not None:
        company = company_node(document)
        graph.add_node(company)
        graph.add_edge(GraphEdge.create(evidence_node.node_id, company.node_id, EdgeType.MENTIONS))


def _add_claim_links(
    graph: EvidenceGraph,
    claim: ClaimLink,
    evidence_by_id: Mapping[str, EvidenceUnit],
) -> None:
    node = claim_node(claim.claim_id, claim.text)
    graph.add_node(node)

    for evidence_id in claim.supporting_evidence_ids:
        if evidence_id not in evidence_by_id:
            continue
        graph.add_edge(GraphEdge.create(node.node_id, evidence_node_id(evidence_id), EdgeType.SUPPORTS))

    for evidence_id in claim.contradicting_evidence_ids:
        if evidence_id not in evidence_by_id:
            continue
        graph.add_edge(GraphEdge.create(node.node_id, evidence_node_id(evidence_id), EdgeType.CONTRADICTS))


def _speaker_from_section(page_or_section: str) -> str:
    if "/" not in page_or_section:
        return ""
    return page_or_section.split("/", maxsplit=1)[1].strip()


def _text_mentions_theme(text: str, theme: str) -> bool:
    return theme.lower() in text.lower()
