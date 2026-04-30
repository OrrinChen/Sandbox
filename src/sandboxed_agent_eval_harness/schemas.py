"""Core typed schemas for tasks, tools, traces, validators, and runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional


JsonDict = Dict[str, Any]


class SchemaValidationError(ValueError):
    """Raised when a schema payload is missing required or typed fields."""


def _require_fields(payload: Mapping[str, Any], required: Iterable[str], schema_name: str) -> None:
    missing = [field_name for field_name in required if field_name not in payload]
    if missing:
        raise SchemaValidationError(f"{schema_name} missing required field(s): {', '.join(missing)}")


def _require_non_empty_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{field_name} must be a non-empty string")


def _require_string_list(value: Any, field_name: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SchemaValidationError(f"{field_name} must be a list of strings")


def _require_mapping(value: Any, field_name: str) -> None:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{field_name} must be an object")


def _json_type_matches(value: Any, expected_type: str) -> bool:
    type_map = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "null": lambda item: item is None,
    }
    if expected_type not in type_map:
        raise SchemaValidationError(f"unsupported schema type: {expected_type}")
    return type_map[expected_type](value)


def _validate_json_object_schema(schema: Mapping[str, Any], payload: Mapping[str, Any], context: str) -> JsonDict:
    if schema.get("type") != "object":
        raise SchemaValidationError(f"{context} schema must have type object")
    _require_mapping(payload, context)

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict):
        raise SchemaValidationError(f"{context} schema properties must be an object")
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise SchemaValidationError(f"{context} schema required must be a list of strings")

    _require_fields(payload, required, context)

    for field_name, field_schema in properties.items():
        if field_name not in payload:
            continue
        if not isinstance(field_schema, dict):
            raise SchemaValidationError(f"{context}.{field_name} schema must be an object")
        expected_type = field_schema.get("type")
        if expected_type and not _json_type_matches(payload[field_name], expected_type):
            raise SchemaValidationError(f"{context}.{field_name} must be {expected_type}")

    return dict(payload)


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    domain: str
    instruction: str
    available_tools: List[str]
    initial_state: JsonDict
    hidden_expected_state: JsonDict
    visible_files: List[str]
    success_criteria: List[str]
    validator_list: List[str]
    max_turns: int
    max_cost: float
    timeout_seconds: int

    def __post_init__(self) -> None:
        _require_non_empty_string(self.task_id, "task_id")
        _require_non_empty_string(self.domain, "domain")
        _require_non_empty_string(self.instruction, "instruction")
        _require_string_list(self.available_tools, "available_tools")
        _require_mapping(self.initial_state, "initial_state")
        _require_mapping(self.hidden_expected_state, "hidden_expected_state")
        _require_string_list(self.visible_files, "visible_files")
        _require_string_list(self.success_criteria, "success_criteria")
        _require_string_list(self.validator_list, "validator_list")
        if not isinstance(self.max_turns, int) or self.max_turns <= 0:
            raise SchemaValidationError("max_turns must be a positive integer")
        if not isinstance(self.max_cost, (int, float)) or isinstance(self.max_cost, bool) or self.max_cost < 0:
            raise SchemaValidationError("max_cost must be a non-negative number")
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise SchemaValidationError("timeout_seconds must be a positive integer")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskSpec":
        required = (
            "task_id",
            "domain",
            "instruction",
            "available_tools",
            "initial_state",
            "hidden_expected_state",
            "visible_files",
            "success_criteria",
            "validator_list",
            "max_turns",
            "max_cost",
            "timeout_seconds",
        )
        _require_fields(payload, required, "TaskSpec")
        return cls(**{field_name: payload[field_name] for field_name in required})


@dataclass(frozen=True)
class ToolSpec:
    tool_name: str
    input_schema: JsonDict
    output_schema: JsonDict
    side_effects: List[str]
    permissions: List[str]
    state_mutation: JsonDict
    failure_modes: List[str]

    def __post_init__(self) -> None:
        _require_non_empty_string(self.tool_name, "tool_name")
        _require_mapping(self.input_schema, "input_schema")
        _require_mapping(self.output_schema, "output_schema")
        _require_string_list(self.side_effects, "side_effects")
        _require_string_list(self.permissions, "permissions")
        _require_mapping(self.state_mutation, "state_mutation")
        _require_string_list(self.failure_modes, "failure_modes")

    def validate_input(self, arguments: Mapping[str, Any]) -> JsonDict:
        return _validate_json_object_schema(self.input_schema, arguments, f"{self.tool_name}.input")

    def validate_output(self, result: Mapping[str, Any]) -> JsonDict:
        return _validate_json_object_schema(self.output_schema, result, f"{self.tool_name}.output")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolSpec":
        required = (
            "tool_name",
            "input_schema",
            "output_schema",
            "side_effects",
            "permissions",
            "state_mutation",
            "failure_modes",
        )
        _require_fields(payload, required, "ToolSpec")
        return cls(**{field_name: payload[field_name] for field_name in required})


@dataclass(frozen=True)
class TraceEvent:
    event_id: str
    event_type: str
    sequence: int
    payload: JsonDict
    metadata: JsonDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty_string(self.event_id, "event_id")
        _require_non_empty_string(self.event_type, "event_type")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise SchemaValidationError("sequence must be a non-negative integer")
        _require_mapping(self.payload, "payload")
        _require_mapping(self.metadata, "metadata")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TraceEvent":
        required = ("event_id", "event_type", "sequence", "payload")
        _require_fields(payload, required, "TraceEvent")
        return cls(
            event_id=payload["event_id"],
            event_type=payload["event_type"],
            sequence=payload["sequence"],
            payload=payload["payload"],
            metadata=payload.get("metadata", {}),
        )

    @classmethod
    def from_json_line(cls, line: str) -> "TraceEvent":
        return cls.from_dict(json.loads(line))


@dataclass(frozen=True)
class ValidatorResult:
    validator_name: str
    passed: bool
    message: str
    failure_type: Optional[str] = None
    details: JsonDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty_string(self.validator_name, "validator_name")
        if not isinstance(self.passed, bool):
            raise SchemaValidationError("passed must be a boolean")
        _require_non_empty_string(self.message, "message")
        if not self.passed:
            _require_non_empty_string(self.failure_type, "failure_type")
        if self.failure_type is not None and not isinstance(self.failure_type, str):
            raise SchemaValidationError("failure_type must be a string when provided")
        _require_mapping(self.details, "details")

    def to_dict(self) -> JsonDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ValidatorResult":
        required = ("validator_name", "passed", "message")
        _require_fields(payload, required, "ValidatorResult")
        return cls(
            validator_name=payload["validator_name"],
            passed=payload["passed"],
            message=payload["message"],
            failure_type=payload.get("failure_type"),
            details=payload.get("details", {}),
        )


@dataclass(frozen=True)
class RunResult:
    run_id: str
    task_id: str
    agent_id: str
    passed: bool
    trace_events: List[TraceEvent]
    validator_results: List[ValidatorResult]
    metrics: JsonDict
    failure_labels: List[str]

    def __post_init__(self) -> None:
        _require_non_empty_string(self.run_id, "run_id")
        _require_non_empty_string(self.task_id, "task_id")
        _require_non_empty_string(self.agent_id, "agent_id")
        if not isinstance(self.passed, bool):
            raise SchemaValidationError("passed must be a boolean")
        if any(not isinstance(event, TraceEvent) for event in self.trace_events):
            raise SchemaValidationError("trace_events must contain TraceEvent instances")
        if any(not isinstance(result, ValidatorResult) for result in self.validator_results):
            raise SchemaValidationError("validator_results must contain ValidatorResult instances")
        _require_mapping(self.metrics, "metrics")
        _require_string_list(self.failure_labels, "failure_labels")
        if self.passed and any(not result.passed for result in self.validator_results):
            raise SchemaValidationError("passed cannot be true when a validator failed")

    def to_dict(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "passed": self.passed,
            "trace_events": [event.to_dict() for event in self.trace_events],
            "validator_results": [result.to_dict() for result in self.validator_results],
            "metrics": dict(self.metrics),
            "failure_labels": list(self.failure_labels),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunResult":
        required = (
            "run_id",
            "task_id",
            "agent_id",
            "passed",
            "trace_events",
            "validator_results",
            "metrics",
            "failure_labels",
        )
        _require_fields(payload, required, "RunResult")
        return cls(
            run_id=payload["run_id"],
            task_id=payload["task_id"],
            agent_id=payload["agent_id"],
            passed=payload["passed"],
            trace_events=[TraceEvent.from_dict(event) for event in payload["trace_events"]],
            validator_results=[
                ValidatorResult.from_dict(result) for result in payload["validator_results"]
            ],
            metrics=payload["metrics"],
            failure_labels=payload["failure_labels"],
        )
