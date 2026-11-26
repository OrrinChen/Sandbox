"""Trace replay execution against fixture-backed tool adapters."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.schemas import JsonDict, SchemaValidationError, TaskSpec, TraceEvent
from sandboxed_agent_eval_harness.tasks import TaskSuite, known_task_suites
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, ToolExecutionError, ToolRegistryError
from sandboxed_agent_eval_harness.tracing.jsonl import TraceReplay
from sandboxed_agent_eval_harness.validators import validate_a1_rag, validate_financial_benchmark, validate_rag_grounding


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
    validator_results: list[JsonDict] = field(default_factory=list)

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
            "validator_results": self.validator_results,
            "passed": self.passed,
        }


class TraceReplayExecutor:
    """Re-execute persisted tool calls and compare them with recorded trace events."""

    def __init__(
        self,
        suite: Optional[TaskSuite] = None,
        executor: Optional[FixtureToolExecutor] = None,
        *,
        additional_suites: Sequence[TaskSuite] = (),
    ) -> None:
        self.suites = [suite] if suite is not None else known_task_suites()
        self.suites.extend(additional_suites)
        self.executor = executor or FixtureToolExecutor()

    def replay(self, trace_path: Path | str, workspace: Path | str) -> TraceReplayExecutionResult:
        path = Path(trace_path)
        replay = TraceReplay.from_jsonl(path)
        task_id = _task_id_from_replay(replay)
        task, suite_version = self._task_for(task_id)
        sandbox = self.executor.create_sandbox(task, workspace)
        before_state = sandbox.snapshot()

        comparisons: list[JsonDict] = []
        divergences: list[JsonDict] = []
        events = replay.events
        revalidate_rag = bool({"rag_grounding", "a1_rag", "financial_benchmark"}.intersection(task.validator_list))
        replayed_results: list[TraceEvent] = []
        tool_call_count = 0
        index = 0
        while index < len(events):
            event = events[index]
            if event.event_type != "tool_call":
                index += 1
                continue
            tool_name = event.payload.get("tool_name")
            if (not isinstance(tool_name, str) or not isinstance(event.payload.get("arguments"), dict)
                    or (revalidate_rag and tool_name not in task.available_tools)):
                divergences.append({"type": "invalid_tool_call", "tool_name": tool_name, "sequence": event.sequence})
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
            if revalidate_rag and comparison["execution_error"] is None:
                replayed_results.append(replace(recorded_result_event, payload={
                    "tool_name": comparison["tool_name"],
                    "result": comparison["replayed"],
                }))
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

        validator_results = []
        if revalidate_rag:
            versions = {"task_version": suite_version, "fixture_version": task.initial_state["fixture_version"]}
            if "tool_version" in task.initial_state:
                versions["tool_version"] = task.initial_state["tool_version"]
            for key, expected in versions.items():
                if replay.metadata.get(key) != expected:
                    divergences.append({"type": "version_mismatch", "field": key, "recorded": replay.metadata.get(key), "expected": expected})
            validator_results = _replay_rag_validation(task, replay, replayed_results, divergences)

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
            validator_results=validator_results,
        )

    def _execute_and_compare(
        self,
        tool_call_event: TraceEvent,
        recorded_result_event: TraceEvent,
        sandbox: Any,
    ) -> JsonDict:
        tool_name = tool_call_event.payload["tool_name"]
        arguments = tool_call_event.payload["arguments"]
        recorded_result = recorded_result_event.payload.get("result")
        try:
            replayed_result = self.executor.execute(tool_name, arguments, sandbox)
            execution_error = None
        except (ToolExecutionError, ToolRegistryError, SchemaValidationError) as exc:
            replayed_result = {}
            execution_error = str(exc)
        matches = (
            execution_error is None
            and recorded_result_event.payload.get("tool_name") == tool_name
            and recorded_result == replayed_result
        )
        return {
            "tool_name": tool_name,
            "tool_call_sequence": tool_call_event.sequence,
            "recorded_result_sequence": recorded_result_event.sequence,
            "recorded": recorded_result,
            "replayed": replayed_result,
            "matches": matches,
            "execution_error": execution_error,
        }

    def _task_for(self, task_id: str) -> tuple[TaskSpec, str]:
        for suite in self.suites:
            for task in suite.tasks:
                if task.task_id == task_id:
                    return task, suite.version
        raise TraceReplayExecutionError(f"trace references unknown task_id: {task_id}")


def _replay_rag_validation(
    task: TaskSpec,
    replay: TraceReplay,
    replayed_results: list[TraceEvent],
    divergences: list[JsonDict],
) -> list[JsonDict]:
    answers = replay.events_by_type("final_answer")
    if (len(answers) != 1 or not isinstance(answers[0].payload.get("content"), str)
            or any(event.sequence >= answers[0].sequence for event in replayed_results)):
        divergences.append({"type": "invalid_final_answer_event"})
        return []
    final_answer = answers[0].payload["content"]
    if "financial_benchmark" in task.validator_list:
        final_answer = _replay_financial_reader(task, replay, replayed_results, final_answer, divergences)
        result = validate_financial_benchmark(task, final_answer, replayed_results).to_dict()
    elif "a1_rag" in task.validator_list:
        result = validate_a1_rag(task.task_id, final_answer, replayed_results).to_dict()
    else:
        result = validate_rag_grounding(
            final_answer, replayed_results, task.hidden_expected_state["evidence_ids"],
        ).to_dict()
    recorded = [event.payload for event in replay.events_by_type("validator_result")]
    if recorded != [result]:
        divergences.append({"type": "validator_result_mismatch", "recorded": recorded, "replayed": [result]})
    return [result]


def _replay_financial_reader(
    task: TaskSpec,
    replay: TraceReplay,
    replayed_results: list[TraceEvent],
    final_answer: str,
    divergences: list[JsonDict],
) -> str:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.benchmark import comparison_baseline

    try:
        baseline = comparison_baseline(replay.metadata)
    except ValueError as exc:
        divergences.append({"type": "invalid_reader_comparison_metadata", "message": str(exc)})
        return final_answer
    if baseline is None:
        return final_answer
    plan = baseline.run(task)
    recorded_calls = [event.payload for event in replay.events_by_type("tool_call")]
    expected_calls = [{"tool_name": call.tool_name, "arguments": call.arguments} for call in plan.tool_calls]
    if recorded_calls != expected_calls or len(replayed_results) != len(expected_calls):
        divergences.append({"type": "reader_comparison_tool_call_mismatch"})
        return final_answer
    regenerated_answer = baseline.finalize(task, plan, replayed_results).final_answer
    if final_answer != regenerated_answer:
        divergences.append({"type": "reader_answer_mismatch", "recorded": final_answer, "replayed": regenerated_answer})
    return regenerated_answer


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
