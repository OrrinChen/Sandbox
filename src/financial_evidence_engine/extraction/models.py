"""Evidence unit models shared by extraction modules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Optional

from financial_evidence_engine.data.models import DocumentMetadata


@dataclass(frozen=True)
class SourceSpan:
    """Location of extracted evidence within a source representation."""

    start: int
    end: int
    label: str


@dataclass(frozen=True)
class EvidenceUnit:
    """A normalized evidence unit traceable to one source document."""

    evidence_id: str
    document_id: str
    company: str
    ticker: str
    fiscal_period: str
    modality: str
    page_or_section: str
    raw_text: str
    source_span: SourceSpan
    normalized_metric: Optional[str] = None
    numeric_value: Optional[Decimal] = None
    unit: Optional[str] = None
    currency: Optional[str] = None

    @classmethod
    def from_document(
        cls,
        document: DocumentMetadata,
        modality: str,
        page_or_section: str,
        raw_text: str,
        source_span: SourceSpan,
        normalized_metric: Optional[str] = None,
        numeric_value: Optional[Decimal] = None,
        unit: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> "EvidenceUnit":
        fiscal_period = f"{document.fiscal_year}-{document.fiscal_quarter}"
        evidence_id = stable_evidence_id(
            document.document_id,
            modality,
            page_or_section,
            raw_text,
            normalized_metric or "",
            str(numeric_value) if numeric_value is not None else "",
        )
        return cls(
            evidence_id=evidence_id,
            document_id=document.document_id,
            company=document.company,
            ticker=document.ticker,
            fiscal_period=fiscal_period,
            modality=modality,
            page_or_section=page_or_section,
            raw_text=raw_text,
            source_span=source_span,
            normalized_metric=normalized_metric,
            numeric_value=numeric_value,
            unit=unit,
            currency=currency,
        )


def stable_evidence_id(*parts: str) -> str:
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
