import csv
import json
from pathlib import Path

from sandboxed_agent_eval_harness.evaluation.model_matrix import main, run_recorded_model_matrix
from sandboxed_agent_eval_harness.models import load_recorded_model_adapters
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite


ROOT = Path(__file__).resolve().parents[1]
MODEL_MATRIX_FIXTURE = ROOT / "fixtures" / "model_outputs" / "model_matrix.json"


def test_model_matrix_fixture_has_distinct_recorded_profiles():
    suite = benchmark_task_suite()
    adapters = load_recorded_model_adapters(MODEL_MATRIX_FIXTURE)
    adapter_names = {adapter.name for adapter in adapters}

    assert {
        "recorded_good_model",
        "recorded_overconfident_model",
        "recorded_tool_sloppy_model",
        "recorded_citation_sloppy_model",
        "recorded_state_sloppy_model",
    }.issubset(adapter_names)
    assert len(adapters) >= 4
    for adapter in adapters:
        assert adapter.task_ids() == sorted(suite.task_ids())


def test_recorded_model_matrix_writes_summary_report_and_csv(tmp_path):
    result = run_recorded_model_matrix(
        recorded_output_path=MODEL_MATRIX_FIXTURE,
        output_dir=tmp_path,
        suite_name="benchmark",
    )

    matrix_path = tmp_path / "model_matrix_summary.json"
    markdown_path = tmp_path / "model_comparison_report.md"
    csv_path = tmp_path / "silent_failure_by_model.csv"

    assert result["matrix_path"] == str(matrix_path)
    assert matrix_path.is_file()
    assert markdown_path.is_file()
    assert csv_path.is_file()
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "report" / "report.json").is_file()

    matrix = json.loads(matrix_path.read_text())
    models = matrix["models"]

    assert matrix["study_id"] == "phase19-recorded-model-matrix"
    assert matrix["suite"] == "benchmark"
    assert matrix["model_count"] >= 4
    assert matrix["run_count"] == 64 * matrix["model_count"]
    assert matrix["distinct_failure_signature_count"] >= 4
    assert "Final-answer-only grading overestimated validated correctness by" in matrix["key_finding"]
    assert models == sorted(
        models,
        key=lambda row: (-row["validator_gap"], -row["silent_failure_count"], row["model"]),
    )
    assert all(row["failure_signature"] for row in models)
    assert any(row["top_root_cause"] == "CITATION_UNSUPPORTED" for row in models)
    assert any(row["top_root_cause"] == "STATE_MUTATION_ERROR" for row in models)

    csv_rows = list(csv.DictReader(csv_path.open()))
    assert len(csv_rows) == matrix["model_count"]
    assert {
        "model",
        "final_answer_pass_rate",
        "validator_pass_rate",
        "silent_failure_count",
        "validator_gap",
        "top_root_cause",
    }.issubset(csv_rows[0])

    markdown = markdown_path.read_text()
    assert "# Recorded Model Matrix" in markdown
    assert "## Failure Signatures" in markdown
    assert "recorded-good-fixture-v1" in markdown
    assert "recorded-citation-sloppy-fixture-v1" in markdown


def test_recorded_model_matrix_cli_smoke(tmp_path, capsys):
    exit_code = main(
        [
            "--recorded-output",
            str(MODEL_MATRIX_FIXTURE),
            "--output-dir",
            str(tmp_path),
            "--suite",
            "benchmark",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "models=" in output
    assert "distinct_signatures=" in output
    assert "max_validator_gap=" in output
    assert (tmp_path / "model_matrix_summary.json").is_file()
