import json
from collections import Counter

from sandboxed_agent_eval_harness.agents import default_agent_baselines
from sandboxed_agent_eval_harness.evaluation.runner import main, run_evaluation
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tracing import load_trace_events


def test_default_agent_baselines_cover_phase8_architectures():
    baselines = default_agent_baselines()

    assert [baseline.name for baseline in baselines] == [
        "single_shot_tool_agent",
        "react_style_agent",
        "planner_executor_agent",
        "oracle_tool_selection_agent",
    ]


def test_evaluation_runner_repeats_tasks_and_writes_trace_artifacts(tmp_path):
    suite = default_task_suite()
    oracle = [baseline for baseline in default_agent_baselines() if baseline.name == "oracle_tool_selection_agent"]

    summary = run_evaluation(
        suite=suite,
        baselines=oracle,
        trials_per_task=2,
        output_dir=tmp_path,
    )

    assert len(summary.runs) == len(suite.tasks) * 2
    assert Counter(run.task_id for run in summary.runs) == {task.task_id: 2 for task in suite.tasks}
    assert all(run.passed for run in summary.runs)
    assert summary.metrics["task_success_rate"] == 1.0
    assert summary.metrics["pass_at_k"]["k"] == 2
    assert summary.metrics["pass_at_k"]["value"] == 1.0

    first_run = summary.runs[0]
    events = load_trace_events(first_run.trace_path)

    assert first_run.trace_path.is_file()
    assert [event.event_type for event in events if event.event_type == "tool_call"]
    assert [event.event_type for event in events if event.event_type == "validator_result"]
    assert (tmp_path / "summary.json").is_file()


def test_evaluation_runner_reports_per_validator_metrics_and_failure_taxonomy(tmp_path):
    suite = default_task_suite()
    baselines = default_agent_baselines()

    summary = run_evaluation(
        suite=suite,
        baselines=baselines,
        trials_per_task=1,
        output_dir=tmp_path,
    )

    assert set(summary.baseline_metrics) == {baseline.name for baseline in baselines}
    assert summary.metrics["run_count"] == len(suite.tasks) * len(baselines)
    assert summary.metrics["task_success_rate"] < 1.0
    assert summary.metrics["failure_taxonomy"]
    assert "numeric_mismatch" in summary.metrics["failure_taxonomy"]
    assert "unsupported_citation" in summary.metrics["failure_taxonomy"]
    assert "tool_sequence" in summary.metrics["per_validator_metrics"]
    assert "numeric" in summary.metrics["per_validator_metrics"]
    assert summary.metrics["tool_selection_accuracy"] <= 1.0
    assert summary.metrics["argument_correctness"] <= 1.0
    assert summary.metrics["state_correctness"] <= 1.0
    assert summary.metrics["numeric_correctness"] <= 1.0
    assert summary.metrics["citation_correctness"] <= 1.0
    assert summary.metrics["average_turns"] > 0
    assert summary.metrics["timeout_rate"] == 0.0

    summary_json = json.loads((tmp_path / "summary.json").read_text())
    assert summary_json["metrics"]["failure_taxonomy"] == summary.metrics["failure_taxonomy"]
    assert summary_json["runs"][0]["trace_path"].endswith(".jsonl")


def test_evaluation_cli_smoke_writes_summary(tmp_path, capsys):
    exit_code = main(
        [
            "--suite",
            "smoke",
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
    assert "runs=6" in output
    assert "task_success_rate=1.000" in output
    assert (tmp_path / "summary.json").is_file()
