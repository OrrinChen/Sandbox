"""Document extraction package."""

from financial_evidence_engine.extraction.deck_chart_extractor import (
    ChartEvidenceUnit,
    ChartExtractionResult,
    ChartReconciliationRow,
    ChartVerificationIssue,
    DeckChartVerificationResult,
    DeckDocumentMetadata,
    DeckPage,
    build_deck_chart_gap_task,
    extract_deck_chart_evidence,
    reconcile_chart_evidence,
    verify_deck_chart_claim,
)
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan
from financial_evidence_engine.extraction.table_extractor import extract_markdown_table
from financial_evidence_engine.extraction.text_extractor import extract_10k_sections, html_to_text
from financial_evidence_engine.extraction.transcript_parser import extract_transcript_sections
from financial_evidence_engine.extraction.xbrl_extractor import extract_xbrl_facts

__all__ = [
    "ChartEvidenceUnit",
    "ChartExtractionResult",
    "ChartReconciliationRow",
    "ChartVerificationIssue",
    "DeckChartVerificationResult",
    "DeckDocumentMetadata",
    "DeckPage",
    "EvidenceUnit",
    "SourceSpan",
    "build_deck_chart_gap_task",
    "extract_10k_sections",
    "extract_deck_chart_evidence",
    "extract_markdown_table",
    "extract_transcript_sections",
    "extract_xbrl_facts",
    "html_to_text",
    "reconcile_chart_evidence",
    "verify_deck_chart_claim",
]
