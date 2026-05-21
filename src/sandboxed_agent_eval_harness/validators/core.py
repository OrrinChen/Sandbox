"""Deterministic validators for trace and task outcome checks."""

from __future__ import annotations

import re
import operator
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.sandbox import StateDiff
from sandboxed_agent_eval_harness.schemas import (
    JsonDict,
    RunResult,
    SchemaValidationError,
    TaskSpec,
    ToolSpec,
    TraceEvent,
    ValidatorResult,
)
from sandboxed_agent_eval_harness.tools import ToolRegistry, ToolRegistryError


DEFAULT_VALIDATOR_NAMES = [
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
_CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_.:/-]+)\]")
_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}
_SCHEMA_FACTORIES: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    "task": TaskSpec.from_dict,
    "tool": ToolSpec.from_dict,
    "trace_event": TraceEvent.from_dict,
    "validator_result": ValidatorResult.from_dict,
    "run_result": RunResult.from_dict,
}


def default_validator_names() -> list[str]:
    return list(DEFAULT_VALIDATOR_NAMES)


def validate_schema(schema_name: str, payload: Mapping[str, Any]) -> ValidatorResult:
    factory = _SCHEMA_FACTORIES.get(schema_name)
    if factory is None:
        return _failed(
            "schema",
            "unknown_schema",
            f"Unknown schema validator target: {schema_name}.",
            {"schema_name": schema_name, "supported_schemas": sorted(_SCHEMA_FACTORIES)},
        )
    try:
        factory(payload)
    except (SchemaValidationError, TypeError, ValueError) as exc:
        return _failed(
            "schema",
            "schema_mismatch",
            str(exc),
            {"schema_name": schema_name, "error": str(exc)},
        )
    return _passed("schema", f"{schema_name} schema matched.")


def validate_tool_sequence(
    events: Sequence[TraceEvent],
    expected_sequence: Optional[Sequence[str]] = None,
    allowed_tools: Optional[Iterable[str]] = None,
    required_tools: Optional[Iterable[str]] = None,
) -> ValidatorResult:
    actual_sequence = _tool_call_names(events)
    if expected_sequence is not None and actual_sequence != list(expected_sequence):
        return _failed(
            "tool_sequence",
            "tool_sequence_mismatch",
            "Tool call sequence did not match expected sequence.",
            {"expected_sequence": list(expected_sequence), "actual_sequence": actual_sequence},
        )

    if allowed_tools is not None:
        allowed = set(allowed_tools)
        unexpected = _unique(tool for tool in actual_sequence if tool not in allowed)
        if unexpected:
            return _failed(
                "tool_sequence",
                "unexpected_tool",
                "Tool call sequence included tools outside the allowed set.",
                {"allowed_tools": sorted(allowed), "unexpected_tools": unexpected, "actual_sequence": actual_sequence},
            )

    if required_tools is not None:
        missing = [tool for tool in required_tools if tool not in actual_sequence]
        if missing:
            return _failed(
                "tool_sequence",
                "missing_required_tool",
                "Tool call sequence omitted required tools.",
                {"missing_tools": missing, "actual_sequence": actual_sequence},
            )

    return _passed("tool_sequence", "Tool call sequence matched.")


def validate_tool_arguments(events: Sequence[TraceEvent], registry: ToolRegistry) -> ValidatorResult:
    for event in events:
        if event.event_type != "tool_call":
            continue
        tool_name = event.payload.get("tool_name")
        arguments = event.payload.get("arguments")
        if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
            return _failed(
                "argument",
                "invalid_tool_call_payload",
                "Tool call trace event is missing a valid tool_name or arguments object.",
                {"sequence": event.sequence, "payload": dict(event.payload)},
            )
        try:
            registry.validate_input(tool_name, arguments)
        except (SchemaValidationError, ToolRegistryError) as exc:
            return _failed(
                "argument",
                "invalid_tool_arguments",
                str(exc),
                {"sequence": event.sequence, "tool_name": tool_name, "error": str(exc)},
            )
    return _passed("argument", "Tool call arguments matched registered schemas.")


