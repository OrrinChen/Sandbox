"""Smoke check for AI data platform framing artifacts."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CsvArtifactSpec:
    path: Path
    required_columns: frozenset[str]


CSV_ARTIFACTS = (
    CsvArtifactSpec(
        path=Path("reports/tables/document_metadata.csv"),
        required_columns=frozenset(
            {
                "document_id",
                "company_ticker",
                "company_name",
                "source_type",
                "fiscal_period",
                "source_url",
                "source_hash",
                "corpus_version_hash",
            }
        ),
    ),
    CsvArtifactSpec(
        path=Path("reports/tables/chunks.csv"),
        required_columns=frozenset(
            {
                "chunk_id",
                "document_id",
                "chunk_type",
                "modality",
                "source_type",
                "company_ticker",
                "fiscal_period",
                "text_length",
                "chunk_hash",
                "source_hash",
            }
        ),
    ),
    CsvArtifactSpec(
        path=Path("reports/tables/evidence_units.csv"),
        required_columns=frozenset(
            {
                "evidence_id",
                "task_id",
                "evidence_role",
                "company_ticker",
                "source_type",
                "modality",
                "fiscal_period",
                "normalized_metric",
                "requires_citation",
            }
        ),
    ),
    CsvArtifactSpec(
        path=Path("reports/tables/claims.csv"),
        required_columns=frozenset(
            {
                "claim_id",
                "claim_text",
                "company_tickers",
                "fiscal_periods",
                "allowed_source_types",
                "expected_verdict",
                "requires_citation",
                "expected_evidence_count",
            }
        ),
    ),
    CsvArtifactSpec(
        path=Path("reports/tables/citation_coverage.csv"),
        required_columns=frozenset(
            {
                "method",
                "task_count",
                "coverage_rate",
                "citation_exactness",
                "evidence_recall_at_k",
                "claim_boundary",
            }
        ),
    ),
    CsvArtifactSpec(
        path=Path("reports/tables/normalization_quality_checks.csv"),
        required_columns=frozenset(
            {
                "check_id",
                "check_type",
                "pass_rate",
                "source",
                "notes",
            }
        ),
    ),
)

TEXT_ARTIFACTS = (
    Path("README.md"),
    Path("PORTFOLIO.md"),
    Path("docs/data_platform_framing.md"),
)

FORBIDDEN_PUBLIC_CLAIMS = (
    "full sec archive",
    "trained neural retriever",
    "general chart parser",
)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    assert path.exists(), f"missing CSV artifact: {path}"
    assert path.stat().st_size > 0, f"empty CSV artifact: {path}"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows


def _assert_csv_artifact(spec: CsvArtifactSpec) -> int:
    rows = _read_csv_rows(spec.path)
    assert rows, f"CSV artifact has no data rows: {spec.path}"

    fieldnames = set(rows[0].keys())
    missing_columns = spec.required_columns - fieldnames
    assert not missing_columns, (
        f"{spec.path} missing required columns: {sorted(missing_columns)}"
    )

    for index, row in enumerate(rows, start=2):
        non_empty_values = [value for value in row.values() if value and value.strip()]
        assert non_empty_values, f"{spec.path}:{index} has no populated fields"

    return len(rows)


def _assert_quality_rows(path: Path) -> int:
    rows = _read_csv_rows(path)
    assert rows, f"{path} has no quality-check rows"

    id_column = "check_id" if "check_id" in rows[0] else "method"
    quality_ids = {row.get(id_column, "").strip() for row in rows}
    assert all(quality_ids), f"{path} contains unnamed quality checks"

    metric_columns = (
        "pass_rate",
        "coverage_rate",
        "citation_exactness",
        "evidence_recall_at_k",
    )
    populated_metric_rows = 0
    for row in rows:
        for column in metric_columns:
            value = row.get(column, "").strip()
            if value:
                metric_value = float(value)
                assert 0 <= metric_value <= 1, f"{path} has invalid {column}: {value}"
                populated_metric_rows += 1
    assert populated_metric_rows, f"{path} has no populated quality metrics"
    return len(rows)


def validate_csv_artifacts() -> dict[str, int]:
    return {
        str(spec.path): _assert_csv_artifact(spec)
        for spec in CSV_ARTIFACTS
    }


def validate_quality_artifacts() -> dict[str, int]:
    return {
        "citation_quality_checks": _assert_quality_rows(
            Path("reports/tables/citation_coverage.csv")
        ),
        "normalization_quality_checks": _assert_quality_rows(
            Path("reports/tables/normalization_quality_checks.csv")
        ),
    }


def validate_text_framing() -> None:
    for path in TEXT_ARTIFACTS:
        assert path.exists(), f"missing text artifact: {path}"

    combined = "\n".join(path.read_text(encoding="utf-8") for path in TEXT_ARTIFACTS)
    lower = combined.lower()

    assert "Data Platform View" in combined
    assert "document_metadata.csv" in combined
    assert "chunks.csv" in combined
    assert "evidence_units.csv" in combined
    assert "citation_coverage.csv" in combined
    assert "normalization_quality_checks.csv" in combined

    for forbidden in FORBIDDEN_PUBLIC_CLAIMS:
        assert forbidden not in lower, f"overclaiming phrase present: {forbidden}"


def validate_data_platform_artifacts() -> dict[str, int]:
    row_counts = validate_csv_artifacts()
    row_counts.update(validate_quality_artifacts())
    validate_text_framing()
    return row_counts


def main() -> None:
    row_counts = validate_data_platform_artifacts()
    summary = " ".join(
        f"{Path(name).name}={count}"
        for name, count in sorted(row_counts.items())
    )
    print(summary)


if __name__ == "__main__":
    main()
