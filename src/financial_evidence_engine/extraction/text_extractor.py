"""SEC filing text extraction and section splitting."""

from __future__ import annotations

import html
import re
from typing import List, Tuple

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


SECTION_LABELS = {
    "1": "Item 1 - Business",
    "1A": "Item 1A - Risk Factors",
    "1B": "Item 1B - Unresolved Staff Comments",
    "2": "Item 2 - Properties",
    "3": "Item 3 - Legal Proceedings",
    "7": "Item 7 - MD&A",
    "7A": "Item 7A - Market Risk",
    "8": "Item 8 - Financial Statements",
}

ITEM_PATTERN = re.compile(r"(?im)^Item\s+(1A|1B|7A|1|2|3|7|8)\.?\s*(.*?)$")


def extract_10k_sections(document: DocumentMetadata, filing_html_or_text: str) -> Tuple[EvidenceUnit, ...]:
    """Chunk a 10-K filing into major SEC item sections."""

    plain_text = html_to_text(filing_html_or_text)
    matches = list(ITEM_PATTERN.finditer(plain_text))
    units: List[EvidenceUnit] = []

    for index, match in enumerate(matches):
        item_code = match.group(1).upper()
        section_label = SECTION_LABELS.get(item_code)
        if section_label is None:
            continue

        section_start = match.end()
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(plain_text)
        section_text = _collapse_whitespace(plain_text[section_start:section_end])
        if not section_text:
            continue

        units.append(
            EvidenceUnit.from_document(
                document=document,
                modality="text",
                page_or_section=section_label,
                raw_text=section_text,
                source_span=SourceSpan(start=section_start, end=section_end, label=section_label),
            )
        )

    return tuple(units)


def html_to_text(filing_html_or_text: str) -> str:
    """Convert simple SEC HTML/text content into section-splittable plain text."""

    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", filing_html_or_text)
    text = re.sub(r"(?i)</?(h[1-6]|p|div|br|tr|li)[^>]*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [_collapse_whitespace(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
