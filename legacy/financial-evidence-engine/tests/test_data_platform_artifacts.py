from scripts.smoke_data_platform_artifacts import (
    CSV_ARTIFACTS,
    FORBIDDEN_PUBLIC_CLAIMS,
    TEXT_ARTIFACTS,
    validate_csv_artifacts,
    validate_quality_artifacts,
    validate_text_framing,
)


def test_data_platform_csv_artifacts_are_present_non_empty_and_schema_checked():
    row_counts = validate_csv_artifacts()

    for spec in CSV_ARTIFACTS:
        assert row_counts[str(spec.path)] >= 1


def test_data_platform_quality_artifacts_have_check_rows():
    row_counts = validate_quality_artifacts()

    assert row_counts["citation_quality_checks"] >= 1
    assert row_counts["normalization_quality_checks"] >= 1


def test_data_platform_public_framing_mentions_view_without_overclaiming():
    validate_text_framing()

    combined = "\n".join(path.read_text(encoding="utf-8") for path in TEXT_ARTIFACTS)
    assert "Data Platform View" in combined
    for forbidden in FORBIDDEN_PUBLIC_CLAIMS:
        assert forbidden not in combined.lower()
