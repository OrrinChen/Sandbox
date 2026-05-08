"""JSONL trace logging and replay helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from sandboxed_agent_eval_harness.schemas import JsonDict, SchemaValidationError, TraceEvent, ValidatorResult


class TraceReplayError(ValueError):
    """Raised when a persisted trace cannot be loaded or replayed."""


def load_trace_events(path: Path | str) -> list[TraceEvent]:
    """Load trace events from a newline-delimited JSON trace file."""

    trace_path = Path(path)
    events: list[TraceEvent] = []
    try:
        lines = trace_path.read_text().splitlines()
    except OSError as exc:
        raise TraceReplayError(f"could not read trace file: {trace_path}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(TraceEvent.from_json_line(line))
        except (SchemaValidationError, ValueError) as exc:
            raise TraceReplayError(f"invalid TraceEvent on line {line_number}: {exc}") from exc
    return events


class TraceLogger:
    """Append ordered trace events to a JSONL file."""

    def __init__(self, path: Path | str, run_metadata: Optional[Mapping[str, Any]] = None) -> None:
        self.path = Path(path)
        self.run_metadata: JsonDict = dict(run_metadata or {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence = len(load_trace_events(self.path)) if self.path.exists() else 0

    def log_user_message(self, content: str, metadata: Optional[Mapping[str, Any]] = None) -> TraceEvent:
        return self._append("user_message", {"content": content}, metadata=metadata)

    def log_agent_message(self, content: str, metadata: Optional[Mapping[str, Any]] = None) -> TraceEvent:
        return self._append("agent_message", {"content": content}, metadata=metadata)

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> TraceEvent:
        return self._append(
            "tool_call",
            {"tool_name": tool_name, "arguments": dict(arguments)},
            metadata=metadata,
        )

    def log_tool_result(
        self,
        tool_name: str,
        result: Mapping[str, Any],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> TraceEvent:
        return self._append("tool_result", {"tool_name": tool_name, "result": dict(result)}, metadata=metadata)

    def log_state_diff(self, diff: Any, metadata: Optional[Mapping[str, Any]] = None) -> TraceEvent:
        payload = diff.to_dict() if hasattr(diff, "to_dict") else dict(diff)
        return self._append("state_diff", payload, metadata=metadata)

    def log_validator_result(
        self,
        validator_result: ValidatorResult | Mapping[str, Any],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> TraceEvent:
        payload = validator_result.to_dict() if hasattr(validator_result, "to_dict") else dict(validator_result)
        return self._append("validator_result", payload, metadata=metadata)

    def log_timeout(
        self,
        operation: str,
        timeout_seconds: float,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> TraceEvent:
        return self._append(
            "timeout_event",
            {"operation": operation, "timeout_seconds": timeout_seconds},
            metadata=metadata,
        )

    def log_error(self, error_type: str, message: str, metadata: Optional[Mapping[str, Any]] = None) -> TraceEvent:
        return self._append("error_event", {"error_type": error_type, "message": message}, metadata=metadata)

    def log_graph_node(
        self,
        node: str,
        payload: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> TraceEvent:
        event_payload = {"node": node}
        if payload:
            event_payload.update(dict(payload))
        return self._append("graph_node", event_payload, metadata=metadata)

    def _append(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> TraceEvent:
        event_metadata = dict(self.run_metadata)
        if metadata:
            event_metadata.update(metadata)
        event = TraceEvent(
            event_id=self._event_id(self._sequence),
            event_type=event_type,
            sequence=self._sequence,
            payload=dict(payload),
            metadata=event_metadata,
        )
        with self.path.open("a") as trace_file:
            trace_file.write(event.to_json_line() + "\n")
        self._sequence += 1
        return event

    def _event_id(self, sequence: int) -> str:
        run_id = self.run_metadata.get("run_id", "trace")
        return f"{run_id}-{sequence:06d}"


class TraceReplay:
    """Loaded trace events plus fixture state needed for deterministic replay."""

    def __init__(
        self,
        events: list[TraceEvent],
        fixture_state: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.events = list(events)
        self.fixture_state: JsonDict = dict(fixture_state or {})
        self._validate_contiguous_sequences()
        self.metadata: JsonDict = dict(self.events[0].metadata) if self.events else {}

    @classmethod
    def from_jsonl(
        cls,
        path: Path | str,
        fixture_state: Optional[Mapping[str, Any]] = None,
    ) -> "TraceReplay":
        return cls(load_trace_events(path), fixture_state=fixture_state)

    def events_by_type(self, event_type: str) -> list[TraceEvent]:
        return [event for event in self.events if event.event_type == event_type]

    def _validate_contiguous_sequences(self) -> None:
        sequences = [event.sequence for event in self.events]
        expected = list(range(len(self.events)))
        if sequences != expected:
            raise TraceReplayError(
                f"trace sequences must be contiguous from 0; expected {expected}, got {sequences}"
            )
