import json

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor, load_trace_events


def test_trace_replay_executor_reexecutes_tool_calls_and_matches_state(tmp_path):
    summary = run_evaluation(
        suite=default_task_suite(),
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "run",
    )
    run = next(item for item in summary.runs if item.task_id == "data-sales-region-summary")

    result = TraceReplayExecutor().replay(run.trace_path, workspace=tmp_path / "replay-workspace")

    assert result.passed is True
    assert result.task_id == "data-sales-region-summary"
    assert result.replayed_tool_calls == 2
    assert result.state_diff_matches is True
    assert result.recorded_state_diff == {"added": ["summary_by_region.csv"], "modified": [], "deleted": []}
    assert result.replayed_state_diff == result.recorded_state_diff
    assert [comparison["matches"] for comparison in result.tool_result_comparisons] == [True, True]
    assert result.divergences == []
    assert (result.workspace_path / "summary_by_region.csv").read_text() == (
        "region,revenue\nwest,5100\neast,3300\ncentral,2350\n"
    )


def test_trace_replay_executor_reexecutes_coding_trace(tmp_path):
    summary = run_evaluation(
        suite=default_task_suite(),
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "run",
    )
    run = next(item for item in summary.runs if item.task_id == "coding-discount-total-fix")

    result = TraceReplayExecutor().replay(run.trace_path, workspace=tmp_path / "replay-coding")

    assert result.passed is True
    assert result.replayed_tool_calls == 2
    assert result.state_diff_matches is True
    assert result.recorded_state_diff == {"added": [], "modified": ["fixtures/code/discount.py"], "deleted": []}
    assert [comparison["matches"] for comparison in result.tool_result_comparisons] == [True, True]


def test_trace_replay_executor_reports_tool_result_divergence(tmp_path):
    summary = run_evaluation(
        suite=default_task_suite(),
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "run",
    )
    run = next(item for item in summary.runs if item.task_id == "data-sales-region-summary")
    tampered_trace = tmp_path / "tampered.jsonl"
    _write_tampered_csv_read_rows(run.trace_path, tampered_trace, rows=999)

    result = TraceReplayExecutor().replay(tampered_trace, workspace=tmp_path / "replay-workspace")
    payload = result.to_dict()

    assert result.passed is False
    assert result.tool_result_comparisons[0]["matches"] is False
    assert result.divergences[0]["type"] == "tool_result_mismatch"
    assert result.divergences[0]["recorded"]["rows"] == 999
    assert result.divergences[0]["replayed"]["rows"] == 6
    assert payload["passed"] is False
    assert payload["workspace_path"].endswith("replay-workspace")


def test_trace_replay_executor_reports_state_diff_divergence(tmp_path):
    summary = run_evaluation(
        suite=default_task_suite(),
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path / "run",
    )
    run = next(item for item in summary.runs if item.task_id == "data-sales-region-summary")
    tampered_trace = tmp_path / "tampered-state.jsonl"
    _write_tampered_state_diff(run.trace_path, tampered_trace)

    result = TraceReplayExecutor().replay(tampered_trace, workspace=tmp_path / "replay-workspace")

    assert result.passed is False
    assert result.state_diff_matches is False
    assert result.divergences[-1]["type"] == "state_diff_mismatch"
    assert result.divergences[-1]["recorded"] == {"added": [], "modified": [], "deleted": []}
    assert result.divergences[-1]["replayed"] == {"added": ["summary_by_region.csv"], "modified": [], "deleted": []}


def _write_tampered_csv_read_rows(source_trace, target_trace, rows):
    events = [event.to_dict() for event in load_trace_events(source_trace)]
    for event in events:
        if event["event_type"] == "tool_result" and event["payload"]["tool_name"] == "csv.read":
            event["payload"]["result"]["rows"] = rows
            break
    _write_jsonl(target_trace, events)


def _write_tampered_state_diff(source_trace, target_trace):
    events = [event.to_dict() for event in load_trace_events(source_trace)]
    for event in events:
        if event["event_type"] == "state_diff":
            event["payload"] = {"added": [], "modified": [], "deleted": []}
            break
    _write_jsonl(target_trace, events)


def _write_jsonl(path, events):
    path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n")
