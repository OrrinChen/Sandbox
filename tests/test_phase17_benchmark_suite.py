import json
from collections import Counter
from pathlib import Path

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.evaluation.model_study import run_silent_failure_study
from sandboxed_agent_eval_harness.evaluation.runner import main, run_evaluation
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite, task_suite_by_name
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor


ROOT = Path(__file__).resolve().parents[1]
RECORDED_OUTPUT = ROOT / "fixtures" / "model_outputs" / "silent_failure_study.json"


def test_benchmark_suite_loads_structured_64_task_manifest():
    suite = benchmark_task_suite()
    domain_counts = Counter(task.domain for task in suite.tasks)

    assert suite.suite_id == "benchmark-fixture-suite"
    assert suite.version == "tasks-benchmark-v1"
    assert len(suite.tasks) == 64
    assert domain_counts == {
        "finance": 12,
        "data_analysis": 12,
        "coding": 12,
        "optimization": 12,
        "file_workflow": 8,
        "citation": 8,
    }
    assert task_suite_by_name("smoke").suite_id == "initial-fixture-suite"
    assert task_suite_by_name("benchmark").suite_id == "benchmark-fixture-suite"

    for task in suite.tasks:
        metadata = suite.metadata_for(task.task_id)
        assert metadata["final_answer_only_risk"] is True
        assert metadata["known_failure_traps"]
        assert "failure_taxonomy_traps" in metadata
        assert metadata["failure_taxonomy_traps"]
        assert all((ROOT / path).is_file() for path in metadata["fixture_paths"])
        assert all((ROOT / path).is_file() for path in task.visible_files)


def test_benchmark_oracle_passes_and_replays_without_divergence(tmp_path):
    suite = benchmark_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "benchmark-run",
    )

    assert summary.metrics["run_count"] == 64
    assert summary.metrics["task_success_rate"] == 1.0
    assert summary.metrics["pass_at_k"]["value"] == 1.0

    replay_executor = TraceReplayExecutor(suite=suite)
    replay_results = [
        replay_executor.replay(run.trace_path, workspace=tmp_path / "replay" / run.task_id)
        for run in summary.runs
    ]

    assert all(result.passed for result in replay_results)
    assert sum(len(result.divergences) for result in replay_results) == 0


def test_evaluation_cli_accepts_benchmark_suite(tmp_path, capsys):
    exit_code = main(
        [
            "--suite",
            "benchmark",
            "--baseline",
            "oracle_tool_selection_agent",
            "--trials",
            "1",
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runs=64" in output
    assert "task_success_rate=1.000" in output
    assert (tmp_path / "summary.json").is_file()


def test_recorded_model_study_can_run_on_benchmark_suite(tmp_path):
    result = run_silent_failure_study(
        recorded_output_path=RECORDED_OUTPUT,
        output_dir=tmp_path,
        suite_name="benchmark",
    )

    study = json.loads((tmp_path / "silent_failure_study.json").read_text())
    comparison = study["model_comparison"][0]

    assert result["model_comparison"][0]["run_count"] == 64
    assert comparison["final_answer_pass_rate"] == 1.0
    assert comparison["validator_pass_rate"] < comparison["final_answer_pass_rate"]
    assert comparison["silent_failure_count"] >= 16