def validate_state(
    actual_diff: StateDiff | Mapping[str, Any],
    expected_diff: StateDiff | Mapping[str, Any],
) -> ValidatorResult:
    actual = _normalize_state_diff(actual_diff)
    expected = _normalize_state_diff(expected_diff)
    if actual != expected:
        return _failed(
            "state",
            "state_mismatch",
            "State diff did not match expected state mutation.",
            {"expected": expected, "actual": actual},
        )
    return _passed("state", "State diff matched expected mutation.")


def validate_numeric(
    metric: str,
    actual: int | float,
    expected: int | float,
    tolerance: int | float = 0,
) -> ValidatorResult:
    details = {"metric": metric, "actual": actual, "expected": expected, "tolerance": tolerance}
    if not _is_number(actual) or not _is_number(expected) or not _is_number(tolerance):
        return _failed("numeric", "invalid_numeric_value", "Numeric validator received a non-numeric value.", details)
    if tolerance < 0:
        return _failed("numeric", "invalid_numeric_tolerance", "Numeric tolerance must be non-negative.", details)
    if abs(actual - expected) > tolerance:
        return _failed("numeric", "numeric_mismatch", f"{metric} did not match expected value.", details)
    return _passed("numeric", f"{metric} matched expected value.", details)


def validate_citations(
    final_answer: str,
    supported_citations: Iterable[str],
    required_citations: Optional[Iterable[str]] = None,
) -> ValidatorResult:
    cited = _unique(_CITATION_PATTERN.findall(final_answer))
    supported = set(supported_citations)
    unsupported = [citation for citation in cited if citation not in supported]
    details: JsonDict = {
        "citations": cited,
        "supported_citations": sorted(supported),
        "unsupported_citations": unsupported,
    }
    if unsupported:
        return _failed("citation", "unsupported_citation", "Final answer cited unsupported sources.", details)

    if required_citations is not None:
        missing = [citation for citation in required_citations if citation not in cited]
        details["missing_citations"] = missing
        if missing:
            return _failed("citation", "missing_citation", "Final answer omitted required citations.", details)

    return _passed("citation", "Final answer citations are supported.", details)


def validate_constraints(metrics: Mapping[str, Any], constraints: Sequence[Mapping[str, Any]]) -> ValidatorResult:
    violations: list[JsonDict] = []
    invalid_constraints: list[JsonDict] = []
    for constraint in constraints:
        metric = constraint.get("metric")
        operator_name = constraint.get("operator")
        expected_value = constraint.get("value")
        if not isinstance(metric, str) or operator_name not in _OPERATORS or not _is_number(expected_value):
            invalid_constraints.append(dict(constraint))
            continue
        actual_value = metrics.get(metric)
        if not _is_number(actual_value) or not _OPERATORS[str(operator_name)](actual_value, expected_value):
            violations.append(
                {
                    "metric": metric,
                    "operator": operator_name,
                    "value": expected_value,
                    "actual": actual_value,
                }
            )
    details = {
        "constraints": [dict(constraint) for constraint in constraints],
        "violations": violations,
        "invalid_constraints": invalid_constraints,
    }
    if invalid_constraints:
        return _failed("constraint", "invalid_constraint", "Constraint validator received malformed constraints.", details)
    if violations:
        return _failed("constraint", "constraint_violation", "One or more constraints were violated.", details)
    return _passed("constraint", "All constraints were satisfied.", details)


def validate_unit_tests(
    events: Sequence[TraceEvent],
    expected: Optional[Mapping[str, Any]] = None,
) -> ValidatorResult:
    expected_result = dict(expected or {})
    result = _latest_tool_result(events, "python.unit_tests")
    if result is None:
        return _failed(
            "unit_test",
            "unit_tests_missing",
            "No python.unit_tests tool result was found in the trace.",
            {"expected": expected_result},
        )

    mismatches = {}
    for key, expected_value in expected_result.items():
        if result.get(key) != expected_value:
            mismatches[key] = {"expected": expected_value, "actual": result.get(key)}
    details = {"expected": expected_result, "actual": result, "mismatches": mismatches}
    if result.get("passed") is not True or mismatches:
        return _failed("unit_test", "unit_tests_failed", "Unit test results did not match expected outcome.", details)
    return _passed("unit_test", "Unit test results matched expected outcome.", details)


