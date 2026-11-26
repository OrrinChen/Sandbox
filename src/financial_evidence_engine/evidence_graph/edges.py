"""Typed evidence graph edges."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Mapping


class EdgeType:
    """Stable edge type names used by the evidence graph."""

    REPORTED_IN = "reported_in"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"
    SAME_METRIC_AS = "same_metric_as"
    SAME_PERIOD_AS = "same_period_as"
    CHANGED_FROM = "changed_from"
    GUIDANCE_FOR = "guidance_for"
    RISK_RELATED_TO = "risk_related_to"


@dataclass(frozen=True)
class GraphEdge:
    """One typed directed edge in the evidence graph."""

    edge_id: str
    source_id: str
    target_id: str
    edge_type: str
    properties: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: Mapping[str, object] = None,
    ) -> "GraphEdge":
        edge_id = stable_edge_id(source_id, target_id, edge_type)
        return cls(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=properties or {},
        )


def stable_edge_id(source_id: str, target_id: str, edge_type: str) -> str:
    payload = f"{source_id}|{edge_type}|{target_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
