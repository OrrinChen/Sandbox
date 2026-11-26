"""XBRL company facts extraction."""

from __future__ import annotations

from decimal import Decimal
from typing import List, Mapping, Tuple

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.metrics import normalize_metric
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


def extract_xbrl_facts(
    document: DocumentMetadata,
    companyfacts_payload: Mapping[str, object],
) -> Tuple[EvidenceUnit, ...]:
    """Extract known financial metrics from SEC company facts into evidence units."""

    facts = companyfacts_payload.get("facts")
    if not isinstance(facts, Mapping):
        raise ValueError("company facts payload missing facts mapping")

    units: List[EvidenceUnit] = []
    for taxonomy, taxonomy_facts in facts.items():
        if not isinstance(taxonomy_facts, Mapping):
            continue
        for raw_metric, metric_payload in taxonomy_facts.items():
            metric_name = normalize_metric(f"{taxonomy}:{raw_metric}") or normalize_metric(str(raw_metric))
            if metric_name is None or not isinstance(metric_payload, Mapping):
                continue

            unit_payload = metric_payload.get("units")
            if not isinstance(unit_payload, Mapping):
                continue

            for unit, unit_facts in unit_payload.items():
                if not isinstance(unit_facts, list):
                    continue
                for index, fact in enumerate(unit_facts):
                    if not _matches_document_period(fact, document):
                        continue
                    numeric_value = Decimal(str(fact["val"]))
                    label = f"{taxonomy}:{raw_metric}:{unit}:{index}"
                    raw_text = (
                        f"{raw_metric} {document.fiscal_year} {document.fiscal_quarter} "
                        f"= {numeric_value} {unit}"
                    )
                    units.append(
                        EvidenceUnit.from_document(
                            document=document,
                            modality="xbrl",
                            page_or_section=label,
                            raw_text=raw_text,
                            source_span=SourceSpan(start=index, end=index + 1, label=label),
                            normalized_metric=metric_name,
                            numeric_value=numeric_value,
                            unit=str(unit),
                            currency=str(unit) if str(unit).isupper() and len(str(unit)) == 3 else None,
                        )
                    )

    return tuple(units)


def _matches_document_period(fact: object, document: DocumentMetadata) -> bool:
    return (
        isinstance(fact, Mapping)
        and fact.get("fy") == document.fiscal_year
        and fact.get("fp") == document.fiscal_quarter
        and "val" in fact
    )