def validate_policy(
    final_answer: str,
    required_terms: Optional[Iterable[str]] = None,
    forbidden_terms: Optional[Iterable[str]] = None,
) -> ValidatorResult:
    answer = final_answer.lower()
    required = list(required_terms or [])
    forbidden = list(forbidden_terms or [])
    missing_required = [term for term in required if term.lower() not in answer]
    forbidden_present = [term for term in forbidden if term.lower() in answer]
    details = {
        "required_terms": required,
        "forbidden_terms": forbidden,
        "missing_required_terms": missing_required,
        "forbidden_terms_present": forbidden_present,
    }
    if missing_required or forbidden_present:
        return _failed("policy", "policy_violation", "Final answer violated deterministic policy terms.", details)
    return _passed("policy", "Final answer satisfied deterministic policy terms.", details)


def validate_cost_latency(
    metrics: Mapping[str, Any],
    *,
    max_cost: float,
    max_latency_seconds: float,
    max_turns: int,
) -> ValidatorResult:
    violations: list[str] = []
    cost = metrics.get("cost")
    latency_seconds = metrics.get("latency_seconds")
    turns = metrics.get("turns")
    timed_out = metrics.get("timed_out")
    if not _is_number(cost) or cost > max_cost:
        violations.append("cost")
    if not _is_number(latency_seconds) or latency_seconds > max_latency_seconds:
        violations.append("latency_seconds")
    if not isinstance(turns, int) or isinstance(turns, bool) or turns > max_turns:
        violations.append("turns")
    if timed_out is True:
        violations.append("timed_out")
    details = {
        "metrics": dict(metrics),
        "max_cost": max_cost,
        "max_latency_seconds": max_latency_seconds,
        "max_turns": max_turns,
        "violations": violations,
    }
    if violations:
        return _failed(
            "cost_latency",
            "cost_latency_violation",
            "Cost, latency, turn, or timeout limits were violated.",
            details,
        )
    return _passed("cost_latency", "Cost, latency, turn, and timeout limits were satisfied.", details)


def validate_lookahead(events: Sequence[TraceEvent]) -> ValidatorResult:
    backtest = _latest_tool_result(events, "run_backtest")
    market_data = _latest_tool_result(events, "load_market_data")
    details = {"run_backtest": backtest, "load_market_data": market_data}
    if backtest is None:
        return _failed(
            "lookahead_validator",
            "backtest_missing",
            "No run_backtest result was found for lookahead validation.",
            details,
        )
    if backtest.get("lookahead_detected") is True or (market_data or {}).get("has_future_return_column") is True:
        return _failed(
            "lookahead_validator",
            "lookahead_detected",
            "Backtest used future-return columns or a lookahead-enabled config.",
            details,
        )
    return _passed("lookahead_validator", "No lookahead was detected.", details)


def validate_pnl_consistency(
    events: Sequence[TraceEvent],
    reported_metrics: Mapping[str, Any],
    *,
    tolerance: float = 0.0,
) -> ValidatorResult:
    backtest = _latest_tool_result(events, "run_backtest")
    if backtest is None:
        return _failed(
            "pnl_consistency_validator",
            "backtest_missing",
            "No run_backtest result was found for PnL consistency validation.",
            {"reported_metrics": dict(reported_metrics)},
        )
    mismatches = {}
    for metric in ["gross_pnl", "net_pnl", "fees", "sharpe", "max_drawdown"]:
        if metric not in reported_metrics:
            continue
        actual = reported_metrics.get(metric)
        expected = backtest.get(metric)
        if not _is_number(actual) or not _is_number(expected) or abs(actual - expected) > tolerance:
            mismatches[metric] = {"reported": actual, "artifact": expected}
    details = {"reported_metrics": dict(reported_metrics), "backtest": backtest, "mismatches": mismatches}
    if mismatches:
        return _failed(
            "pnl_consistency_validator",
            "pnl_consistency_mismatch",
            "Reported PnL or risk metrics did not match the backtest artifact.",
            details,
        )
    return _passed("pnl_consistency_validator", "Reported metrics matched the backtest artifact.", details)


