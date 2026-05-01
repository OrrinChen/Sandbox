import json
from pathlib import Path

from sandboxed_agent_eval_harness.evaluation.model_study import main, run_silent_failure_study


ROOT = Path(__file__).resolve().parents[1]
RECORDED_OUTPUT = ROOT / "fixtures" / "model_outputs" / "silent_failure_study.json"


def test_silent_failure_study_writes_summary_report_and_model_comparison(tmp_path):
    result = run_silent_failure_study(
        recorded_output_path=RECORDED_OUTPUT,
        output_dir=tmp_path,
    )

    study_path = tmp_path / "silent_failure_study.json"
    summary_path = tmp_path / "summary.json"
    report_path = tmp_path / "report" / "report.json"

    assert study_path.is_file()
    assert summary_path.is_file()
    assert report_path.is_file()
    assert result["study_path"] == str(study_path)

    study = json.loads(study_path.read_text())
    comparison = study["model_comparison"][0]

    assert comparison["model"] == "recorded-gpt-style-v1"
    assert comparison["final_answer_pass_rate"] == 1.0
    assert comparison["validator_pass_rate"] < comparison["final_answer_pass_rate"]
    assert comparison["silent_failure_count"] > 0
    assert comparison["overstatement_rate"] > 0


def test_silent_failure_study_cli_smoke(tmp_path, capsys):
    exit_code = main(
        [
            "--recorded-output",
            str(RECORDED_OUTPUT),
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "models=1" in output
    assert "final_answer_pass_rate=1.000" in output
    assert "silent_failures=" in output
