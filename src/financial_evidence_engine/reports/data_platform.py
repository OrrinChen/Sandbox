"""Data-platform artifact exports for the portfolio package."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from financial_evidence_engine.evaluation import DueDiligenceTaskSet, build_seed_task_set
from financial_evidence_engine.retrieval import build_raw_financial_corpus, run_real_retrieval_evaluation
from financial_evidence_engine.retrieval.raw_corpus import DocumentChunk, RawFinancialCorpus
from financial_evidence_engine.retrieval.real_baselines import RealRetrievalEvaluationResult


DATA_PLATFORM_TABLES: tuple[str, ...] = (
    "document_metadata.csv",
    "chunks.csv",
    "evidence_units.csv",
    "claims.csv",
    "citation_coverage.csv",
    "normalization_quality_checks.csv",
)


@dataclass(frozen=True)
class DataPlatformArtifactManifest:
    """Manifest for generated AI data-platform portfolio tables."""

    output_dir: Path
    table_paths: Mapping[str, Path]
    row_counts: Mapping[str, int]
    document_count: int
    chunk_count: int
    claim_count: int
    api_key_required: bool = False

    def to_dict(self) -> Mapping[str, object]:
        return {
            "output_dir": str(self.output_dir),
            "table_paths": {name: str(path) for name, path in self.table_paths.items()},
            "row_counts": dict(self.row_counts),
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "claim_count": self.claim_count,
            "api_key_required": self.api_key_required,
        }


def write_data_platform_artifacts(
    output_dir: Path = Path("reports/tables"),
    task_set: Optional[DueDiligenceTaskSet] = None,
    raw_corpus: Optional[RawFinancialCorpus] = None,
    retrieval_result: Optional[RealRetrievalEvaluationResult] = None,
) -> DataPlatformArtifactManifest:
    """Write data-platform view CSV artifacts from existing deterministic fixtures."""

    task_set = task_set or build_seed_task_set()
    raw_corpus = raw_corpus or build_raw_financial_corpus(task_set)
    retrieval_result = retrieval_result or run_real_retrieval_evaluation(
        task_set,
        corpus_mode="benchmark",
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    rows_by_table = {
        "document_metadata.csv": _document_metadata_rows(raw_corpus),
        "chunks.csv": _chunk_rows(raw_corpus.chunks),
        "evidence_units.csv": _evidence_unit_rows(task_set),
        "claims.csv": _claim_rows(task_set),
        "citation_coverage.csv": _citation_coverage_rows(retrieval_result),
        "normalization_quality_checks.csv": _normalization_quality_rows(task_set, raw_corpus, retrieval_result),
    }

    table_paths = {}
    row_counts = {}
    for table_name in DATA_PLATFORM_TABLES:
        rows = rows_by_table[table_name]
        table_path = output_dir / table_name
        _write_csv(table_path, rows)
        table_paths[table_name] = table_path
        row_counts[table_name] = len(rows)

    return DataPlatformArtifactManifest(
        output_dir=output_dir,
        table_paths=table_paths,
        row_counts=row_counts,
        document_count=row_counts["document_metadata.csv"],
        chunk_count=row_counts["chunks.csv"],
        claim_count=row_counts["claims.csv"],
    )


def _document_metadata_rows(raw_corpus: RawFinancialCorpus) -> list[Mapping[str, object]]:
    chunks_by_document: dict[str, list[DocumentChunk]] = defaultdict(list)
    for chunk in raw_corpus.chunks:
        chunks_by_document[chunk.provenance.document_id].append(chunk)

    rows = []
    for document_id, chunks in sorted(chunks_by_document.items()):
        first = chunks[0].provenance
        rows.append(
            {
                "document_id": document_id,
                "company_ticker": first.company_ticker,
                "company_name": first.company_name,
                "source_type": first.source_type,
                "fiscal_period": first.fiscal_period,
                "source_url": first.source_url,
                "source_hash": first.source_hash,
                "chunk_count": len(chunks),
                "modalities": _pipe_sorted(chunk.modality for chunk in chunks),
                "chunk_types": _pipe_sorted(chunk.chunk_type for chunk in chunks),
                "normalized_metrics": _pipe_sorted(
                    chunk.normalized_metric
                    for chunk in chunks
                    if chunk.normalized_metric
                ),
                "section_or_page_count": len({chunk.provenance.section_or_page for chunk in chunks}),
                "corpus_id": raw_corpus.manifest.corpus_id,
                "corpus_version_hash": raw_corpus.manifest.version_hash,
            }
        )
    return rows


def _chunk_rows(chunks: Sequence[DocumentChunk]) -> list[Mapping[str, object]]:
    return [
        {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.provenance.document_id,
            "chunk_type": chunk.chunk_type,
            "modality": chunk.modality,
            "company_ticker": chunk.provenance.company_ticker,
            "source_type": chunk.provenance.source_type,
            "fiscal_period": chunk.provenance.fiscal_period,
            "section_or_page": chunk.provenance.section_or_page,
            "source_span_start": chunk.provenance.source_span_start,
            "source_span_end": chunk.provenance.source_span_end,
            "text_length": len(chunk.text),
            "normalized_metric": chunk.normalized_metric or "",
            "numeric_value": str(chunk.numeric_value) if chunk.numeric_value is not None else "",
            "unit": chunk.unit or "",
            "currency": chunk.currency or "",
            "chunk_hash": chunk.chunk_hash,
            "source_hash": chunk.provenance.source_hash,
            "source_url": chunk.provenance.source_url,
        }
        for chunk in chunks
    ]


def _evidence_unit_rows(task_set: DueDiligenceTaskSet) -> list[Mapping[str, object]]:
    rows = []
    for task in task_set.tasks:
        for requirement in task.expected_evidence:
            rows.append(
                {
                    "evidence_id": requirement.requirement_id,
                    "task_id": task.task_id,
                    "evidence_role": "gold_requirement",
                    "company_ticker": requirement.company_ticker,
                    "source_type": requirement.source_type,
                    "modality": requirement.modality,
                    "fiscal_period": requirement.fiscal_period,
                    "page_or_section": requirement.role,
                    "normalized_metric": requirement.metric or "",
                    "min_count": requirement.min_count,
                    "expected_verdict": task.expected_verdict,
                    "requires_citation": task.requires_citation,
                }
            )
    return rows


def _claim_rows(task_set: DueDiligenceTaskSet) -> list[Mapping[str, object]]:
    return [
        {
            "claim_id": task.task_id,
            "family": task.family,
            "claim_text": task.claim_text,
            "question": task.question,
            "company_tickers": "|".join(task.company_tickers),
            "fiscal_periods": "|".join(task.fiscal_periods),
            "allowed_source_types": "|".join(task.allowed_source_types),
            "expected_verdict": task.expected_verdict,
            "requires_citation": task.requires_citation,
            "expected_evidence_count": len(task.expected_evidence),
            "numeric_check_count": len(task.numeric_checks),
            "known_distractor_count": len(task.known_distractors),
        }
        for task in task_set.tasks
    ]


def _citation_coverage_rows(result: RealRetrievalEvaluationResult) -> list[Mapping[str, object]]:
    rows = []
    for method, run in sorted(result.runs.items()):
        report = result.reports[method]
        retrieved = [evidence for prediction in run.predictions for evidence in prediction.retrieved_evidence]
        cited = [evidence for evidence in retrieved if evidence.cited]
        predictions_with_citation = sum(
            1
            for prediction in run.predictions
            if any(evidence.cited for evidence in prediction.retrieved_evidence)
        )
        rows.append(
            {
                "method": method,
                "corpus_mode": result.corpus_mode,
                "task_count": report.task_count,
                "predictions_with_citation": predictions_with_citation,
                "retrieved_evidence_count": len(retrieved),
                "cited_evidence_count": len(cited),
                "coverage_rate": _decimal_str(_ratio(predictions_with_citation, report.task_count)),
                "citation_exactness": _decimal_str(report.metrics["citation_exactness"]),
                "evidence_recall_at_k": _decimal_str(report.metrics["evidence_recall_at_k"]),
                "claim_boundary": "local deterministic evidence coverage; not broad SEC-scale ingestion",
            }
        )
    return rows


def _normalization_quality_rows(
    task_set: DueDiligenceTaskSet,
    raw_corpus: RawFinancialCorpus,
    result: RealRetrievalEvaluationResult,
) -> list[Mapping[str, object]]:
    full_engine = result.reports["full_engine_real"].metrics
    numeric_chunks = [chunk for chunk in raw_corpus.chunks if chunk.numeric_value is not None]
    unit_normalized = [chunk for chunk in numeric_chunks if chunk.unit and chunk.currency]
    period_chunks = [chunk for chunk in raw_corpus.chunks if chunk.provenance.fiscal_period]
    metric_chunks = [chunk for chunk in raw_corpus.chunks if chunk.normalized_metric]
    numeric_checks = [check for task in task_set.tasks for check in task.numeric_checks]
    numeric_checks_with_unit = [check for check in numeric_checks if check.expected_unit]

    return [
        _quality_row(
            "fiscal_period_chunk_coverage",
            "fiscal_period_normalization",
            len(period_chunks),
            len(raw_corpus.chunks),
            "raw_corpus",
            "Every raw chunk keeps an explicit fiscal period for retrieval filtering.",
        ),
        _quality_row(
            "unit_currency_numeric_chunk_coverage",
            "unit_normalization",
            len(unit_normalized),
            len(numeric_chunks),
            "raw_corpus",
            "Numeric chunks keep unit and currency when a value is present.",
        ),
        _quality_row(
            "metric_mapped_chunk_coverage",
            "metric_normalization",
            len(metric_chunks),
            len(raw_corpus.chunks),
            "raw_corpus",
            "Metric names are normalized where the local fixture exposes metric intent.",
        ),
        _quality_row(
            "numeric_check_unit_coverage",
            "unit_normalization",
            len(numeric_checks_with_unit),
            len(numeric_checks),
            "task_set",
            "Gold numeric checks carry expected units when the task requires numeric reconciliation.",
        ),
        _quality_metric_row(
            "full_engine_fiscal_period_correctness",
            "fiscal_period_normalization",
            full_engine["fiscal_period_correctness"],
            "real_retrieval_evaluation",
            "Full-engine retrieved evidence matches task fiscal periods.",
        ),
        _quality_metric_row(
            "full_engine_entity_correctness",
            "entity_normalization",
            full_engine["entity_correctness"],
            "real_retrieval_evaluation",
            "Full-engine retrieved evidence matches task companies.",
        ),
        _quality_metric_row(
            "full_engine_numeric_correctness",
            "numeric_reconciliation",
            full_engine["numeric_correctness"],
            "real_retrieval_evaluation",
            "Full-engine numeric checks pass when structured evidence is available.",
        ),
        _quality_metric_row(
            "full_engine_citation_exactness",
            "citation_validation",
            full_engine["citation_exactness"],
            "real_retrieval_evaluation",
            "Matched evidence is cited rather than used as decorative text.",
        ),
    ]


def _quality_row(
    check_id: str,
    check_type: str,
    passed_count: int,
    total_count: int,
    source: str,
    notes: str,
) -> Mapping[str, object]:
    return {
        "check_id": check_id,
        "check_type": check_type,
        "passed_count": passed_count,
        "total_count": total_count,
        "pass_rate": _decimal_str(_ratio(passed_count, total_count)),
        "source": source,
        "notes": notes,
    }


def _quality_metric_row(
    check_id: str,
    check_type: str,
    pass_rate: Decimal,
    source: str,
    notes: str,
) -> Mapping[str, object]:
    return {
        "check_id": check_id,
        "check_type": check_type,
        "passed_count": "",
        "total_count": "",
        "pass_rate": _decimal_str(pass_rate),
        "source": source,
        "notes": notes,
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _pipe_sorted(values: Iterable[object]) -> str:
    return "|".join(sorted({str(value) for value in values if value not in {None, ""}}))


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def _decimal_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))
