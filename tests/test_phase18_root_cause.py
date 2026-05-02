import json

import pytest

from sandboxed_agent_eval_harness.agents import default_agent_baselines
from sandboxed_agent_eval_harness.evaluation.model_study import run_silent_failure_study
from sandboxed_agent_eval_harness.evaluation.report import (
    ROOT_CAUSE_CATEGORIES,
    build_evaluation_report,
    root_cause_category_for_validator_result,
    write_evaluation_report,
)
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tasks import default_task_suite


def test_root_cause_mapping_covers_phase18_categories():
    examples = [
        ({"validator_name": "tool_sequence", "failure_type": "tool_sequence_mismatch"}, "TOOL_SELECTION_ERROR"),
        ({"validator_name": "argument", "failure_type": "invalid_tool_arguments"}, "TOOL_ARGUMENT_ERROR"),
        ({"validator_name": "unit_test", "failure_type": "unit_tests_missing"}, "TOOL_RESULT_MISUSE"),
        ({"validator_name": "state", "failure_type": "state_mismatch"}, "STATE_MUTATION_ERROR"),
        ({"validator_name": "numeric", "failure_type": "numeric_mismatch"}, "NUMERIC_MISMATCH"),
        ({"validator_name": "citation", "failure_type": "unsupported_citation"}, "CITATION_UNSUPPORTED"),
        ({"validator_name": "constraint", "failure_type": "constraint_violation"}, "CONSTRAINT_VIOLATION"),
        ({"validator_name": "replay", "failure_type": "tool_result_mismatch"}, "TRACE_REPLAY_DIVERGENCE"),
        (
            {
                "validator_name": "cost_latency",
                "failure_type": "cost_latency_violation",
                "details": {"violations": ["timed_out"]},
            },
            "TIMEOUT",
        ),
        (
            {
                "validator_name": "cost_latency",
                "failure_type": "cost_latency_violation",
                "details": {"violations": ["cost"]},
            },
            "COST_LIMIT_EXCEEDED",
        ),
        ({"validator_name": "final_answer", "failure_type": "final_answer_overclaim"}, "FINAL_ANSWER_OVERCLAIM"),
    ]

    mapped_categories = {root_cause_category_for_validator_result(payload) for payload, _ in examples}

    assert [root_cause_category_for_validator_result(payload) for payload, _ in examples] == [
        expected for _, expected in examples
    ]
    assert mapped_categories == set(ROOT_CAUSE_CATEGORIES)


def test_report_exposes_root_cause_breakdowns_and_executive_summary(tmp_path):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=default_agent_baselines(),
        trials_per_task=1,
        output_dir=tmp_path / "current",
    )

    report = build_evaluation_report(summary, suite=suite)
    report_dict = report.to_dict()
    final_metrics = report_dict["final_answer_vs_validator"]
    root_cause = report_dict["root_cause_summary"]

    assert "Final-answer-only grading overestimated validated correctness by" in report_dict["executive_summary"]
    assert final_metrics["silent_failure_rate"] > 0
    assert final_metrics["answer_overclaim_rate"] == final_metrics["silent_failure_rate"]
    assert final_metrics["validator_gap"] == pytest.approx(
        final_metrics["final_answer_pass_rate"] - final_metrics["validator_pass_rate"]
    )
    assert root_cause["validator_gap"] == final_metrics["validator_gap"]
    assert root_cause["categories"]["FINAL_ANSWER_OVERCLAIM"]["count"] == final_metrics["silent_failure_count"]
    assert root_cause["categories"]["CITATION_UNSUPPORTED"]["count"] > 0
    assert root_cause["failure_by_domain"]["finance"]["CITATION_UNSUPPORTED"] > 0
    assert root_cause["failure_by_model"]["deterministic-fixture-agent"]["FINAL_ANSWER_OVERCLAIM"] > 0
    assert root_cause["failure_by_validator"]["citation"]["CITATION_UNSUPPORTED"] > 0
    assert root_cause["failure_by_tool"]
    assert root_cause["top_replayable_failure_traces"]
    assert root_cause["top_replayable_failure_traces"][0]["trace_path"].endswith(".jsonl")


def test_report_markdown_has_executive_summary(tmp_path):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=default_agent_baselines(),
        trials_per_task=1,
        output_dir=tmp_path / "current",
    )
    report = build_evaluation_report(summary, suite=suite)

    paths = write_evaluation_report(report, tmp_path / "report")
    markdown = (tmp_path / "report" / "report.md").read_text()
    report_json = json.loads((tmp_path / "report" / "report.json").read_text())

    assert paths["markdown_path"].endswith("report.md")
    assert "## Executive Summary" in markdown
    assert "Final-answer-only grading overestimated validated correctness by" in markdown
    assert "root_cause_summary" in report_json
    assert report_json["root_cause_summary"]["categories"]


def test_silent_failure_study_contains_root_cause_breakdown(tmp_path):
    result = run_silent_failure_study(
        recorded_output_path="fixtures/model_outputs/silent_failure_study.json",
        output_dir=tmp_path,
        suite_name="benchmark",
    )

    study = json.loads((tmp_path / "silent_failure_study.json").read_text())
    root_cause = study["root_cause_breakdown"]

    assert result["root_cause_breakdown"]["silent_failure_count"] == 32
    assert root_cause["silent_failure_count"] == 32
    assert root_cause["validator_gap"] == pytest.approx(0.5)
    assert root_cause["failure_by_domain"]
    assert root_cause["failure_by_tool"]
    assert root_cause["failure_by_model"]["recorded-gpt-style-v1"]["FINAL_ANSWER_OVERCLAIM"] == 32
    assert root_cause["failure_by_validator"]
    assert root_cause["top_replayable_failure_traces"]
