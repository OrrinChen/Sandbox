from __future__ import annotations

import csv
import json
from pathlib import Path

from sandboxed_agent_eval_harness.evaluation.portfolio import main, run_portfolio_report


ROOT = Path(__file__).resolve().parents[1]
MODEL_MATRIX_FIXTURE = ROOT / "fixtures" / "model_outputs" / "model_matrix.json"


def test_portfolio_report_generates_public_artifacts(tmp_path):
    output_dir = tmp_path / "reports"
    evidence_dir = tmp_path / "artifacts" / "portfolio_model_matrix"

    result = run_portfolio_report(
        output_dir=output_dir,
        evidence_dir=evidence_dir,
        recorded_output_path=MODEL_MATRIX_FIXTURE,
    )

    report_md = output_dir / "portfolio_report.md"
    report_json = output_dir / "portfolio_report.json"
    model_matrix_csv = output_dir / "tables" / "model_matrix.csv"
    failure_taxonomy_csv = output_dir / "tables" / "failure_taxonomy.csv"
    domain_breakdown_csv = output_dir / "tables" / "domain_breakdown.csv"
    examples_dir = output_dir / "examples"

    assert result["portfolio_report_md"] == str(report_md)
    assert report_md.is_file()
    assert report_json.is_file()
    assert model_matrix_csv.is_file()
    assert failure_taxonomy_csv.is_file()
    assert domain_breakdown_csv.is_file()
    assert len(sorted(examples_dir.glob("replayable_failure_*.md"))) >= 3

    payload = json.loads(report_json.read_text())
    assert payload["problem"]["headline"] == "Final-answer-only eval misses silent tool-use failures"
    assert payload["evidence"]["recorded_offline"] is True
    assert payload["evidence"]["live_provider_benchmark"] is False
    assert payload["benchmark"]["task_count"] == 64
    assert payload["model_matrix"]["model_count"] == 5
    assert payload["model_matrix"]["distinct_failure_signature_count"] >= 4
    assert "Final-answer-only grading overestimated validated correctness by" in payload["key_result"]
    assert len(payload["case_studies"]) >= 3
    assert all(Path(case["trace_path"]).is_file() for case in payload["case_studies"])

    markdown = report_md.read_text()
    for heading in [
        "## Problem",
        "## System",
        "## Evidence",
        "## Benchmark",
        "## Failure Taxonomy",
        "## Reproducibility",
        "## Limitations",
    ]:
        assert heading in markdown
    assert "not a live-provider benchmark" in markdown
    assert "not a security product" in markdown

    model_rows = list(csv.DictReader(model_matrix_csv.open()))
    taxonomy_rows = list(csv.DictReader(failure_taxonomy_csv.open()))
    domain_rows = list(csv.DictReader(domain_breakdown_csv.open()))
    assert len(model_rows) == 5
    assert {"model", "validator_gap", "top_root_cause"}.issubset(model_rows[0])
    assert any(row["category"] == "FINAL_ANSWER_OVERCLAIM" for row in taxonomy_rows)
    assert {"domain", "run_count", "success_rate", "silent_failure_count"}.issubset(domain_rows[0])


def test_portfolio_case_studies_point_to_replayable_traces(tmp_path):
    run_portfolio_report(
        output_dir=tmp_path / "reports",
        evidence_dir=tmp_path / "artifacts" / "portfolio_model_matrix",
        recorded_output_path=MODEL_MATRIX_FIXTURE,
    )

    examples = sorted((tmp_path / "reports" / "examples").glob("replayable_failure_*.md"))

    assert len(examples) >= 3
    for example in examples[:3]:
        text = example.read_text()
        assert "Trace path:" in text
        assert "Replay command:" in text
        assert "Root causes:" in text
        trace_path_line = next(line for line in text.splitlines() if line.startswith("Trace path:"))
        trace_path = trace_path_line.split(":", 1)[1].strip()
        assert Path(trace_path).is_file()
        assert trace_path.endswith(".jsonl")


def test_portfolio_report_cli_and_makefile_smoke(tmp_path, capsys):
    exit_code = main(
        [
            "--output-dir",
            str(tmp_path / "reports"),
            "--evidence-dir",
            str(tmp_path / "artifacts" / "portfolio_model_matrix"),
            "--recorded-output",
            str(MODEL_MATRIX_FIXTURE),
        ]
    )
    output = capsys.readouterr().out
    makefile = (ROOT / "Makefile").read_text()

    assert exit_code == 0
    assert "portfolio_report=" in output
    assert "case_studies=" in output
    assert "models=5" in output
    assert (tmp_path / "reports" / "portfolio_report.md").is_file()
    assert "portfolio-report:" in makefile
    assert "sandboxed_agent_eval_harness.evaluation.portfolio" in makefile
