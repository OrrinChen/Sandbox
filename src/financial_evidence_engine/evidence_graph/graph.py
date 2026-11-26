"""In-memory evidence graph container and query helpers."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from financial_evidence_engine.evidence_graph.edges import GraphEdge
from financial_evidence_engine.evidence_graph.nodes import GraphNode


class EvidenceGraph:
    """Small deterministic graph container for local evidence reasoning."""

    def __init__(self) -> None:
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._edge_ids = set()

    @property
    def nodes(self) -> Tuple[GraphNode, ...]:
        return tuple(self._nodes.values())

    @property
    def edges(self) -> Tuple[GraphEdge, ...]:
        return tuple(self._edges)

    def add_node(self, node: GraphNode) -> None:
        existing = self._nodes.get(node.node_id)
        if existing is None:
            self._nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.edge_id in self._edge_ids:
            return
        self._edge_ids.add(edge.edge_id)
        self._edges.append(edge)

    def node(self, node_id: str) -> GraphNode:
        return self._nodes[node_id]

    def maybe_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def has_edge(self, source_id: str, target_id: str, edge_type: str) -> bool:
        return any(
            edge.source_id == source_id and edge.target_id == target_id and edge.edge_type == edge_type
            for edge in self._edges
        )

    def outgoing(self, node_id: str, edge_type: Optional[str] = None) -> Tuple[GraphEdge, ...]:
        return tuple(
            edge
            for edge in self._edges
            if edge.source_id == node_id and (edge_type is None or edge.edge_type == edge_type)
        )

    def incoming(self, node_id: str, edge_type: Optional[str] = None) -> Tuple[GraphEdge, ...]:
        return tuple(
            edge
            for edge in self._edges
            if edge.target_id == node_id and (edge_type is None or edge.edge_type == edge_type)
        )

    def target_nodes(self, node_id: str, edge_type: Optional[str] = None) -> Tuple[GraphNode, ...]:
        return tuple(self._nodes[edge.target_id] for edge in self.outgoing(node_id, edge_type))

    def source_nodes(self, node_id: str, edge_type: Optional[str] = None) -> Tuple[GraphNode, ...]:
        return tuple(self._nodes[edge.source_id] for edge in self.incoming(node_id, edge_type))

    def evidence_for_claim(self, claim_id: str) -> Tuple[GraphNode, ...]:
        claim_node_id = f"claim:{claim_id}"
        return tuple(
            self._nodes[edge.target_id]
            for edge in self.outgoing(claim_node_id)
            if edge.edge_type in {"supports", "contradicts"} and edge.target_id.startswith("evidence:")
        )

    def evidence_for_metric(self, ticker: str, normalized_metric: str) -> Tuple[GraphNode, ...]:
        metric_node_id = f"metric:{ticker.upper()}:{normalized_metric}"
        return self.target_nodes(metric_node_id, "same_metric_as")

    def evidence_for_company_period(self, ticker: str, fiscal_period: str) -> Tuple[GraphNode, ...]:
        period_node_id = f"period:{ticker.upper()}:{fiscal_period}"
        return tuple(
            node
            for node in self.source_nodes(period_node_id, "same_period_as")
            if node.node_id.startswith("evidence:")
        )

    def evidence_for_risk_theme(self, ticker: str, theme: str) -> Tuple[GraphNode, ...]:
        from financial_evidence_engine.evidence_graph.nodes import risk_factor_node_id

        risk_node_id = risk_factor_node_id(ticker, theme)
        return self.target_nodes(risk_node_id, "risk_related_to")


def nodes_by_id(nodes: Iterable[GraphNode]) -> Dict[str, GraphNode]:
    return {node.node_id: node for node in nodes}
