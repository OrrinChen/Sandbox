"""Simple table extraction for markdown-style financial tables."""

from __future__ import annotations

from decimal import Decimal
import re
from typing import List, Sequence, Tuple

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.metrics import normalize_metric, parse_unit_and_currency
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


def extract_markdown_table(
    document: DocumentMetadata,
    markdown_table: str,
    page_or_section: str,
) -> Tuple[EvidenceUnit, ...]:
    """Extract normalized numeric evidence from a markdown table."""

    rows = _parse_markdown_rows(markdown_table)
    if len(rows) < 2:
        return ()

    header = rows[0]
    body = [row for row in rows[1:] if not _is_separator_row(row)]
    metric_index = _find_column(header, "metric")
    unit_index = _find_column(header, "unit")
    value_index = _first_value_column(header, metric_index, unit_index)

    units: List[EvidenceUnit] = []
    for row_index, row in enumerate(body):
        if len(row) <= max(metric_index, value_index, unit_index):
            continue
        normalized_metric = normalize_metric(row[metric_index])
        if normalized_metric is None:
            continue
        numeric_value = _parse_decimal(row[value_index])
        unit, currency = parse_unit_and_currency(row[unit_index])
        raw_text = " | ".join(row)
        units.append(
            EvidenceUnit.from_document(
                document=document,
                modality="table",
                page_or_section=page_or_section,
                raw_text=raw_text,
                source_span=SourceSpan(start=row_index, end=row_index + 1, label=f"{page_or_section}:row:{row_index}"),
                normalized_metric=normalized_metric,
                numeric_value=numeric_value,
                unit=unit,
                currency=currency,
            )
        )

    return tuple(units)


def _parse_markdown_rows(markdown_table: str) -> List[List[str]]:
    rows = []
    for line in markdown_table.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


def _is_separator_row(row: Sequence[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in row)


def _find_column(header: Sequence[str], name: str) -> int:
    for index, column in enumerate(header):
        if column.strip().lower() == name:
            return index
    raise ValueError(f"table missing {name} column")


def _first_value_column(header: Sequence[str], metric_index: int, unit_index: int) -> int:
    for index, _column in enumerate(header):
        if index not in {metric_index, unit_index}:
            return index
    raise ValueError("table missing numeric value column")


def _parse_decimal(raw_value: str) -> Decimal:
    cleaned = raw_value.replace(",", "").replace("$", "").strip()
    return Decimal(cleaned)
