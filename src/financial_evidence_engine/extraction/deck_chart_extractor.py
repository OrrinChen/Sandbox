"""Minimal investor-deck chart extraction and reconciliation.

This module intentionally supports a narrow, auditable slice: text-extractable
investor-deck PDF fixtures with explicit chart key/value lines. It is not a
general chart parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Iterable, Mapping, Optional, Tuple

from financial_evidence_engine.evaluation import (
    DueDiligenceTask,
    EvidenceRequirement,
    KnownDistractor,
    NumericCheckSpec,
)
from financial_evidence_engine.extraction.metrics import normalize_metric, parse_unit_and_currency
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan, stable_evidence_id


PDF_TEXT_PATTERN = re.compile(r"\(([^()]*)\)\s*Tj")
PAGE_PATTERN = re.compile(r"\bPAGE\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class DeckDocumentMetadata:
    """Traceable metadata for an investor-deck PDF."""

    document_id: str
    company: str
    ticker: str
    fiscal_year: int
    fiscal_quarter: str
    period_end_date: date
    publication_date: date
    source_url: str
    retrieved_at: datetime
    version_hash: str
    deck_title: str
    source_type: str = "investor_deck"

    @property
    def fiscal_period(self) -> str:
        return f"FY{self.fiscal_year}" if self.fiscal_quarter == "FY" else f"{self.fiscal_quarter} FY{self.fiscal_year}"

    def to_dict(self) -> Mapping[str, object]:
        return {
            "document_id": self.document_id,
            "company": self.company,
            "ticker": self.ticker,
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "period_end_date": self.period_end_date.isoformat(),
            "publication_date": self.publication_date.isoformat(),
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at.isoformat(),
            "version_hash": self.version_hash,
            "deck_title": self.deck_title,
            "source_type": self.source_type,
        }


@dataclass(frozen=True)
class DeckPage:
    """One extracted deck page."""

    document_id: str
    page_number: int
    text: str
    source_span: SourceSpan

    def to_dict(self) -> Mapping[str, object]:
        return {
            "document_id": self.document_id,
            "page_number": self.page_number,
            "text": self.text,
            "source_span": _span_to_dict(self.source_span),
        }


@dataclass(frozen=True)
class ChartEvidenceUnit:
    """Chart evidence extracted from an investor-deck page."""

    evidence_id: str
    document_id: str
    company: str
    company_ticker: str
    fiscal_period: str
    page_number: int
    chart_title: str
    metric: str
    numeric_value: Decimal
    unit: Optional[str]
    currency: Optional[str]
    extracted_text: str
    source_span: SourceSpan

    def to_evidence_unit(self) -> EvidenceUnit:
        return EvidenceUnit(
            evidence_id=self.evidence_id,
            document_id=self.document_id,
            company=self.company,
            ticker=self.company_ticker,
            fiscal_period=self.fiscal_period,
            modality="chart",
            page_or_section=f"Page {self.page_number} / {self.chart_title}",
            raw_text=self.extracted_text,
            source_span=self.source_span,
            normalized_metric=self.metric,
            numeric_value=self.numeric_value,
            unit=self.unit,
            currency=self.currency,
        )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "document_id": self.document_id,
            "company": self.company,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "page_number": self.page_number,
            "chart_title": self.chart_title,
            "metric": self.metric,
            "numeric_value": str(self.numeric_value),
            "unit": self.unit,
            "currency": self.currency,
            "extracted_text": self.extracted_text,
            "source_span": _span_to_dict(self.source_span),
        }


@dataclass(frozen=True)
class ChartVerificationIssue:
    """Issue surfaced during chart extraction or reconciliation."""

    issue_id: str
    issue_type: str
    severity: str
    message: str
    page_number: Optional[int] = None

    def to_dict(self) -> Mapping[str, object]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "page_number": self.page_number,
        }


@dataclass(frozen=True)
class ChartExtractionResult:
    """Deck page and chart extraction result."""

    deck: DeckDocumentMetadata
    pages: Tuple[DeckPage, ...]
    chart_evidence: Tuple[ChartEvidenceUnit, ...]
    issues: Tuple[ChartVerificationIssue, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "deck": self.deck.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
            "chart_evidence": [evidence.to_dict() for evidence in self.chart_evidence],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class ChartReconciliationRow:
    """Reconciliation result for one deck chart item against reference evidence."""

    chart_evidence_id: str
    reference_evidence_id: str
    company_ticker: str
    fiscal_period: str
    metric: str
    chart_value: Decimal
    normalized_chart_value: Decimal
    reference_value: Decimal
    unit: Optional[str]
    currency: Optional[str]
    difference: Decimal
    tolerance: Decimal
    status: str
    verdict: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "chart_evidence_id": self.chart_evidence_id,
            "reference_evidence_id": self.reference_evidence_id,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "metric": self.metric,
            "chart_value": str(self.chart_value),
            "normalized_chart_value": str(self.normalized_chart_value),
            "reference_value": str(self.reference_value),
            "unit": self.unit,
            "currency": self.currency,
            "difference": str(self.difference),
            "tolerance": str(self.tolerance),
            "status": self.status,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class DeckChartVerificationResult:
    """Claim-level verification result for the investor-deck chart slice."""

    claim_text: str
    final_verdict: str
    extraction_result: ChartExtractionResult
    reconciliation_rows: Tuple[ChartReconciliationRow, ...]
    issues: Tuple[ChartVerificationIssue, ...]
    text_only_failure_reason: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "claim_text": self.claim_text,
            "final_verdict": self.final_verdict,
            "extraction_result": self.extraction_result.to_dict(),
            "reconciliation_rows": [row.to_dict() for row in self.reconciliation_rows],
            "issues": [issue.to_dict() for issue in self.issues],
            "text_only_failure_reason": self.text_only_failure_reason,
        }


def extract_deck_chart_evidence(
    deck: DeckDocumentMetadata,
    pdf_path: Path,
) -> ChartExtractionResult:
    """Extract chart evidence from a text-extractable PDF fixture."""

    if not pdf_path.exists():
        issue = _issue("missing_pdf", "error", f"Deck PDF fixture does not exist: {pdf_path}")
        return ChartExtractionResult(deck=deck, pages=(), chart_evidence=(), issues=(issue,))

    raw_text = pdf_path.read_bytes().decode("latin-1", errors="ignore")
    extracted_lines = tuple(line.strip() for line in PDF_TEXT_PATTERN.findall(raw_text) if line.strip())
    if not extracted_lines:
        extracted_lines = tuple(line.strip() for line in raw_text.splitlines() if line.strip() and not line.startswith("%"))

    pages = _extract_pages(deck, extracted_lines)
    chart_evidence = tuple(
        evidence
        for evidence in (_chart_from_page(deck, page) for page in pages)
        if evidence is not None
    )
    issues = () if chart_evidence else (_issue("missing_chart_evidence", "error", "No chart key/value block was extracted."),)
    return ChartExtractionResult(deck=deck, pages=pages, chart_evidence=chart_evidence, issues=issues)


def reconcile_chart_evidence(
    chart: ChartEvidenceUnit,
    reference_evidence: Iterable[EvidenceUnit],
    tolerance: Decimal = Decimal("0"),
) -> Tuple[ChartReconciliationRow, ...]:
    """Compare deck chart evidence against XBRL or filing evidence."""

    rows = []
    normalized_chart_value = _normalize_chart_value(chart.numeric_value, chart.unit)
    for reference in reference_evidence:
        if not _reference_matches(chart, reference):
            continue
        assert reference.numeric_value is not None
        difference = abs(normalized_chart_value - reference.numeric_value)
        status = "pass" if difference <= tolerance else "fail"
        rows.append(
            ChartReconciliationRow(
                chart_evidence_id=chart.evidence_id,
                reference_evidence_id=reference.evidence_id,
                company_ticker=chart.company_ticker,
                fiscal_period=chart.fiscal_period,
                metric=chart.metric,
                chart_value=chart.numeric_value,
                normalized_chart_value=normalized_chart_value,
                reference_value=reference.numeric_value,
                unit=chart.unit,
                currency=chart.currency,
                difference=difference,
                tolerance=tolerance,
                status=status,
                verdict="support" if status == "pass" else "contradict",
            )
        )
    return tuple(rows)


def verify_deck_chart_claim(
    claim_text: str,
    extraction_result: ChartExtractionResult,
    reference_evidence: Iterable[EvidenceUnit],
) -> DeckChartVerificationResult:
    """Verify one deck-chart claim using extracted chart evidence and reference facts."""

    if not extraction_result.chart_evidence:
        issue = _issue(
            "missing_chart_evidence",
            "error",
            "Text-only retrieval cannot verify the deck chart claim because no chart value was extracted.",
        )
        return DeckChartVerificationResult(
            claim_text=claim_text,
            final_verdict="insufficient",
            extraction_result=extraction_result,
            reconciliation_rows=(),
            issues=(issue,),
            text_only_failure_reason=issue.message,
        )

    rows = []
    for chart in extraction_result.chart_evidence:
        rows.extend(reconcile_chart_evidence(chart, reference_evidence))
    if not rows:
        issue = _issue(
            "missing_reference_evidence",
            "error",
            "No matching XBRL or filing reference evidence was available for the deck chart value.",
        )
        return DeckChartVerificationResult(
            claim_text=claim_text,
            final_verdict="insufficient",
            extraction_result=extraction_result,
            reconciliation_rows=(),
            issues=(issue,),
            text_only_failure_reason="",
        )

    final_verdict = "support" if all(row.status == "pass" for row in rows) else "contradict"
    return DeckChartVerificationResult(
        claim_text=claim_text,
        final_verdict=final_verdict,
        extraction_result=extraction_result,
        reconciliation_rows=tuple(rows),
        issues=(),
        text_only_failure_reason="",
    )


def build_deck_chart_gap_task() -> DueDiligenceTask:
    """Build the Phase 10 chart-gap task without changing the 60-task seed set."""

    task_id = "phase10:nvda:deck_chart_gap"
    return DueDiligenceTask(
        task_id=task_id,
        family="chart_gap",
        question=(
            "Does NVIDIA's FY2024 investor-deck Data Center revenue chart reconcile "
            "to the corresponding XBRL filing fact?"
        ),
        claim_text="NVIDIA FY2024 Data Center revenue was $47.5 billion.",
        company_tickers=("NVDA",),
        fiscal_periods=("FY2024",),
        allowed_source_types=("investor_deck", "sec_xbrl_companyfacts"),
        expected_evidence=(
            EvidenceRequirement(
                requirement_id=f"{task_id}:ev1",
                source_type="investor_deck",
                modality="chart",
                company_ticker="NVDA",
                fiscal_period="FY2024",
                role="deck chart value",
                metric="revenue",
            ),
            EvidenceRequirement(
                requirement_id=f"{task_id}:ev2",
                source_type="sec_xbrl_companyfacts",
                modality="xbrl",
                company_ticker="NVDA",
                fiscal_period="FY2024",
                role="XBRL reported revenue fact",
                metric="revenue",
            ),
        ),
        numeric_checks=(
            NumericCheckSpec(
                check_id=f"{task_id}:num1",
                company_ticker="NVDA",
                fiscal_period="FY2024",
                metric="revenue",
                relation="reconcile_chart_to_xbrl",
            ),
        ),
        expected_verdict="support",
        known_distractors=(
            KnownDistractor(
                distractor_id=f"{task_id}:dist1",
                description="deck narrative without extracted chart value",
                reason="Text-only deck retrieval cannot validate a chart numeric claim.",
            ),
        ),
    )


def _extract_pages(deck: DeckDocumentMetadata, lines: Tuple[str, ...]) -> Tuple[DeckPage, ...]:
    if not lines:
        return ()

    page_number = 1
    page_lines = []
    for line in lines:
        match = PAGE_PATTERN.search(line)
        if match:
            page_number = int(match.group(1))
            continue
        page_lines.append(line)
    text = "\n".join(page_lines)
    return (
        DeckPage(
            document_id=deck.document_id,
            page_number=page_number,
            text=text,
            source_span=SourceSpan(start=0, end=len(lines), label=f"page:{page_number}"),
        ),
    )


def _chart_from_page(deck: DeckDocumentMetadata, page: DeckPage) -> Optional[ChartEvidenceUnit]:
    fields = _parse_key_values(page.text)
    chart_title = fields.get("chart")
    value = fields.get("value")
    raw_metric = fields.get("metric")
    raw_unit = fields.get("unit", "")
    if not chart_title or value is None or raw_metric is None:
        return None

    metric = normalize_metric(raw_metric) or raw_metric.strip().lower().replace(" ", "_")
    unit, currency = parse_unit_and_currency(raw_unit)
    extracted_text = (
        f"{chart_title}: {fields.get('company', deck.ticker)} "
        f"{fields.get('fiscal period', deck.fiscal_period)} {raw_metric} {value} {raw_unit}".strip()
    )
    evidence_id = stable_evidence_id(deck.document_id, "chart", chart_title, value, raw_unit)
    chart_start = max(page.text.find("CHART:"), 0)
    return ChartEvidenceUnit(
        evidence_id=evidence_id,
        document_id=deck.document_id,
        company=deck.company,
        company_ticker=fields.get("company", deck.ticker),
        fiscal_period=fields.get("fiscal period", deck.fiscal_period),
        page_number=page.page_number,
        chart_title=chart_title,
        metric=metric,
        numeric_value=Decimal(value.replace(",", "")),
        unit=unit,
        currency=currency,
        extracted_text=extracted_text,
        source_span=SourceSpan(
            start=chart_start,
            end=chart_start + len(extracted_text),
            label=f"page:{page.page_number}:chart:{chart_title}",
        ),
    )


def _parse_key_values(text: str) -> Mapping[str, str]:
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _reference_matches(chart: ChartEvidenceUnit, reference: EvidenceUnit) -> bool:
    return (
        reference.ticker == chart.company_ticker
        and reference.fiscal_period == chart.fiscal_period.replace("FY", "") + "-FY"
        and reference.normalized_metric == chart.metric
        and reference.numeric_value is not None
    )


def _normalize_chart_value(value: Decimal, unit: Optional[str]) -> Decimal:
    if unit == "billions":
        return value * Decimal("1000000000")
    if unit == "millions":
        return value * Decimal("1000000")
    if unit == "thousands":
        return value * Decimal("1000")
    return value


def _issue(issue_type: str, severity: str, message: str, page_number: Optional[int] = None) -> ChartVerificationIssue:
    return ChartVerificationIssue(
        issue_id=stable_evidence_id(issue_type, severity, message, str(page_number)),
        issue_type=issue_type,
        severity=severity,
        message=message,
        page_number=page_number,
    )


def _span_to_dict(span: SourceSpan) -> Mapping[str, object]:
    return {
        "start": span.start,
        "end": span.end,
        "label": span.label,
    }
