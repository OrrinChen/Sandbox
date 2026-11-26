"""Portfolio-ready technical report generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Tuple

from financial_evidence_engine.bundled import DECK_FIXTURE
from financial_evidence_engine.case_studies import PortfolioCaseStudy, build_portfolio_case_studies
from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evaluation import (
    build_adversarial_evaluation_report,
    build_phase7_evaluation_report,
    build_seed_task_set,
)
from financial_evidence_engine.extraction import (
    DeckDocumentMetadata,
    SourceSpan,
    build_deck_chart_gap_task,
    extract_deck_chart_evidence,
    verify_deck_chart_claim,
)
from financial_evidence_engine.extraction.models import EvidenceUnit
from financial_evidence_engine.reports.final_report import REPRODUCIBILITY_COMMANDS, RESUME_BULLET_LONG
from financial_evidence_engine.retrieval import run_real_retrieval_evaluation


REPORT_TITLE = "Multimodal Financial Due-Diligence Evidence Engine"
REPORT_SECTION_TITLES: Tuple[str, ...] = (
    "Problem: ordinary RAG is unsafe for financial due diligence",
    "System overview",
    "Evidence graph and validators",
    "Real retrieval benchmark",
    "Three failure case studies",
    "Investor deck and chart extraction case",
    "Ablation results",
    "Limitations",
    "Reproducibility",
    "Resume bullet",
)


@dataclass(frozen=True)
class PortfolioReportSection:
    """One report section rendered to Markdown and PDF text."""

    title: str
    body_lines: Tuple[str, ...]

    def to_markdown(self, index: int) -> str:
        lines = [f"## {index}. {self.title}", ""]
        lines.extend(self.body_lines)
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class FigureSpec:
    """Portable figure spec written as JSON for report reproducibility."""

    figure_id: str
    title: str
    figure_type: str
    values: Mapping[str, object]
    insight: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "figure_id": self.figure_id,
            "title": self.title,
            "figure_type": self.figure_type,
            "values": _jsonable(self.values),
            "insight": self.insight,
        }


@dataclass(frozen=True)
class TableSpec:
    """Portable table spec written as JSON for report reproducibility."""

    table_id: str
    title: str
    columns: Tuple[str, ...]
    rows: Tuple[Mapping[str, object], ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "table_id": self.table_id,
            "title": self.title,
            "columns": list(self.columns),
            "rows": [_jsonable(row) for row in self.rows],
        }


@dataclass(frozen=True)
class PortfolioReportPackage:
    """Complete Phase 17 report package before writing files."""

    title: str
    sections: Tuple[PortfolioReportSection, ...]
    figures: Tuple[FigureSpec, ...]
    tables: Tuple[TableSpec, ...]
    resume_bullet: str
    case_study_count: int

    @property
    def page_count(self) -> int:
        return len(self.sections)

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        for index, section in enumerate(self.sections, start=1):
            lines.append(section.to_markdown(index).rstrip())
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def pdf_pages(self) -> Tuple[Tuple[str, ...], ...]:
        return tuple(
            (section.title,) + _wrap_lines(section.body_lines)
            for section in self.sections
        )


@dataclass(frozen=True)
class PortfolioReportArtifactManifest:
    """Files written by the Phase 17 portfolio report builder."""

    pdf_path: Path
    markdown_path: Path
    figure_paths: Tuple[Path, ...]
    table_paths: Tuple[Path, ...]
    resume_bullet_path: Path
    manifest_path: Path
    page_count: int

    def to_dict(self) -> Mapping[str, object]:
        return {
            "pdf_path": str(self.pdf_path),
            "markdown_path": str(self.markdown_path),
            "figure_paths": [str(path) for path in self.figure_paths],
            "table_paths": [str(path) for path in self.table_paths],
            "resume_bullet_path": str(self.resume_bullet_path),
            "manifest_path": str(self.manifest_path),
            "page_count": self.page_count,
        }


def build_portfolio_report_package() -> PortfolioReportPackage:
    """Build a 10-section technical report from deterministic local artifacts."""

    task_set = build_seed_task_set()
    phase7_report = build_phase7_evaluation_report(task_set)
    real_retrieval = run_real_retrieval_evaluation(task_set)
    case_studies = build_portfolio_case_studies(task_set, real_retrieval)
    adversarial_report = build_adversarial_evaluation_report()
    deck_summary = _deck_chart_summary()

    figures = _build_figures(phase7_report, real_retrieval, case_studies, adversarial_report, deck_summary)
    tables = _build_tables(case_studies, deck_summary)
    sections = _build_sections(
        phase7_report=phase7_report,
        real_retrieval=real_retrieval,
        case_studies=case_studies,
        adversarial_report=adversarial_report,
        deck_summary=deck_summary,
    )
    return PortfolioReportPackage(
        title=REPORT_TITLE,
        sections=sections,
        figures=figures,
        tables=tables,
        resume_bullet=RESUME_BULLET_LONG,
        case_study_count=len(case_studies),
    )


def write_portfolio_report_artifacts(
    package: PortfolioReportPackage,
    reports_dir: Path = Path("reports"),
) -> PortfolioReportArtifactManifest:
    """Write Markdown, PDF, figure specs, table specs, resume bullet, and manifest."""

    figures_dir = reports_dir / "figures"
    tables_dir = reports_dir / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = reports_dir / "final_report.pdf"
    markdown_path = reports_dir / "final_report.md"
    resume_bullet_path = reports_dir / "resume_bullet.txt"
    manifest_path = reports_dir / "portfolio_report_manifest.json"

    markdown_path.write_text(package.to_markdown(), encoding="utf-8")
    _write_pdf(pdf_path, package.title, package.pdf_pages())
    resume_bullet_path.write_text(package.resume_bullet.rstrip() + "\n", encoding="utf-8")

    figure_paths = []
    for figure in package.figures:
        path = figures_dir / f"{figure.figure_id}.json"
        path.write_text(json.dumps(figure.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        figure_paths.append(path)

    table_paths = []
    for table in package.tables:
        path = tables_dir / f"{table.table_id}.json"
        path.write_text(json.dumps(table.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        table_paths.append(path)

    manifest = PortfolioReportArtifactManifest(
        pdf_path=pdf_path,
        markdown_path=markdown_path,
        figure_paths=tuple(figure_paths),
        table_paths=tuple(table_paths),
        resume_bullet_path=resume_bullet_path,
        manifest_path=manifest_path,
        page_count=package.page_count,
    )
    manifest_payload = {
        **manifest.to_dict(),
        "case_study_count": package.case_study_count,
        "includes_limitations": any(section.title == "Limitations" for section in package.sections),
        "includes_reproducibility": any(section.title == "Reproducibility" for section in package.sections),
        "resume_bullet": package.resume_bullet,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _build_sections(
    phase7_report,
    real_retrieval,
    case_studies: Tuple[PortfolioCaseStudy, ...],
    adversarial_report,
    deck_summary: Mapping[str, object],
) -> Tuple[PortfolioReportSection, ...]:
    full_report = real_retrieval.reports["full_engine_real"]
    bm25_report = real_retrieval.reports["bm25_real"]
    ablation_rows = [
        f"- `{method}` verdict accuracy `{report.metrics['verdict_accuracy']}`"
        for method, report in phase7_report.ablation_reports.items()
    ]
    case_rows = [
        f"- `{case.case_id}`: `{case.failure_mode}`, verdict `{case.final_full_engine_verdict}`"
        for case in case_studies
    ]
    return (
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[0],
            body_lines=(
                "Ordinary RAG can return fluent financial answers while mixing fiscal periods, units, sources, or unsupported management narratives.",
                "This project frames due diligence as claim-level evidence verification rather than chatbot answer generation.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[1],
            body_lines=(
                "Pipeline: claim decomposition -> retrieval -> evidence graph linking -> financial normalization -> validator gates -> auditable memo.",
                "The local corpus covers SEC/XBRL facts, filings, transcripts, tables, raw chunks, investor-deck pages, and chart evidence fixtures.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[2],
            body_lines=(
                "Evidence nodes are tied to company, period, source type, modality, metric, and provenance.",
                "Validators check citation support, fiscal periods, entity/source consistency, numeric reconciliation, unsupported claims, contradictions, and red-team failure modes.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[3],
            body_lines=(
                f"Real retrieval benchmark: `{real_retrieval.task_count}` tasks over `{real_retrieval.corpus_document_count}` benchmark documents.",
                f"BM25 verdict accuracy: `{bm25_report.metrics['verdict_accuracy']}`.",
                f"Full engine verdict accuracy: `{full_report.metrics['verdict_accuracy']}` with `{len(real_retrieval.failure_cases)}` surfaced failure cases.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[4],
            body_lines=tuple(case_rows),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[5],
            body_lines=(
                f"Claim: {deck_summary['claim_text']}",
                f"Deck pages: `{deck_summary['deck_pages']}`, chart evidence: `{deck_summary['chart_evidence']}`, reconciliation rows: `{deck_summary['reconciliation_rows']}`.",
                f"Verdict: `{deck_summary['verdict']}` for NVIDIA FY2024 Data Center revenue after chart-to-XBRL reconciliation.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[6],
            body_lines=tuple(ablation_rows),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[7],
            body_lines=(
                "The raw corpus is still a deterministic local fixture, not a broad live SEC paragraph index.",
                "Dense retrieval defaults to an offline deterministic proxy; optional real embedding providers are skipped unless available.",
                "The chart extraction slice is narrow and text-extractable; broad chart parsing remains future work.",
                f"Red-team detection accuracy is `{adversarial_report.full_engine_accuracy}`, not perfect by design.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[8],
            body_lines=(
                "One-command portfolio report generation: `python3 scripts/build_portfolio_report.py`.",
                "Trace reproduction: `python3 scripts/smoke_trace_reproducibility.py`.",
                "Full local validation remains offline and deterministic; no API key is required.",
            ),
        ),
        PortfolioReportSection(
            title=REPORT_SECTION_TITLES[9],
            body_lines=(RESUME_BULLET_LONG,),
        ),
    )


def _build_figures(
    phase7_report,
    real_retrieval,
    case_studies: Tuple[PortfolioCaseStudy, ...],
    adversarial_report,
    deck_summary: Mapping[str, object],
) -> Tuple[FigureSpec, ...]:
    return (
        FigureSpec(
            figure_id="method_comparison",
            title="Method comparison",
            figure_type="bar",
            values={
                method: report.metrics["verdict_accuracy"]
                for method, report in real_retrieval.reports.items()
            },
            insight="Validator-augmented retrieval outperforms retrieval-only methods on verdict accuracy.",
        ),
        FigureSpec(
            figure_id="failure_mode_breakdown",
            title="Failure mode breakdown",
            figure_type="bar",
            values=adversarial_report.failure_mode_counts,
            insight="Red-team tasks cover period, entity, unit, citation, unsupported, deck-only, and transcript-only failure families.",
        ),
        FigureSpec(
            figure_id="validator_coverage",
            title="Validator coverage",
            figure_type="matrix",
            values=adversarial_report.validator_coverage_matrix,
            insight="Each adversarial failure mode has a validator owner.",
        ),
        FigureSpec(
            figure_id="case_study_flow",
            title="Case study flow",
            figure_type="flow",
            values={case.case_id: case.failure_mode for case in case_studies},
            insight="Portfolio cases map real retrieval failures to validator explanations.",
        ),
        FigureSpec(
            figure_id="chart_evidence_reconciliation",
            title="Chart evidence reconciliation",
            figure_type="reconciliation",
            values=deck_summary,
            insight="The investor-deck chart value is reconciled against XBRL evidence instead of treated as decorative text.",
        ),
    )


def _build_tables(
    case_studies: Tuple[PortfolioCaseStudy, ...],
    deck_summary: Mapping[str, object],
) -> Tuple[TableSpec, ...]:
    return (
        TableSpec(
            table_id="case_study_summary",
            title="Case study summary",
            columns=("case_id", "failure_mode", "task_id", "final_verdict"),
            rows=tuple(
                {
                    "case_id": case.case_id,
                    "failure_mode": case.failure_mode,
                    "task_id": case.task_id,
                    "final_verdict": case.final_full_engine_verdict,
                }
                for case in case_studies
            ),
        ),
        TableSpec(
            table_id="deck_reconciliation",
            title="Investor deck reconciliation",
            columns=("claim", "deck_pages", "chart_evidence", "reconciliation_rows", "verdict"),
            rows=(deck_summary,),
        ),
        TableSpec(
            table_id="reproducibility_commands",
            title="Reproducibility commands",
            columns=("step", "command"),
            rows=tuple(
                {"step": index, "command": command}
                for index, command in enumerate(REPRODUCIBILITY_COMMANDS, start=1)
            ),
        ),
    )


def _deck_chart_summary() -> Mapping[str, object]:
    deck = DeckDocumentMetadata(
        document_id="NVDA:investor_deck:FY2024:data_center_fixture",
        company="NVIDIA Corporation",
        ticker="NVDA",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 1, 28),
        publication_date=date(2024, 2, 21),
        source_url="fixture://nvda_fy2024_data_center_chart.pdf",
        retrieved_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        version_hash="1" * 64,
        deck_title="NVIDIA FY2024 Investor Presentation",
    )
    extraction = extract_deck_chart_evidence(
        deck,
        DECK_FIXTURE,
    )
    task = build_deck_chart_gap_task()
    verification = verify_deck_chart_claim(
        task.claim_text,
        extraction,
        (_xbrl_reference_unit(),),
    )
    return {
        "claim_text": task.claim_text,
        "deck_pages": len(extraction.pages),
        "chart_evidence": len(extraction.chart_evidence),
        "reconciliation_rows": len(verification.reconciliation_rows),
        "verdict": verification.final_verdict,
    }


def _xbrl_reference_unit() -> EvidenceUnit:
    document = DocumentMetadata(
        document_id="NVDA:sec_xbrl_companyfacts:2024:FY",
        company="NVIDIA Corporation",
        ticker="NVDA",
        cik="0001045810",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 1, 28),
        publication_date=date(2024, 2, 21),
        filing_date=date(2024, 2, 21),
        source_url="fixture://nvda-companyfacts-2024.json",
        retrieved_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        version_hash="2" * 64,
        accession_number="0001045810-24-000029",
    )
    return EvidenceUnit.from_document(
        document=document,
        modality="xbrl",
        page_or_section="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        raw_text="Data Center revenue FY2024 = 47500000000 USD",
        source_span=SourceSpan(start=0, end=1, label="us-gaap:DataCenterRevenue:USD:0"),
        normalized_metric="revenue",
        numeric_value=Decimal("47500000000"),
        unit="USD",
        currency="USD",
    )


def _write_pdf(path: Path, title: str, pages: Sequence[Sequence[str]]) -> None:
    objects = []
    page_object_ids = []
    font_object_id = 3
    next_object_id = 4
    for page_lines in pages:
        page_object_id = next_object_id
        content_object_id = next_object_id + 1
        next_object_id += 2
        page_object_ids.append(page_object_id)
        stream = _pdf_text_stream((title,) + tuple(page_lines))
        objects.append(
            (
                page_object_id,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>",
            )
        )
        objects.append(
            (
                content_object_id,
                f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
            )
        )

    kids = " ".join(f"{object_id} 0 R" for object_id in page_object_ids)
    header_objects = [
        (1, "<< /Type /Catalog /Pages 2 0 R >>"),
        (2, f"<< /Type/Pages /Kids [{kids}] /Count {len(page_object_ids)} >>"),
        (font_object_id, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ]
    all_objects = sorted(header_objects + objects, key=lambda item: item[0])
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in all_objects:
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(all_objects) + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f\n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n\n".encode("latin-1"))
    output.extend(
        (
            "trailer\n"
            f"<< /Size {len(all_objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("latin-1")
    )
    path.write_bytes(bytes(output))


def _pdf_text_stream(lines: Sequence[str]) -> str:
    output = ["BT", "/F1 10 Tf", "50 760 Td", "13 TL"]
    for line in lines[:46]:
        output.append(f"({_pdf_escape(line[:94])}) Tj")
        output.append("T*")
    output.append("ET")
    return "\n".join(output)


def _pdf_escape(text: str) -> str:
    ascii_text = text.encode("latin-1", errors="replace").decode("latin-1")
    return ascii_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(lines: Iterable[str], width: int = 92) -> Tuple[str, ...]:
    wrapped = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        remaining = line
        while len(remaining) > width:
            split_at = remaining.rfind(" ", 0, width)
            if split_at <= 0:
                split_at = width
            wrapped.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        if remaining:
            wrapped.append(remaining)
    return tuple(wrapped)


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
