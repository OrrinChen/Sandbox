"""LangGraph-style runner that maps graph transitions into harness traces."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Optional

from sandboxed_agent_eval_harness.agents import AgentBaseline, OracleToolSelectionAgent
from sandboxed_agent_eval_harness.evaluation.runner import _validate_plan
from sandboxed_agent_eval_harness.integrations.common import require_optional_dependency
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec, TraceEvent, ValidatorResult
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, ToolExecutionError, ToolRegistry, default_tool_registry
from sandboxed_agent_eval_harness.tracing import TraceLogger


@dataclass(frozen=True)
class LangGraphRunResult:
    run_id: str
    task_id: str
    backend: str
    trace_path: Path
    checkpoint_path: Path
    passed: bool
    validator_results: list[ValidatorResult]
    metrics: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "backend": self.backend,
            "trace_path": str(self.trace_path),
            "checkpoint_path": str(self.checkpoint_path),
            "passed": self.passed,
            "validator_results": [result.to_dict() for result in self.validator_results],
            "metrics": dict(self.metrics),
        }


class LangGraphRunner:
    """Run a fixture-backed planning graph while preserving deterministic harness evidence."""

    def __init__(
        self,
        *,
        registry: Optional[ToolRegistry] = None,
        executor: Optional[FixtureToolExecutor] = None,
        backend: str = "local",
    ) -> None:
        if backend not in {"local", "langgraph"}:
            raise ValueError("backend must be 'local' or 'langgraph'")
        self.registry = registry or default_tool_registry()
        self.executor = executor or FixtureToolExecutor(self.registry)
        self.backend = backend

    def run(
        self,
        *,
        task: TaskSpec,
        baseline: Optional[AgentBaseline] = None,
        output_dir: Path | str = "artifacts/integrations/langgraph",
        attempt_index: int = 0,
    ) -> LangGraphRunResult:
        if self.backend == "langgraph":
            require_optional_dependency("langgraph.graph")

        agent = baseline or OracleToolSelectionAgent()
        output_path = Path(output_dir)
        traces_path = output_path / "traces"
        workspaces_path = output_path / "workspaces"
        checkpoints_path = output_path / "checkpoints"
        traces_path.mkdir(parents=True, exist_ok=True)
        workspaces_path.mkdir(parents=True, exist_ok=True)
        checkpoints_path.mkdir(parents=True, exist_ok=True)

        run_id = f"langgraph-{agent.name}-{task.task_id}-{attempt_index:03d}"
        trace_path = traces_path / f"{run_id}.jsonl"
        checkpoint_path = checkpoints_path / f"{run_id}.json"
        if trace_path.exists():
            trace_path.unlink()

        logger = TraceLogger(
            trace_path,
            run_metadata={
                "run_id": run_id,
                "task_id": task.task_id,
                "agent_id": agent.name,
                "model": agent.model,
                "prompt_version": agent.prompt_version,
                "tool_version": "tools-v1",
                "tool_execution_mode": "fixture_adapter",
                "sandbox_backend": self.executor.sandbox_backend_name,
                "task_version": "optional-integrations-v1",
                "fixture_version": str(task.initial_state.get("fixture_version", "fixtures-v1")),
                "integration": "langgraph",
                "graph_backend": self.backend,
            },
        )

        trace_events: list[TraceEvent] = []
        checkpoints: list[JsonDict] = []
        plan = agent.run(task, attempt_index=attempt_index)
        self._log_node(logger, trace_events, checkpoints, "plan", {"tool_calls": len(plan.tool_calls)})
        trace_events.append(logger.log_user_message(task.instruction))
        trace_events.append(logger.log_agent_message(f"{agent.name} entered LangGraph runner for {task.task_id}."))

        sandbox = self.executor.create_sandbox(task, workspaces_path / run_id)
        before_state = sandbox.snapshot()
        execution_errors: list[str] = []
        for tool_call in plan.tool_calls:
            self._log_node(logger, trace_events, checkpoints, "tool_call", {"tool_name": tool_call.tool_name})
            trace_events.append(logger.log_tool_call(tool_call.tool_name, tool_call.arguments))
            try:
                result = self.executor.execute(tool_call.tool_name, tool_call.arguments, sandbox)
                self._log_node(logger, trace_events, checkpoints, "tool_result", {"tool_name": tool_call.tool_name})
                trace_events.append(logger.log_tool_result(tool_call.tool_name, result))
            except ToolExecutionError as exc:
                execution_errors.append(str(exc))
                trace_events.append(logger.log_error("tool_execution_error", str(exc)))

        state_diff = before_state.diff(sandbox.snapshot()).to_dict()
        trace_events.append(logger.log_state_diff(state_diff))
        plan_metrics = {
            "cost": plan.cost,
            "latency_seconds": plan.latency_seconds,
            "turns": plan.turns,
            "timed_out": plan.timed_out,
        }
        self._log_node(logger, trace_events, checkpoints, "validate", {"validators": list(task.validator_list)})
        validator_results = _validate_plan(
            task,
            plan.final_answer,
            plan.reported_metrics,
            plan_metrics,
            state_diff,
            trace_events,
            self.registry,
        )
        if execution_errors:
            validator_results.append(
                ValidatorResult(
                    validator_name="tool_execution",
                    passed=False,
                    failure_type="tool_execution_error",
                    message="One or more fixture-backed tool calls failed.",
                    details={"errors": execution_errors},
                )
            )
        for result in validator_results:
            trace_events.append(logger.log_validator_result(result))

        passed = not plan.timed_out and all(result.passed for result in validator_results)
        self._log_node(logger, trace_events, checkpoints, "retry_or_finish", {"passed": passed})
        metrics = {
            "final_answer_passed": bool(plan.final_answer_passed),
            "tool_calls": len(plan.tool_calls),
            "turns": plan.turns,
            "latency_seconds": plan.latency_seconds,
            "cost": plan.cost,
            "timed_out": plan.timed_out,
            "graph_backend": self.backend,
            "checkpoint_path": str(checkpoint_path),
        }
        checkpoint_payload = {
            "run_id": run_id,
            "task_id": task.task_id,
            "backend": self.backend,
            "checkpoints": checkpoints,
            "passed": passed,
        }
        checkpoint_path.write_text(json.dumps(checkpoint_payload, indent=2, sort_keys=True) + "\n")
        return LangGraphRunResult(
            run_id=run_id,
            task_id=task.task_id,
            backend=self.backend,
            trace_path=trace_path,
            checkpoint_path=checkpoint_path,
            passed=passed,
            validator_results=validator_results,
            metrics=metrics,
        )

    @staticmethod
    def _log_node(
        logger: TraceLogger,
        trace_events: list[TraceEvent],
        checkpoints: list[JsonDict],
        node: str,
        payload: JsonDict,
    ) -> None:
        event = logger.log_graph_node(node, payload)
        trace_events.append(event)
        checkpoints.append({"node": node, "sequence": event.sequence, "payload": dict(payload)})
