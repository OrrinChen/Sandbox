import json

import pytest

from sandboxed_agent_eval_harness.schemas import TraceEvent, ValidatorResult
from sandboxed_agent_eval_harness.sandbox import StateDiff
from sandboxed_agent_eval_harness.tracing import (
    TraceLogger,
    TraceReplay,
    TraceReplayError,
    load_trace_events,
)


def make_logger(path):
    return TraceLogger(
        path,
        run_metadata={
            "run_id": "run-001",
            "task_id": "finance-revenue-yoy",
            "agent_id": "single-shot-tool-agent",
            "model": "fixture-model",
            "prompt_version": "prompt-v1",
            "tool_version": "tools-v1",
            "task_version": "finance-v1",
            "fixture_version": "fixtures-v1",
        },
    )


def test_trace_logger_persists_ordered_jsonl_events(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    logger = make_logger(trace_path)

    logger.log_user_message("Compare FY2023 revenue.")
    logger.log_agent_message("I will inspect the fixture.")
    logger.log_tool_call("financial_statement.lookup", {"ticker": "AAPL", "fiscal_year": 2023})
    logger.log_tool_result("financial_statement.lookup", {"values": {"revenue": 383285}})

    lines = trace_path.read_text().splitlines()
    events = load_trace_events(trace_path)

    assert len(lines) == 4
    assert [event.sequence for event in events] == [0, 1, 2, 3]
    assert [event.event_type for event in events] == [
        "user_message",
        "agent_message",
        "tool_call",
        "tool_result",
    ]
    assert events[0].metadata["run_id"] == "run-001"
    assert events[0].metadata["model"] == "fixture-model"
    assert json.loads(lines[2])["payload"]["tool_name"] == "financial_statement.lookup"


def test_trace_logger_records_state_diff_validator_timeout_and_error_events(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    logger = make_logger(trace_path)
    diff = StateDiff(added=["output.csv"], modified=["input.csv"], deleted=[])
    validator = ValidatorResult(
        validator_name="numeric",
        passed=False,
        failure_type="numeric_mismatch",
        message="Revenue did not match expected value.",
        details={"expected": 383285, "actual": 999},
    )

    logger.log_state_diff(diff)
    logger.log_validator_result(validator)
    logger.log_timeout("python_subprocess", timeout_seconds=0.1)
    logger.log_error("SandboxPathError", "path is outside workspace")

    events = load_trace_events(trace_path)

    assert [event.event_type for event in events] == [
        "state_diff",
        "validator_result",
        "timeout_event",
        "error_event",
    ]
    assert events[0].payload == diff.to_dict()
    assert events[1].payload["failure_type"] == "numeric_mismatch"
    assert events[2].payload == {"operation": "python_subprocess", "timeout_seconds": 0.1}
    assert events[3].payload["error_type"] == "SandboxPathError"


def test_trace_replay_preserves_event_order_and_metadata(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    logger = make_logger(trace_path)
    logger.log_user_message("Run task.")
    logger.log_tool_call("csv.read", {"path": "fixtures/data/sales.csv"})
    logger.log_tool_result("csv.read", {"path": "fixtures/data/sales.csv", "rows": 2})

    replay = TraceReplay.from_jsonl(
        trace_path,
        fixture_state={"fixtures/data/sales.csv": "region,revenue\nwest,10\n"},
    )

    assert [event.event_type for event in replay.events] == ["user_message", "tool_call", "tool_result"]
    assert replay.metadata["task_version"] == "finance-v1"
    assert replay.fixture_state == {"fixtures/data/sales.csv": "region,revenue\nwest,10\n"}
    assert replay.events_by_type("tool_call")[0].payload["tool_name"] == "csv.read"
    assert replay.events_by_type("missing") == []


def test_trace_replay_rejects_non_contiguous_sequences(tmp_path):
    trace_path = tmp_path / "bad.jsonl"
    events = [
        TraceEvent(event_id="evt-000", event_type="user_message", sequence=0, payload={"content": "hi"}),
        TraceEvent(event_id="evt-002", event_type="agent_message", sequence=2, payload={"content": "gap"}),
    ]
    trace_path.write_text("\n".join(event.to_json_line() for event in events) + "\n")

    with pytest.raises(TraceReplayError, match="contiguous"):
        TraceReplay.from_jsonl(trace_path)


def test_load_trace_events_rejects_malformed_jsonl(tmp_path):
    trace_path = tmp_path / "bad.jsonl"
    trace_path.write_text('{"event_id": "evt-1", "event_type": "user_message"}\n')

    with pytest.raises(TraceReplayError, match="TraceEvent"):
        load_trace_events(trace_path)
