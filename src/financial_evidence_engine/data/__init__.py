"""Data ingestion package."""

from financial_evidence_engine.data.cache import CachedPayload, SourceCache, stable_json_hash
from financial_evidence_engine.data.document_registry import (
    align_documents_by_company_period,
    build_registry_for_company,
)
from financial_evidence_engine.data.ingestion import SecIngestionResult, ingest_sec_company
from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.data.sec_client import SecClient

__all__ = [
    "CachedPayload",
    "DocumentMetadata",
    "SecClient",
    "SecIngestionResult",
    "SourceCache",
    "align_documents_by_company_period",
    "build_registry_for_company",
    "ingest_sec_company",
    "stable_json_hash",
]
