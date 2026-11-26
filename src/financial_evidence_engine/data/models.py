"""Shared data-layer models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DocumentMetadata:
    """Traceable source document metadata for downstream evidence units."""

    document_id: str
    company: str
    ticker: str
    cik: str
    source_type: str
    filing_type: str
    fiscal_year: int
    fiscal_quarter: str
    period_end_date: date
    publication_date: date
    filing_date: Optional[date]
    source_url: str
    retrieved_at: datetime
    version_hash: str
    accession_number: Optional[str] = None


@dataclass(frozen=True)
class CachedPayload:
    """Cached source payload plus reproducibility metadata."""

    payload_path: Path
    metadata_path: Path
    retrieved_at: datetime
    version_hash: str
