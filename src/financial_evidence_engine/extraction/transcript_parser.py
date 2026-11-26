"""Earnings transcript parsing into speaker evidence units."""

from __future__ import annotations

import re
from typing import List, Tuple

from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan


SECTION_NAMES = {
    "prepared remarks": "Prepared Remarks",
    "presentation": "Prepared Remarks",
    "question and answer": "Question and Answer",
    "questions and answers": "Question and Answer",
    "q&a": "Question and Answer",
}

SPEAKER_PATTERN = re.compile(r"^[A-Z][A-Za-z .'-]+ - [A-Za-z][A-Za-z &'/-]+$")


def extract_transcript_sections(document: DocumentMetadata, transcript_text: str) -> Tuple[EvidenceUnit, ...]:
    """Split transcript text by section and speaker."""

    lines = [line.strip() for line in transcript_text.splitlines() if line.strip()]
    units: List[EvidenceUnit] = []
    current_section = "Transcript"
    current_speaker = None
    current_lines: List[str] = []
    search_start = 0

    for line in lines:
        section = SECTION_NAMES.get(line.lower())
        if section is not None:
            units.extend(_flush(document, current_section, current_speaker, current_lines, transcript_text, search_start))
            search_start = _advance_search_start(transcript_text, current_lines, search_start)
            current_section = section
            current_speaker = None
            current_lines = []
            continue

        if SPEAKER_PATTERN.match(line):
            units.extend(_flush(document, current_section, current_speaker, current_lines, transcript_text, search_start))
            search_start = _advance_search_start(transcript_text, current_lines, search_start)
            current_speaker = line
            current_lines = []
            continue

        current_lines.append(line)

    units.extend(_flush(document, current_section, current_speaker, current_lines, transcript_text, search_start))
    return tuple(units)


def _flush(
    document: DocumentMetadata,
    section: str,
    speaker: str,
    lines: List[str],
    transcript_text: str,
    search_start: int,
) -> Tuple[EvidenceUnit, ...]:
    if speaker is None or not lines:
        return ()

    raw_text = " ".join(lines)
    start = transcript_text.find(lines[0], search_start)
    if start < 0:
        start = search_start
    end = start + len(raw_text)
    page_or_section = f"{section} / {speaker}"
    return (
        EvidenceUnit.from_document(
            document=document,
            modality="transcript",
            page_or_section=page_or_section,
            raw_text=raw_text,
            source_span=SourceSpan(start=start, end=end, label=page_or_section),
        ),
    )


def _advance_search_start(transcript_text: str, lines: List[str], search_start: int) -> int:
    if not lines:
        return search_start
    position = transcript_text.find(lines[-1], search_start)
    if position < 0:
        return search_start
    return position + len(lines[-1])
