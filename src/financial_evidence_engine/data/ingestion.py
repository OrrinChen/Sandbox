"""Phase 1 SEC source ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

from financial_evidence_engine.config import CompanyUniverseEntry
from financial_evidence_engine.data.cache import SourceCache
from financial_evidence_engine.data.document_registry import build_registry_for_company
from financial_evidence_engine.data.models import CachedPayload, DocumentMetadata


@dataclass(frozen=True)
class SecIngestionResult:
    """Cached SEC payloads and resulting document metadata."""

    documents: Tuple[DocumentMetadata, ...]
    cached_payloads: Dict[str, CachedPayload]


def ingest_sec_company(
    company: CompanyUniverseEntry,
    sec_client,
    cache: SourceCache,
    retrieved_at: datetime,
) -> SecIngestionResult:
    """Fetch, cache, and register SEC submissions and XBRL company facts for one company."""

    submissions_payload = sec_client.fetch_submissions(company.cik)
    companyfacts_payload = sec_client.fetch_companyfacts(company.cik)

    cached_payloads = {
        "submissions": cache.write_json(
            f"sec/submissions/{company.ticker}.json",
            submissions_payload,
            retrieved_at=retrieved_at,
        ),
        "companyfacts": cache.write_json(
            f"sec/companyfacts/{company.ticker}.json",
            companyfacts_payload,
            retrieved_at=retrieved_at,
        ),
    }

    documents = build_registry_for_company(
        company=company,
        submissions_payload=submissions_payload,
        companyfacts_payload=companyfacts_payload,
        retrieved_at=retrieved_at,
    )

    return SecIngestionResult(documents=documents, cached_payloads=cached_payloads)
