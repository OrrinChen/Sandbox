import json

import pytest

from sandboxed_agent_eval_harness.schemas import (
    RunResult,
    SchemaValidationError,
    TraceEvent,
    ValidatorResult,
)


def test_trace_event_serializes_to_jsonl_compatible_record():
    event = TraceEvent(
        event_id="evt-001",
        event_type="tool_call",
        sequence=3,
        payload={
            "tool_name": "financial_statement.lookup",
            "arguments": {"ticker": "AAPL", "fiscal_year": 2023},
        },
        metadata={"task_version": "finance-v1"},
    )

    line = event.to_json_line()
    decoded = json.loads(line)
    restored = TraceEvent.from_json_line(line)

    assert decoded["event_type"] == "tool_call"
    assert decoded["sequence"] == 3
    assert restored == event


def test_trace_event_rejects_negative_sequence():
    with pytest.raises(SchemaValidationError, match="sequence"):
        TraceEvent(
            event_id="evt-bad",
            event_type="tool_result",
            sequence=-1,
            payload={},
        )


def test_validator_result_round_trips_pass_and_failure_records():
    passed = ValidatorResult(
        validator_name="numeric",
        passed=True,
        message="Revenue matched expected value.",
        details={"expected": 383285, "actual": 383285},
    )
    failed = ValidatorResult(
        validator_name="citation",
        passed=False,
        failure_type="unsupported_citation",
        message="Final answer cited a source not present in trace.",
        details={"citation": "made-up-source"},
    )

    assert ValidatorResult.from_dict(passed.to_dict()) == passed
    assert ValidatorResult.from_dict(failed.to_dict()) == failed
    assert failed.to_dict()["failure_type"] == "unsupported_citation"


def test_validator_result_requires_failure_type_when_failed():
    with pytest.raises(SchemaValidationError, match="failure_type"):
        ValidatorResult(
            validator_name="citation",
            passed=False,
            message="Missing citation.",
        )


def test_run_result_serializes_nested_trace_and_validator_results():
    event = TraceEvent(
        event_id="evt-001",
        event_type="tool_call",
        sequence=1,
        payload={"tool_name": "csv.group_metrics"},
    )
    validator = ValidatorResult(
        validator_name="schema",
        passed=True,
        message="Output schema matched.",
    )
    run = RunResult(
        run_id="run-001",
        task_id="data-group-metrics",
        agent_id="single-shot-tool-agent",
        passed=True,
        trace_events=[event],
        validator_results=[validator],
        metrics={"latency_seconds": 1.2, "tool_calls": 1},
        failure_labels=[],
    )

    serialized = run.to_dict()
    restored = RunResult.from_dict(serialized)

    assert restored == run
    assert serialized["trace_events"][0]["event_type"] == "tool_call"
    assert serialized["validator_results"][0]["validator_name"] == "schema"


def test_run_result_rejects_mismatched_pass_status():
    failed_validator = ValidatorResult(
        validator_name="numeric",
        passed=False,
        failure_type="numeric_mismatch",
        message="Actual value differed from expected.",
    )

    with pytest.raises(SchemaValidationError, match="passed"):
        RunResult(
            run_id="run-bad",
            task_id="finance-revenue-yoy",
            agent_id="single-shot-tool-agent",
            passed=True,
            trace_events=[],
            validator_results=[failed_validator],
            metrics={},
            failure_labels=["numeric_mismatch"],
        )
