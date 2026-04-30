from pathlib import Path

from sandboxed_agent_eval_harness.sandbox import StateDiff
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import default_tool_registry
from sandboxed_agent_eval_harness.validators import (
    default_validator_names,
    validate_citations,
    validate_numeric,
    validate_schema,
    validate_state,
    validate_tool_arguments,
    validate_tool_sequence,
)


ROOT = Path(__file__).resolve().parents[1]


def make_task_payload():
    return {
        "task_id": "finance-revenue-yoy",
        "domain": "finance",
        "instruction": "Compare FY2023 revenue.",
        "available_tools": ["financial_statement.lookup"],
        "initial_state": {},
        "hidden_expected_state": {"revenue": 383285},
        "visible_files": [],
        "success_criteria": ["Use fixture-backed revenue."],
        "validator_list": ["schema", "numeric"],
        "max_turns": 4,
        "max_cost": 0.0,
        "timeout_seconds": 30,
    }


def tool_call(sequence, tool_name, arguments):
    return TraceEvent(
        event_id=f"evt-{sequence:03d}",
        event_type="tool_call",
        sequence=sequence,
        payload={"tool_name": tool_name, "arguments": arguments},
    )


def test_schema_validator_returns_pass_or_deterministic_failure():
    valid = validate_schema("task", make_task_payload())
    invalid_payload = dict(make_task_payload(), max_turns=0)

    invalid = validate_schema("task", invalid_payload)

    assert valid.passed is True
    assert valid.validator_name == "schema"
    assert invalid.passed is False
    assert invalid.failure_type == "schema_mismatch"
    assert invalid.details["schema_name"] == "task"
    assert "max_turns" in invalid.message


def test_tool_sequence_validator_catches_wrong_tool_use():
    events = [
        tool_call(0, "financial_statement.lookup", {"ticker": "AAPL"}),
        tool_call(1, "transcript.search", {"ticker": "AAPL"}),
    ]

    passed = validate_tool_sequence(
        events,
        expected_sequence=["financial_statement.lookup", "transcript.search"],
    )
    failed = validate_tool_sequence(
        events,
        expected_sequence=["financial_statement.lookup", "csv.read"],
    )

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "tool_sequence_mismatch"
    assert failed.details["actual_sequence"] == ["financial_statement.lookup", "transcript.search"]


def test_argument_validator_uses_tool_registry_schemas():
    registry = default_tool_registry()
    valid_events = [
        tool_call(
            0,
            "financial_statement.lookup",
            {"ticker": "AAPL", "fiscal_year": 2023, "statement": "income"},
        )
    ]
    invalid_events = [
        tool_call(
            0,
            "financial_statement.lookup",
            {"ticker": "AAPL", "fiscal_year": "2023", "statement": "income"},
        )
    ]

    passed = validate_tool_arguments(valid_events, registry)
    failed = validate_tool_arguments(invalid_events, registry)

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "invalid_tool_arguments"
    assert failed.details["tool_name"] == "financial_statement.lookup"
    assert failed.details["sequence"] == 0


def test_state_validator_detects_unexpected_mutations():
    expected = StateDiff(added=["summary.csv"], modified=[], deleted=[])
    actual = StateDiff(added=["summary.csv"], modified=[], deleted=[])
    corrupted = StateDiff(added=["summary.csv"], modified=["input.csv"], deleted=[])

    passed = validate_state(actual, expected)
    failed = validate_state(corrupted, expected)

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "state_mismatch"
    assert failed.details["actual"]["modified"] == ["input.csv"]


def test_numeric_validator_detects_plausible_wrong_numbers():
    passed = validate_numeric("revenue", actual=383285, expected=383285)
    failed = validate_numeric("revenue", actual=383000, expected=383285, tolerance=10)

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "numeric_mismatch"
    assert failed.details == {
        "metric": "revenue",
        "actual": 383000,
        "expected": 383285,
        "tolerance": 10,
    }


def test_citation_validator_detects_unsupported_citations():
    passed = validate_citations(
        "Revenue matched the filing [aapl-2023-10k].",
        supported_citations=["aapl-2023-10k"],
    )
    failed = validate_citations(
        "Revenue matched an unsupported source [made-up-source].",
        supported_citations=["aapl-2023-10k"],
    )

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "unsupported_citation"
    assert failed.details["unsupported_citations"] == ["made-up-source"]


def test_validators_config_declares_default_validator_names():
    validators_config = (ROOT / "configs" / "validators.yaml").read_text()

    assert default_validator_names() == [
        "schema",
        "tool_sequence",
        "argument",
        "state",
        "numeric",
        "citation",
    ]
    for validator_name in default_validator_names():
        assert validator_name in validators_config
