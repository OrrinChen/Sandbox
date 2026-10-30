"""Gymnasium-style multi-turn environment over fixture-backed harness tasks.

``step`` returns ``(observation, reward, terminated, truncated, info)``.
Intermediate rewards are 0. The terminal reward is the evaluator outcome.
The observation never includes hidden expected state, gold outputs, or success
criteria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from sandboxed_agent_eval_harness.rl.actions import ParsedAction, parse_action, render_action
from sandboxed_agent_eval_harness.rl.reward import RewardWeights, oracle_leak_findings, score_trajectory
from sandboxed_agent_eval_harness.sandbox import FileSystemSandbox
from sandboxed_agent_eval_harness.schemas import JsonDict, SchemaValidationError, TaskSpec, TraceEvent
from sandboxed_agent_eval_harness.tools import (
    FixtureToolExecutor,
    ToolExecutionError,
    ToolRegistry,
    ToolRegistryError,
    default_tool_registry,
)
from sandboxed_agent_eval_harness.tracing import TraceLogger


@dataclass
class EpisodeState:
    task: TaskSpec
    metadata: JsonDict
    turn_index: int = 0
    format_errors: int = 0
    invalid_tool_calls: int = 0
    execution_errors: list[str] = field(default_factory=list)
    history: list[JsonDict] = field(default_factory=list)
    trace_events: list[TraceEvent] = field(default_factory=list)
    final_answer: str = ""
    reported_metrics: JsonDict = field(default_factory=dict)
    finished: bool = False


class SandboxToolEnv:
    """One task at a time. Call ``reset`` with a task id from the supplied split."""

    def __init__(
        self,
        tasks: Sequence[TaskSpec],
        *,
        task_metadata: Mapping[str, Mapping[str, Any]] | None = None,
        registry: ToolRegistry | None = None,
        executor: FixtureToolExecutor | None = None,
        reward_weights: RewardWeights | None = None,
        split_name: str = "unspecified",
        workspace_root: Path | str | None = None,
    ) -> None:
        if not tasks:
            raise ValueError("SandboxToolEnv requires at least one task")
        self.tasks = {task.task_id: task for task in tasks}
        self.task_metadata = {key: dict(value) for key, value in (task_metadata or {}).items()}
        self.registry = registry or default_tool_registry()
        self.executor = executor or FixtureToolExecutor(self.registry)
        self.reward_weights = reward_weights or RewardWeights()
        self.split_name = split_name
        self._owned_temp: TemporaryDirectory[str] | None = None
        if workspace_root is None:
            self._owned_temp = TemporaryDirectory(prefix="sandbox-rl-")
            self.workspace_root = Path(self._owned_temp.name)
        else:
            self.workspace_root = Path(workspace_root)
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._episode: EpisodeState | None = None
        self._sandbox: FileSystemSandbox | None = None
        self._before_state: Any = None
        self._logger: TraceLogger | None = None
        self.action_space = {
            "type": "tool_call or finish",
            "formats": ["dict", "<tool_call>{json}</tool_call>", "<finish>{json}</finish>"],
        }
        self.observation_space = {
            "type": "dict",
            "keys": [
                "task_id",
                "domain",
                "instruction",
                "available_tools",
                "visible_files",
                "turn_index",
                "max_turns",
                "history",
                "split",
            ],
        }

    def close(self) -> None:
        if self._owned_temp is not None:
            self._owned_temp.cleanup()
            self._owned_temp = None

    def __enter__(self) -> "SandboxToolEnv":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def reset(
        self,
        *,
        task_id: str | None = None,
        seed: int | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> tuple[JsonDict, JsonDict]:
        del seed, options
        if task_id is None:
            task_id = sorted(self.tasks)[0]
        try:
            task = self.tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task is not in this environment split: {task_id}") from exc
        workspace = self.workspace_root / "workspaces" / task.task_id
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        self._sandbox = self.executor.create_sandbox(task, workspace)
        self._before_state = self._sandbox.snapshot()
        # Traces live outside the task workspace so the state diff matches the eval runner.
        trace_path = self.workspace_root / "traces" / f"{task.task_id}.jsonl"
        if trace_path.exists():
            trace_path.unlink()
        self._logger = TraceLogger(
            trace_path,
            run_metadata={
                "run_id": f"rl-{task.task_id}",
                "task_id": task.task_id,
                "agent_id": "agentic-rl",
                "model": "policy",
                "prompt_version": "agentic-rl-v1",
                "tool_version": "tools-v1",
                "tool_execution_mode": "fixture_adapter",
                "sandbox_backend": self.executor.sandbox_backend_name,
                "task_version": "agentic-rl",
                "fixture_version": str(task.initial_state.get("fixture_version", "fixtures-v1")),
            },
        )
        episode = EpisodeState(task=task, metadata=dict(self.task_metadata.get(task.task_id, {})))
        episode.trace_events.append(self._logger.log_user_message(task.instruction))
        self._episode = episode
        observation = self._observation()
        findings = oracle_leak_findings(observation, task, episode.metadata)
        if findings:
            raise RuntimeError(f"initial observation leaks oracle fields for {task.task_id}: {findings}")
        return observation, {"task_id": task.task_id, "split": self.split_name}

    def step(self, action: str | Mapping[str, Any] | ParsedAction) -> tuple[JsonDict, float, bool, bool, JsonDict]:
        episode = self._require_episode()
        if episode.finished:
            raise RuntimeError("episode already finished; call reset")
        parsed = parse_action(action)
        episode.turn_index += 1
        logger = self._logger
        assert logger is not None
        if parsed.type == "invalid":
            episode.format_errors += 1
            episode.trace_events.append(logger.log_error("format_error", parsed.error or "invalid action"))
            episode.history.append({"type": "error", "message": parsed.error or "invalid action"})
        elif parsed.type == "tool_call":
            self._execute_tool(parsed)
        else:
            episode.final_answer = parsed.final_answer
            episode.reported_metrics = dict(parsed.reported_metrics)
            episode.trace_events.append(logger.log_agent_message(parsed.final_answer))
            return self._finish(terminated=True, truncated=False)

        if episode.turn_index >= episode.task.max_turns:
            return self._finish(terminated=False, truncated=True)
        return self._observation(), 0.0, False, False, self._progress_info()

    def force_terminate(self) -> tuple[JsonDict, float, bool, bool, JsonDict]:
        episode = self._require_episode()
        if episode.finished:
            raise RuntimeError("episode already finished")
        return self._finish(terminated=False, truncated=True)

    def render_prompt(self, observation: Mapping[str, Any] | None = None, *, mode: str = "tool") -> str:
        current = dict(observation or self._observation())
        if mode == "bare":
            return (
                "Answer the task. Do not invent tool results.\n"
                f"Task: {current['instruction']}\n"
            )
        if mode != "tool":
            raise ValueError("prompt mode must be 'tool' or 'bare'")
        return (
            "You are a tool-using agent inside a fixture sandbox. "
            "Reply with exactly one action and no other text.\n"
            "Tool call:\n<tool_call>\n"
            '{"name": "tool.name", "arguments": {}}\n</tool_call>\n'
            "Finish:\n<finish>\n"
            '{"final_answer": "...", "reported_metrics": {}}\n</finish>\n'
            f"Task: {current['instruction']}\n"
            f"Tools: {_stable_json(current['available_tools'])}\n"
            f"Visible files: {_stable_json(current['visible_files'])}\n"
            f"Turn: {current['turn_index']} of {current['max_turns']}\n"
            f"History: {_stable_json(current['history'])}\n"
            "Action:\n"
        )

    def _execute_tool(self, action: ParsedAction) -> None:
        episode = self._require_episode()
        logger = self._logger
        sandbox = self._sandbox
        assert logger is not None and sandbox is not None
        if action.name not in episode.task.available_tools:
            episode.invalid_tool_calls += 1
            message = f"tool is not available for this task: {action.name}"
            episode.execution_errors.append(message)
            episode.trace_events.append(logger.log_error("invalid_tool", message))
            episode.history.append({"type": "error", "message": message})
            return
        episode.trace_events.append(logger.log_tool_call(action.name, action.arguments))
        episode.history.append(
            {"type": "tool_call", "tool_name": action.name, "arguments": dict(action.arguments)}
        )
        try:
            result = self.executor.execute(action.name, action.arguments, sandbox)
        except (ToolExecutionError, ToolRegistryError, SchemaValidationError) as exc:
            episode.invalid_tool_calls += 1
            episode.execution_errors.append(str(exc))
            episode.trace_events.append(logger.log_error("tool_execution_error", str(exc)))
            episode.history.append({"type": "error", "tool_name": action.name, "message": str(exc)})
            return
        episode.trace_events.append(logger.log_tool_result(action.name, result))
        episode.history.append({"type": "tool_result", "tool_name": action.name, "result": dict(result)})

    def _finish(self, *, terminated: bool, truncated: bool) -> tuple[JsonDict, float, bool, bool, JsonDict]:
        episode = self._require_episode()
        sandbox = self._sandbox
        logger = self._logger
        assert sandbox is not None and logger is not None
        state_diff = self._before_state.diff(sandbox.snapshot()).to_dict()
        episode.trace_events.append(logger.log_state_diff(state_diff))
        timed_out = truncated
        if timed_out:
            episode.trace_events.append(
                logger.log_timeout("agent_run", timeout_seconds=episode.task.timeout_seconds)
            )
        plan_metrics = {
            "cost": 0.0,
            "latency_seconds": 0.0,
            "turns": episode.turn_index,
            "timed_out": timed_out,
        }
        breakdown = score_trajectory(
            episode.task,
            final_answer=episode.final_answer,
            reported_metrics=episode.reported_metrics,
            plan_metrics=plan_metrics,
            state_diff=state_diff,
            trace_events=episode.trace_events,
            registry=self.registry,
            format_errors=episode.format_errors,
            invalid_tool_calls=episode.invalid_tool_calls,
            execution_errors=episode.execution_errors,
            timed_out=timed_out,
            weights=self.reward_weights,
        )
        for result in breakdown.validator_results:
            episode.trace_events.append(logger.log_validator_result(result))
        episode.finished = True
        info = self._progress_info()
        info.update(
            {
                "reward": breakdown.to_dict(),
                "passed": breakdown.passed,
                "silent_failure": bool(breakdown.silent_failure),
                "incomplete": bool(breakdown.incomplete),
                "terminated": terminated,
                "truncated": truncated,
            }
        )
        return self._observation(), breakdown.total, terminated, truncated, info

    def _observation(self) -> JsonDict:
        episode = self._require_episode()
        task = episode.task
        return {
            "task_id": task.task_id,
            "domain": task.domain,
            "instruction": task.instruction,
            "available_tools": [_public_tool(self.registry, name) for name in task.available_tools],
            "visible_files": list(task.visible_files),
            "turn_index": episode.turn_index,
            "max_turns": task.max_turns,
            "history": [dict(item) for item in episode.history],
            "split": self.split_name,
        }

    def _progress_info(self) -> JsonDict:
        episode = self._require_episode()
        return {
            "task_id": episode.task.task_id,
            "split": self.split_name,
            "turn_index": episode.turn_index,
            "format_errors": episode.format_errors,
            "invalid_tool_calls": episode.invalid_tool_calls,
        }

    def _require_episode(self) -> EpisodeState:
        if self._episode is None:
            raise RuntimeError("call reset before step")
        return self._episode


def rollout_actions(env: SandboxToolEnv, task_id: str, actions: Sequence[str | Mapping[str, Any] | ParsedAction]) -> JsonDict:
    """Execute a scripted action list and return the terminal info."""

    env.reset(task_id=task_id)
    info: JsonDict = {}
    for action in actions:
        _observation, _reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            return info
    _observation, _reward, _terminated, _truncated, info = env.force_terminate()
    return info


def render_scripted_action(action: Mapping[str, Any] | ParsedAction) -> str:
    return render_action(action)


def _public_tool(registry: ToolRegistry, tool_name: str) -> JsonDict:
    spec = registry.get(tool_name)
    return {"name": spec.tool_name, "input_schema": spec.input_schema}


def _stable_json(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True)
