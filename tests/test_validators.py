from pathlib import Path

from sandboxed_agent_eval_harness.sandbox import StateDiff
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import default_tool_registry
from sandboxed_agent_eval_harness.validators import (
    default_validator_names,
    validate_artifact_grounding,
    validate_citations,
    validate_constraints,
    validate_cost_latency,
    validate_cost_inclusion,
    validate_lookahead,
    validate_numeric,
    validate_policy,
    validate_pnl_consistency,
    validate_risk_limits,
    validate_schema,
    validate_state,
    validate_tool_arguments,
    validate_tool_sequence,
    validate_unit_tests,
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


def test_constraint_validator_catches_infeasible_metrics():
    constraints = [
        {"metric": "order_quantity", "operator": ">=", "value": 0},
        {"metric": "service_level", "operator": ">=", "value": 0.8},
    ]

    passed = validate_constraints({"order_quantity": 120, "service_level": 1.0}, constraints)
    failed = validate_constraints({"order_quantity": 120, "service_level": 0.5}, constraints)

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "constraint_violation"
    assert failed.details["violations"][0]["metric"] == "service_level"


def test_unit_test_validator_reads_python_unit_test_tool_results():
    events = [
        TraceEvent(
            event_id="evt-000",
            event_type="tool_result",
            sequence=0,
            payload={
                "tool_name": "python.unit_tests",
                "result": {"passed": True, "tests_run": 2, "failures": 0},
            },
        )
    ]

    passed = validate_unit_tests(events, expected={"passed": True, "tests_run": 2, "failures": 0})
    failed = validate_unit_tests([], expected={"passed": True, "tests_run": 2, "failures": 0})

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "unit_tests_missing"


def test_policy_validator_checks_required_and_forbidden_terms():
    passed = validate_policy("Used fixture-backed data only.", required_terms=["fixture-backed"])
    failed = validate_policy(
        "This result is guaranteed.",
        required_terms=["fixture-backed"],
        forbidden_terms=["guaranteed"],
    )

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "policy_violation"
    assert failed.details["missing_required_terms"] == ["fixture-backed"]
    assert failed.details["forbidden_terms_present"] == ["guaranteed"]


def test_cost_latency_validator_catches_budget_regressions():
    passed = validate_cost_latency(
        {"cost": 0.0, "latency_seconds": 0.02, "turns": 3, "timed_out": False},
        max_cost=0.0,
        max_latency_seconds=1.0,
        max_turns=5,
    )
    failed = validate_cost_latency(
        {"cost": 0.1, "latency_seconds": 2.0, "turns": 7, "timed_out": True},
        max_cost=0.0,
        max_latency_seconds=1.0,
        max_turns=5,
    )

    assert passed.passed is True
    assert failed.passed is False
    assert failed.failure_type == "cost_latency_violation"
    assert set(failed.details["violations"]) == {"cost", "latency_seconds", "turns", "timed_out"}


def test_validators_config_declares_default_validator_names():
    validators_config = (ROOT / "configs" / "validators.yaml").read_text()

    assert default_validator_names() == [
        "schema",
        "tool_sequence",
        "argument",
        "state",
        "numeric",
        "citation",
        "constraint",
        "unit_test",
        "policy",
        "cost_latency",
        "lookahead_validator",
        "pnl_consistency_validator",
        "cost_inclusion_validator",
        "risk_limit_validator",
        "artifact_grounding_validator",
    ]
    for validator_name in default_validator_names():
        assert validator_name in validators_config


def test_trading_validators_catch_backtest_silent_failures():
    events = [
        TraceEvent(
            event_id="evt-000",
            event_type="tool_result",
            sequence=0,
            payload={
                "tool_name": "run_backtest",
                "result": {
                    "gross_pnl": 1250.0,
                    "net_pnl": 1250.0,
                    "fees": 0.0,
                    "sharpe": 2.1,
                    "max_drawdown": 0.12,
                    "costs_included": False,
                    "lookahead_detected": True,
                },
            },
        ),
        TraceEvent(
            event_id="evt-001",
            event_type="tool_result",
            sequence=1,
            payload={"tool_name": "risk_check", "result": {"passed": False, "violations": [{"metric": "max_drawdown"}]}},
        ),
    ]

    assert validate_lookahead(events).failure_type == "lookahead_detected"
    assert validate_cost_inclusion(events).failure_type == "costs_not_included"
    assert validate_pnl_consistency(events, {"net_pnl": 820.0}).failure_type == "pnl_consistency_mismatch"
    assert validate_risk_limits(events).failure_type == "risk_limit_violation"
    assert (
        validate_artifact_grounding(
            "Strategy is profitable.",
            events,
            required_sources=["strategy-report-mean-reversion-v1"],
        ).failure_type
        == "artifact_grounding_missing"
    )
