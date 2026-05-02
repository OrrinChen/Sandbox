"""Trace replay execution against fixture-backed tool adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from sandboxed_agent_eval_harness.schemas import JsonDict, TraceEvent
from sandboxed_agent_eval_harness.tasks import TaskSuite, known_task_suites
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, ToolExecutionError
from sandboxed_agent_eval_harness.tracing.jsonl import TraceReplay


class TraceReplayExecutionError(RuntimeError):
    """Raised when a trace cannot be re-executed deterministically."""


@dataclass(frozen=True)
class TraceReplayExecutionResult:
    trace_path: Path
    task_id: str
    replayed_tool_calls: int
    tool_result_comparisons: list[JsonDict]
    recorded_state_diff: JsonDict
    replayed_state_diff: JsonDict
    state_diff_matches: bool
    divergences: list[JsonDict]
    workspace_path: Path

    @property
    def passed(self) -> bool:
        return not self.divergences

    def to_dict(self) -> JsonDict:
        return {
            "trace_path": str(self.trace_path),
            "task_id": self.task_id,
            "replayed_tool_calls": self.replayed_tool_calls,
            "tool_result_comparisons": [dict(item) for item in self.tool_result_comparisons],
            "recorded_state_diff": dict(self.recorded_state_diff),
            "replayed_state_diff": dict(self.replayed_state_diff),
            "state_diff_matches": self.state_diff_matches,
            "divergences": [dict(item) for item in self.divergences],
            "workspace_path": str(self.workspace_path),
            "passed": self.passed,
        }


class TraceReplayExecutor:
    """Re-execute persisted tool calls and compare them with recorded trace events."""

    def __init__(
        self,
        suite: Optional[TaskSuite] = None,
        executor: Optional[FixtureToolExecutor] = None,
    ) -> None:
        self.suites = [suite] if suite is not None else known_task_suites()
        self.executor = executor or FixtureToolExecutor()

    def replay(self, trace_path: Path | str, workspace: Path | str) -> TraceReplayExecutionResult:
        path = Path(trace_path)
        replay = TraceReplay.from_jsonl(path)
        task_id = _task_id_from_replay(replay)
        task = self._task_for(task_id)
        sandbox = self.executor.create_sandbox(task, workspace)
        before_state = sandbox.snapshot()

        comparisons: list[JsonDict] = []
        divergences: list[JsonDict] = []
        events = replay.events
        tool_call_count = 0
        index = 0
        while index < len(events):
            event = events[index]
            if event.event_type != "tool_call":
                index += 1
                continue
            tool_call_count += 1
            recorded_result_event = _next_tool_result(events, index + 1)
            if recorded_result_event is None:
                divergences.append(
                    {
                        "type": "missing_recorded_tool_result",
                        "tool_name": event.payload.get("tool_name"),
                        "sequence": event.sequence,
                    }
                )
                index += 1
                continue
            comparison = self._execute_and_compare(event, recorded_result_event, sandbox)
            comparisons.append(comparison)
            if not comparison["matches"]:
                divergences.append(
                    {
                        "type": "tool_result_mismatch",
                        "tool_name": comparison["tool_name"],
                        "tool_call_sequence": comparison["tool_call_sequence"],
                        "recorded": comparison["recorded"],
                        "replayed": comparison["replayed"],
                    }
                )
            index += 1

        recorded_state_diff = _recorded_state_diff(events)
        replayed_state_diff = before_state.diff(sandbox.snapshot()).to_dict()
        state_diff_matches = recorded_state_diff == replayed_state_diff
        if not state_diff_matches:
            divergences.append(
                {
                    "type": "state_diff_mismatch",
                    "recorded": recorded_state_diff,
                    "replayed": replayed_state_diff,
                }
            )

        return TraceReplayExecutionResult(
            trace_path=path,
            task_id=task_id,
            replayed_tool_calls=tool_call_count,
            tool_result_comparisons=comparisons,
            recorded_state_diff=recorded_state_diff,
            replayed_state_diff=replayed_state_diff,
            state_diff_matches=state_diff_matches,
            divergences=divergences,
            workspace_path=Path(workspace),
        )

    def _execute_and_compare(
        self,
        tool_call_event: TraceEvent,
        recorded_result_event: TraceEvent,
        sandbox: Any,
    ) -> JsonDict:
        tool_name = tool_call_event.payload["tool_name"]
        arguments = tool_call_event.payload["arguments"]
        recorded_result = dict(recorded_result_event.payload.get("result", {}))
        try:
            replayed_result = self.executor.execute(tool_name, arguments, sandbox)
            execution_error = None
        except ToolExecutionError as exc:
            replayed_result = {}
            execution_error = str(exc)
        matches = execution_error is None and recorded_result == replayed_result
        return {
            "tool_name": tool_name,
            "tool_call_sequence": tool_call_event.sequence,
            "recorded_result_sequence": recorded_result_event.sequence,
            "recorded": recorded_result,
            "replayed": replayed_result,
            "matches": matches,
            "execution_error": execution_error,
        }

    def _task_for(self, task_id: str) -> Any:
        for suite in self.suites:
            for task in suite.tasks:
                if task.task_id == task_id:
                    return task
        raise TraceReplayExecutionError(f"trace references unknown task_id: {task_id}")


def _task_id_from_replay(replay: TraceReplay) -> str:
    task_id = replay.metadata.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise TraceReplayExecutionError("trace metadata must include task_id")
    return task_id


def _next_tool_result(events: list[TraceEvent], start_index: int) -> Optional[TraceEvent]:
    for event in events[start_index:]:
        if event.event_type == "tool_result":
            return event
        if event.event_type == "tool_call":
            return None
    return None


def _recorded_state_diff(events: list[TraceEvent]) -> JsonDict:
    for event in events:
        if event.event_type == "state_diff":
            return dict(event.payload)
    return {"added": [], "modified": [], "deleted": []}
