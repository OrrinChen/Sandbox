import json

import pytest

from sandboxed_agent_eval_harness.agents import (
    OracleToolSelectionAgent,
    default_agent_baselines,
)
from sandboxed_agent_eval_harness.evaluation.report import (
    build_evaluation_report,
    main,
)
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tasks import default_task_suite


def test_report_summarizes_domains_failures_pass_at_k_and_worst_traces(tmp_path):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=default_agent_baselines(),
        trials_per_task=2,
        output_dir=tmp_path / "current",
    )

    report = build_evaluation_report(summary, suite=suite)
    report_dict = report.to_dict()

    assert report_dict["domain_success"]["finance"]["run_count"] == 24
    assert report_dict["domain_success"]["finance"]["success_rate"] == pytest.approx(0.5)
    assert report_dict["domain_success"]["data_analysis"]["run_count"] == 24
    assert report_dict["domain_success"]["data_analysis"]["success_rate"] == pytest.approx(0.75)
    assert report_dict["final_answer_vs_validator"]["final_answer_pass_rate"] == 1.0
    assert report_dict["final_answer_vs_validator"]["validator_pass_rate"] == summary.metrics["task_success_rate"]
    assert report_dict["final_answer_vs_validator"]["silent_failure_count"] > 0
    assert report_dict["failure_type_distribution"]["numeric_mismatch"] > 0
    assert report_dict["failure_type_distribution"]["unsupported_citation"] > 0
    assert report_dict["pass_at_k_curve"] == [
        {"k": 1, "value": pytest.approx(summary.metrics["pass_at_k"]["value"])},
        {"k": 2, "value": pytest.approx(summary.metrics["pass_at_k"]["value"])},
    ]
    assert report_dict["cost_latency_summary"]["average_latency_seconds"] > 0
    assert report_dict["cost_latency_summary"]["average_cost"] == 0.0
    assert report_dict["failure_insights"]

    worst_trace = report_dict["worst_traces"][0]
    assert worst_trace["trace_path"].endswith(".jsonl")
    assert worst_trace["replay_ready"] is True
    assert worst_trace["failure_types"]

    version_matrix = report_dict["version_matrix"]
    assert version_matrix["model"] == ["deterministic-fixture-agent"]
    assert version_matrix["task_version"] == ["tasks-v1"]
    assert version_matrix["tool_version"] == ["tools-v1"]


def test_report_compares_against_previous_run_artifact(tmp_path):
    suite = default_task_suite()
    previous = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=2,
        output_dir=tmp_path / "previous",
    )
    current = run_evaluation(
        suite=suite,
        baselines=default_agent_baselines(),
        trials_per_task=2,
        output_dir=tmp_path / "current",
    )

    report = build_evaluation_report(current, suite=suite, previous_summary=previous.to_dict())
    comparison = report.to_dict()["regression_comparison"]

    assert comparison["task_success_rate"]["previous"] == 1.0
    assert comparison["task_success_rate"]["current"] == current.metrics["task_success_rate"]
    assert comparison["task_success_rate"]["delta"] < 0
    assert comparison["current_versions"]["task_version"] == ["tasks-v1"]
    assert comparison["previous_versions"]["task_version"] == ["tasks-v1"]
    assert comparison["baseline_task_success_rate"]["oracle_tool_selection_agent"]["delta"] == 0.0
    assert comparison["baseline_task_success_rate"]["single_shot_tool_agent"]["previous"] is None


def test_report_cli_writes_json_and_markdown(tmp_path, capsys):
    suite = default_task_suite()
    previous = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "previous",
    )
    current = run_evaluation(
        suite=suite,
        baselines=default_agent_baselines(),
        trials_per_task=1,
        output_dir=tmp_path / "current",
    )
    output_dir = tmp_path / "report"

    exit_code = main(
        [
            "--summary",
            str(current.output_dir / "summary.json"),
            "--previous-summary",
            str(previous.output_dir / "summary.json"),
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out
    report_json = json.loads((output_dir / "report.json").read_text())
    report_markdown = (output_dir / "report.md").read_text()

    assert exit_code == 0
    assert "report=" in output
    assert report_json["regression_comparison"]["task_success_rate"]["delta"] < 0
    assert report_json["worst_traces"]
    assert "# Sandboxed Agent Evaluation Report" in report_markdown
    assert "## Worst Traces" in report_markdown