def validate_cost_inclusion(events: Sequence[TraceEvent]) -> ValidatorResult:
    backtest = _latest_tool_result(events, "run_backtest")
    details = {"run_backtest": backtest}
    if backtest is None:
        return _failed(
            "cost_inclusion_validator",
            "backtest_missing",
            "No run_backtest result was found for cost inclusion validation.",
            details,
        )
    if backtest.get("costs_included") is not True or not _is_number(backtest.get("fees")) or backtest.get("fees") <= 0:
        return _failed(
            "cost_inclusion_validator",
            "costs_not_included",
            "Backtest artifact did not include trading costs.",
            details,
        )
    return _passed("cost_inclusion_validator", "Trading costs were included in backtest results.", details)


def validate_risk_limits(events: Sequence[TraceEvent]) -> ValidatorResult:
    risk = _latest_tool_result(events, "risk_check")
    details = {"risk_check": risk}
    if risk is None:
        return _failed(
            "risk_limit_validator",
            "risk_check_missing",
            "No risk_check result was found.",
            details,
        )
    if risk.get("passed") is not True or risk.get("violations"):
        return _failed(
            "risk_limit_validator",
            "risk_limit_violation",
            "Risk check reported one or more limit violations.",
            details,
        )
    return _passed("risk_limit_validator", "Risk limits were satisfied.", details)


def validate_artifact_grounding(
    final_answer: str,
    events: Sequence[TraceEvent],
    *,
    required_sources: Optional[Iterable[str]] = None,
) -> ValidatorResult:
    required = list(required_sources or [])
    observed = _observed_sources(events)
    missing_sources = [source for source in required if source not in observed]
    missing_citations = [source for source in required if f"[{source}]" not in final_answer]
    details = {
        "required_sources": required,
        "observed_sources": observed,
        "missing_sources": missing_sources,
        "missing_citations": missing_citations,
    }
    if missing_sources or missing_citations:
        return _failed(
            "artifact_grounding_validator",
            "artifact_grounding_missing",
            "Final answer was not grounded in required trading artifacts.",
            details,
        )
    return _passed("artifact_grounding_validator", "Final answer was grounded in required artifacts.", details)


def _tool_call_names(events: Sequence[TraceEvent]) -> list[str]:
    return [
        str(event.payload.get("tool_name"))
        for event in events
        if event.event_type == "tool_call" and "tool_name" in event.payload
    ]


def _latest_tool_result(events: Sequence[TraceEvent], tool_name: str) -> Optional[JsonDict]:
    for event in reversed(events):
        if event.event_type != "tool_result":
            continue
        if event.payload.get("tool_name") != tool_name:
            continue
        result = event.payload.get("result")
        return dict(result) if isinstance(result, Mapping) else None
    return None


def _observed_sources(events: Sequence[TraceEvent]) -> list[str]:
    sources: list[str] = []
    for event in events:
        if event.event_type != "tool_result":
            continue
        result = event.payload.get("result", {})
        if not isinstance(result, Mapping):
            continue
        source = result.get("source")
        if isinstance(source, str):
            sources.append(source)
        raw_sources = result.get("sources")
        if isinstance(raw_sources, list):
            sources.extend(source for source in raw_sources if isinstance(source, str))
    return _unique(sources)


def _normalize_state_diff(diff: StateDiff | Mapping[str, Any]) -> JsonDict:
    raw = diff.to_dict() if hasattr(diff, "to_dict") else dict(diff)
    return {
        "added": list(raw.get("added", [])),
        "modified": list(raw.get("modified", [])),
        "deleted": list(raw.get("deleted", [])),
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _unique(items: Iterable[str]) -> list[str]:
    seen = set()
    unique_items = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items


def _passed(validator_name: str, message: str, details: Optional[Mapping[str, Any]] = None) -> ValidatorResult:
    return ValidatorResult(
        validator_name=validator_name,
        passed=True,
        message=message,
        details=dict(details or {}),
    )


def _failed(validator_name: str, failure_type: str, message: str, details: Mapping[str, Any]) -> ValidatorResult:
    return ValidatorResult(
        validator_name=validator_name,
        passed=False,
        failure_type=failure_type,
        message=message,
        details=dict(details),
    )
