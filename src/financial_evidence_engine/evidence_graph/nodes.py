"""Typed evidence graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Mapping

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.models import EvidenceUnit


class NodeType:
    """Stable node type names used by the evidence graph."""

    COMPANY = "Company"
    DOCUMENT = "Document"
    FISCAL_PERIOD = "FiscalPeriod"
    METRIC = "Metric"
    CLAIM = "Claim"
    EVIDENCE_UNIT = "EvidenceUnit"
    RISK_FACTOR = "RiskFactor"
    SEGMENT = "Segment"
    SPEAKER = "Person/Speaker"
    EVENT = "Event"


@dataclass(frozen=True)
class GraphNode:
    """One typed node in the evidence graph."""

    node_id: str
    node_type: str
    label: str
    properties: Mapping[str, object] = field(default_factory=dict)


def company_node(document: DocumentMetadata) -> GraphNode:
    return GraphNode(
        node_id=company_node_id(document.ticker),
        node_type=NodeType.COMPANY,
        label=document.company,
        properties={"ticker": document.ticker, "cik": document.cik, "company": document.company},
    )


def document_node(document: DocumentMetadata) -> GraphNode:
    return GraphNode(
        node_id=document_node_id(document.document_id),
        node_type=NodeType.DOCUMENT,
        label=document.document_id,
        properties={
            "document_id": document.document_id,
            "ticker": document.ticker,
            "company": document.company,
            "source_type": document.source_type,
            "filing_type": document.filing_type,
            "fiscal_period": fiscal_period_label(document.fiscal_year, document.fiscal_quarter),
            "period_end_date": document.period_end_date.isoformat(),
            "publication_date": document.publication_date.isoformat(),
            "source_url": document.source_url,
            "version_hash": document.version_hash,
        },
    )


def fiscal_period_node(document: DocumentMetadata) -> GraphNode:
    label = fiscal_period_label(document.fiscal_year, document.fiscal_quarter)
    return GraphNode(
        node_id=fiscal_period_node_id(document.ticker, label),
        node_type=NodeType.FISCAL_PERIOD,
        label=label,
        properties={
            "ticker": document.ticker,
            "fiscal_year": document.fiscal_year,
            "fiscal_quarter": document.fiscal_quarter,
            "fiscal_period": label,
            "period_end_date": document.period_end_date.isoformat(),
        },
    )


def metric_node(ticker: str, normalized_metric: str) -> GraphNode:
    return GraphNode(
        node_id=metric_node_id(ticker, normalized_metric),
        node_type=NodeType.METRIC,
        label=normalized_metric,
        properties={"ticker": ticker, "normalized_metric": normalized_metric},
    )


def claim_node(claim_id: str, text: str) -> GraphNode:
    return GraphNode(
        node_id=claim_node_id(claim_id),
        node_type=NodeType.CLAIM,
        label=text,
        properties={"claim_id": claim_id, "text": text},
    )


def evidence_unit_node(evidence: EvidenceUnit) -> GraphNode:
    return GraphNode(
        node_id=evidence_node_id(evidence.evidence_id),
        node_type=NodeType.EVIDENCE_UNIT,
        label=evidence.page_or_section,
        properties={
            "evidence_id": evidence.evidence_id,
            "document_id": evidence.document_id,
            "company": evidence.company,
            "ticker": evidence.ticker,
            "fiscal_period": evidence.fiscal_period,
            "modality": evidence.modality,
            "page_or_section": evidence.page_or_section,
            "raw_text": evidence.raw_text,
            "normalized_metric": evidence.normalized_metric,
            "numeric_value": str(evidence.numeric_value) if evidence.numeric_value is not None else None,
            "unit": evidence.unit,
            "currency": evidence.currency,
            "source_span_label": evidence.source_span.label,
            "source_span_start": evidence.source_span.start,
            "source_span_end": evidence.source_span.end,
        },
    )


def risk_factor_node(ticker: str, theme: str) -> GraphNode:
    return GraphNode(
        node_id=risk_factor_node_id(ticker, theme),
        node_type=NodeType.RISK_FACTOR,
        label=theme,
        properties={"ticker": ticker, "theme": theme},
    )


def segment_node(ticker: str, segment: str) -> GraphNode:
    return GraphNode(
        node_id=f"segment:{ticker.upper()}:{slugify(segment)}",
        node_type=NodeType.SEGMENT,
        label=segment,
        properties={"ticker": ticker.upper(), "segment": segment},
    )


def speaker_node(ticker: str, speaker: str) -> GraphNode:
    return GraphNode(
        node_id=f"speaker:{ticker.upper()}:{slugify(speaker)}",
        node_type=NodeType.SPEAKER,
        label=speaker,
        properties={"ticker": ticker.upper(), "speaker": speaker},
    )


def event_node(ticker: str, event_id: str, label: str) -> GraphNode:
    return GraphNode(
        node_id=f"event:{ticker.upper()}:{slugify(event_id)}",
        node_type=NodeType.EVENT,
        label=label,
        properties={"ticker": ticker.upper(), "event_id": event_id},
    )


def company_node_id(ticker: str) -> str:
    return f"company:{ticker.upper()}"


def document_node_id(document_id: str) -> str:
    return f"document:{document_id}"


def fiscal_period_node_id(ticker: str, fiscal_period: str) -> str:
    return f"period:{ticker.upper()}:{fiscal_period}"


def metric_node_id(ticker: str, normalized_metric: str) -> str:
    return f"metric:{ticker.upper()}:{normalized_metric}"


def claim_node_id(claim_id: str) -> str:
    return f"claim:{claim_id}"


def evidence_node_id(evidence_id: str) -> str:
    return f"evidence:{evidence_id}"


def risk_factor_node_id(ticker: str, theme: str) -> str:
    return f"risk_factor:{ticker.upper()}:{slugify(theme)}"


def fiscal_period_label(fiscal_year: int, fiscal_quarter: str) -> str:
    return f"{fiscal_year}-{fiscal_quarter}"


def slugify(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-")
