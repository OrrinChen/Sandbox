"""Deterministic validators for trace and task outcome checks."""

from __future__ import annotations

import re
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


DEFAULT_VALIDATOR_NAMES = ["schema", "tool_sequence", "argument", "state", "numeric", "citation"]
_CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_.:/-]+)\]")
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


def _tool_call_names(events: Sequence[TraceEvent]) -> list[str]:
    return [
        str(event.payload.get("tool_name"))
        for event in events
        if event.event_type == "tool_call" and "tool_name" in event.payload
    ]


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
