import json

import pytest

from sandboxed_agent_eval_harness.agents import (
    OracleToolSelectionAgent,
    default_agent_baselines,
)
from sandboxed_agent_eval_harness.evaluation.gates import (
    default_threshold_config_path,
    discover_trace_paths,
    evaluate_regression_gates,
    load_threshold_preset,
    main,
)
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor


def test_regression_gates_pass_for_oracle_summary_and_clean_replay(tmp_path):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "oracle",
    )
    run = next(item for item in summary.runs if item.task_id == "data-sales-region-summary")
    replay_result = TraceReplayExecutor().replay(run.trace_path, workspace=tmp_path / "replay")

    gate_report = evaluate_regression_gates(
        summary,
        thresholds={
            "min_task_success_rate": 1.0,
            "min_pass_at_k": 1.0,
            "max_failure_taxonomy": {"numeric_mismatch": 0},
            "max_replay_divergences": 0,
        },
        replay_results=[replay_result],
    )

    payload = gate_report.to_dict()

    assert gate_report.passed is True
    assert [result["name"] for result in payload["results"]] == [
        "task_success_rate",
        "pass_at_k",
        "failure_taxonomy.numeric_mismatch",
        "replay_divergences",
    ]
    assert payload["replay_divergence_summary"]["divergence_count"] == 0
    assert payload["replay_divergence_summary"]["replayed_traces"] == 1


def test_regression_gates_fail_on_metric_drop_and_failure_taxonomy(tmp_path):
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

    gate_report = evaluate_regression_gates(
        current,
        previous_summary=previous,
        thresholds={
            "min_task_success_rate": 0.9,
            "max_task_success_rate_drop": 0.1,
            "max_failure_taxonomy": {
                "numeric_mismatch": 0,
                "unsupported_citation": 0,
            },
        },
    )

    failures = [result for result in gate_report.to_dict()["results"] if result["passed"] is False]
    failure_names = {result["name"] for result in failures}

    assert gate_report.passed is False
    assert "task_success_rate" in failure_names
    assert "task_success_rate_drop" in failure_names
    assert "failure_taxonomy.numeric_mismatch" in failure_names
    assert "failure_taxonomy.unsupported_citation" in failure_names


def test_regression_gate_cli_returns_nonzero_for_failed_thresholds(tmp_path, capsys):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=default_agent_baselines(),
        trials_per_task=1,
        output_dir=tmp_path / "summary",
    )
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"min_task_success_rate": 0.99}) + "\n")

    exit_code = main(
        [
            "--summary",
            str(summary.output_dir / "summary.json"),
            "--thresholds",
            str(thresholds_path),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 1
    assert '"passed": false' in output
    assert '"name": "task_success_rate"' in output


def test_regression_gate_cli_returns_zero_for_passing_replay_thresholds(tmp_path, capsys):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "summary",
    )
    run = next(item for item in summary.runs if item.task_id == "data-sales-region-summary")
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(
        json.dumps(
            {
                "min_task_success_rate": 1.0,
                "min_pass_at_k": 1.0,
                "max_replay_divergences": 0,
            }
        )
        + "\n"
    )

    exit_code = main(
        [
            "--summary",
            str(summary.output_dir / "summary.json"),
            "--thresholds",
            str(thresholds_path),
            "--replay-trace",
            str(run.trace_path),
            "--replay-workspace",
            str(tmp_path / "replay"),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"passed": true' in output
    assert '"divergence_count": 0' in output


def test_default_threshold_config_declares_strict_smoke_preset():
    preset = load_threshold_preset("strict_smoke")

    assert default_threshold_config_path().name == "regression_gates.json"
    assert preset.preset_id == "strict_smoke"
    assert preset.thresholds["min_task_success_rate"] == 1.0
    assert preset.thresholds["min_pass_at_k"] == 1.0
    assert preset.thresholds["max_replay_divergences"] == 0
    assert preset.replay["discover_from_summary"] is True


def test_discover_trace_paths_uses_unique_summary_run_traces(tmp_path):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "summary",
    )
    first_trace = str(summary.runs[0].trace_path)
    summary_dict = summary.to_dict()
    summary_dict["runs"].append(dict(summary_dict["runs"][0]))

    trace_paths = discover_trace_paths(summary_dict)

    assert len(trace_paths) == len(summary.runs)
    assert first_trace in trace_paths
    assert all(path.endswith(".jsonl") for path in trace_paths)


def test_regression_gate_cli_loads_preset_and_discovers_summary_traces(tmp_path, capsys):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "summary",
    )

    exit_code = main(
        [
            "--summary",
            str(summary.output_dir / "summary.json"),
            "--threshold-preset",
            "strict_smoke",
            "--discover-traces",
            "--replay-workspace",
            str(tmp_path / "replay"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["passed"] is True
    assert payload["preset"]["id"] == "strict_smoke"
    assert payload["replay_divergence_summary"]["replayed_traces"] == len(summary.runs)
    assert payload["replay_divergence_summary"]["divergence_count"] == 0


def test_regression_gate_cli_rejects_threshold_file_and_preset_together(tmp_path):
    suite = default_task_suite()
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "summary",
    )
    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"min_task_success_rate": 1.0}) + "\n")

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--summary",
                str(summary.output_dir / "summary.json"),
                "--thresholds",
                str(thresholds_path),
                "--threshold-preset",
                "strict_smoke",
            ]
        )

    assert exc.value.code == 2
