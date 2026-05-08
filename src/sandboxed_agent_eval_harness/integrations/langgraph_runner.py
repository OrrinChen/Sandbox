"""Optional LangGraph workflow runner that preserves harness evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, TypedDict

from sandboxed_agent_eval_harness.agents import AgentBaseline, AgentRunPlan, OracleToolSelectionAgent
from sandboxed_agent_eval_harness.evaluation.runner import _validate_plan
from sandboxed_agent_eval_harness.integrations.common import require_optional_dependency
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec, TraceEvent, ValidatorResult
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, ToolExecutionError, ToolRegistry, default_tool_registry
from sandboxed_agent_eval_harness.tracing import TraceLogger


class HarnessGraphState(TypedDict, total=False):
    task: JsonDict
    run_id: str
    task_id: str
    baseline_name: str
    attempt_index: int
    plan: JsonDict
    tool_calls: list[JsonDict]
    tool_results: list[JsonDict]
    state_diff: JsonDict
    validator_results: list[JsonDict]
    metrics: JsonDict
    execution_errors: list[str]
    retry_count: int
    passed: bool
    trace_path: str
    checkpoint_path: str


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


def build_langgraph_workflow(
    node_functions: Mapping[str, Callable[[HarnessGraphState], HarnessGraphState]],
    *,
    checkpointer: Any,
    graph_module: Optional[Any] = None,
) -> Any:
    """Build and compile the optional LangGraph StateGraph workflow."""

    graph_api = graph_module or require_optional_dependency("langgraph.graph")
    builder = graph_api.StateGraph(HarnessGraphState)
    for node_name in ["plan", "tool_call", "tool_result", "validate", "retry_or_finish"]:
        builder.add_node(node_name, node_functions[node_name])
    builder.add_edge(graph_api.START, "plan")
    builder.add_edge("plan", "tool_call")
    builder.add_edge("tool_call", "tool_result")
    builder.add_edge("tool_result", "validate")
    builder.add_edge("validate", "retry_or_finish")
    builder.add_conditional_edges("retry_or_finish", _route_after_retry, {"finish": graph_api.END})
    return builder.compile(checkpointer=checkpointer)


class LangGraphRunner:
    """Run local graph-style or compiled LangGraph workflows without changing harness semantics."""

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
        agent = baseline or OracleToolSelectionAgent()
        context = self._prepare_context(task, agent, output_dir, attempt_index, stategraph_compiled=self.backend == "langgraph")
        if self.backend == "local":
            return self._run_local(task, agent, context, attempt_index)
        return self._run_compiled_langgraph(task, agent, context, attempt_index)

    def _run_local(
        self,
        task: TaskSpec,
        agent: AgentBaseline,
        context: "_RunContext",
        attempt_index: int,
    ) -> LangGraphRunResult:
        plan = agent.run(task, attempt_index=attempt_index)
        self._record_plan(context, task, agent, plan, integration_name="langgraph_style")
        execution_errors = self._record_tool_calls_and_results(context, plan)
        state_diff = context.before_state.diff(context.sandbox.snapshot()).to_dict()
        context.trace_events.append(context.logger.log_state_diff(state_diff))
        validator_results = self._record_validation(context, task, plan, state_diff, execution_errors)
        passed = self._passed(plan, validator_results)
        self._log_node(context, "retry_or_finish", {"passed": passed})
        metrics = self._metrics(plan, context, stategraph_compiled=False, state_history_count=len(context.checkpoints))
        self._write_checkpoint(context, passed=passed, metrics=metrics)
        return LangGraphRunResult(
            run_id=context.run_id,
            task_id=task.task_id,
            backend="local",
            trace_path=context.trace_path,
            checkpoint_path=context.checkpoint_path,
            passed=passed,
            validator_results=validator_results,
            metrics=metrics,
        )

    def _run_compiled_langgraph(
        self,
        task: TaskSpec,
        agent: AgentBaseline,
        context: "_RunContext",
        attempt_index: int,
    ) -> LangGraphRunResult:
        graph_module = require_optional_dependency("langgraph.graph")
        memory_module = require_optional_dependency("langgraph.checkpoint.memory")
        checkpointer = memory_module.InMemorySaver()
        runtime: dict[str, Any] = {}

        def plan_node(state: HarnessGraphState) -> HarnessGraphState:
            plan = agent.run(task, attempt_index=attempt_index)
            runtime["plan"] = plan
            self._record_plan(context, task, agent, plan, integration_name="langgraph")
            return {
                "plan": _plan_to_dict(plan),
                "tool_calls": [_tool_call_to_dict(tool_call) for tool_call in plan.tool_calls],
                "metrics": _plan_metrics(plan),
            }

        def tool_call_node(state: HarnessGraphState) -> HarnessGraphState:
            plan = runtime["plan"]
            for tool_call in plan.tool_calls:
                self._log_node(context, "tool_call", {"tool_name": tool_call.tool_name})
                context.trace_events.append(context.logger.log_tool_call(tool_call.tool_name, tool_call.arguments))
            return {}

        def tool_result_node(state: HarnessGraphState) -> HarnessGraphState:
            plan = runtime["plan"]
            execution_errors = self._record_tool_results(context, plan)
            state_diff = context.before_state.diff(context.sandbox.snapshot()).to_dict()
            context.trace_events.append(context.logger.log_state_diff(state_diff))
            runtime["execution_errors"] = execution_errors
            runtime["state_diff"] = state_diff
            return {
                "tool_results": list(runtime.get("tool_results", [])),
                "execution_errors": execution_errors,
                "state_diff": state_diff,
            }

        def validate_node(state: HarnessGraphState) -> HarnessGraphState:
            plan = runtime["plan"]
            validator_results = self._record_validation(
                context,
                task,
                plan,
                dict(runtime.get("state_diff", {})),
                list(runtime.get("execution_errors", [])),
            )
            runtime["validator_results"] = validator_results
            passed = self._passed(plan, validator_results)
            runtime["passed"] = passed
            return {
                "validator_results": [result.to_dict() for result in validator_results],
                "passed": passed,
            }

        def retry_or_finish_node(state: HarnessGraphState) -> HarnessGraphState:
            passed = bool(runtime.get("passed"))
            self._log_node(context, "retry_or_finish", {"passed": passed})
            return {"retry_count": 0, "passed": passed}

        graph = build_langgraph_workflow(
            {
                "plan": plan_node,
                "tool_call": tool_call_node,
                "tool_result": tool_result_node,
                "validate": validate_node,
                "retry_or_finish": retry_or_finish_node,
            },
            checkpointer=checkpointer,
            graph_module=graph_module,
        )
        config = {"configurable": {"thread_id": context.run_id}}
        final_state = graph.invoke(
            {
                "task": task.to_dict(),
                "run_id": context.run_id,
                "task_id": task.task_id,
                "baseline_name": agent.name,
                "attempt_index": attempt_index,
                "retry_count": 0,
                "trace_path": str(context.trace_path),
                "checkpoint_path": str(context.checkpoint_path),
            },
            config=config,
        )
        history_count = _state_history_count(graph, config)
        plan = runtime["plan"]
        validator_results = list(runtime.get("validator_results", []))
        passed = bool(final_state.get("passed", runtime.get("passed", False)))
        metrics = self._metrics(plan, context, stategraph_compiled=True, state_history_count=history_count)
        self._write_checkpoint(context, passed=passed, metrics=metrics)
        return LangGraphRunResult(
            run_id=context.run_id,
            task_id=task.task_id,
            backend="langgraph",
            trace_path=context.trace_path,
            checkpoint_path=context.checkpoint_path,
            passed=passed,
            validator_results=validator_results,
            metrics=metrics,
        )

    def _prepare_context(
        self,
        task: TaskSpec,
        agent: AgentBaseline,
        output_dir: Path | str,
        attempt_index: int,
        *,
        stategraph_compiled: bool,
    ) -> "_RunContext":
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

        integration_name = "langgraph" if stategraph_compiled else "langgraph_style"
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
                "integration": integration_name,
                "graph_backend": self.backend,
                "stategraph_compiled": stategraph_compiled,
                "thread_id": run_id,
            },
        )
        sandbox = self.executor.create_sandbox(task, workspaces_path / run_id)
        return _RunContext(
            run_id=run_id,
            trace_path=trace_path,
            checkpoint_path=checkpoint_path,
            logger=logger,
            sandbox=sandbox,
            before_state=sandbox.snapshot(),
            trace_events=[],
            checkpoints=[],
        )

    def _record_plan(
        self,
        context: "_RunContext",
        task: TaskSpec,
        agent: AgentBaseline,
        plan: AgentRunPlan,
        *,
        integration_name: str,
    ) -> None:
        self._log_node(context, "plan", {"tool_calls": len(plan.tool_calls)})
        context.trace_events.append(context.logger.log_user_message(task.instruction))
        context.trace_events.append(
            context.logger.log_agent_message(f"{agent.name} entered {integration_name} runner for {task.task_id}.")
        )

    def _record_tool_calls_and_results(self, context: "_RunContext", plan: AgentRunPlan) -> list[str]:
        execution_errors: list[str] = []
        for tool_call in plan.tool_calls:
            self._log_node(context, "tool_call", {"tool_name": tool_call.tool_name})
            context.trace_events.append(context.logger.log_tool_call(tool_call.tool_name, tool_call.arguments))
            execution_errors.extend(self._record_single_tool_result(context, tool_call))
        return execution_errors

    def _record_tool_results(self, context: "_RunContext", plan: AgentRunPlan) -> list[str]:
        execution_errors: list[str] = []
        for tool_call in plan.tool_calls:
            execution_errors.extend(self._record_single_tool_result(context, tool_call))
        return execution_errors

    def _record_single_tool_result(self, context: "_RunContext", tool_call: Any) -> list[str]:
        try:
            result = self.executor.execute(tool_call.tool_name, tool_call.arguments, context.sandbox)
            self._log_node(context, "tool_result", {"tool_name": tool_call.tool_name})
            context.trace_events.append(context.logger.log_tool_result(tool_call.tool_name, result))
            return []
        except ToolExecutionError as exc:
            context.trace_events.append(context.logger.log_error("tool_execution_error", str(exc)))
            return [str(exc)]

    def _record_validation(
        self,
        context: "_RunContext",
        task: TaskSpec,
        plan: AgentRunPlan,
        state_diff: JsonDict,
        execution_errors: list[str],
    ) -> list[ValidatorResult]:
        self._log_node(context, "validate", {"validators": list(task.validator_list)})
        validator_results = _validate_plan(
            task,
            plan.final_answer,
            plan.reported_metrics,
            _plan_metrics(plan),
            state_diff,
            context.trace_events,
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
            context.trace_events.append(context.logger.log_validator_result(result))
        return validator_results

    @staticmethod
    def _passed(plan: AgentRunPlan, validator_results: list[ValidatorResult]) -> bool:
        return not plan.timed_out and all(result.passed for result in validator_results)

    def _metrics(
        self,
        plan: AgentRunPlan,
        context: "_RunContext",
        *,
        stategraph_compiled: bool,
        state_history_count: int,
    ) -> JsonDict:
        return {
            "final_answer_passed": bool(plan.final_answer_passed),
            "tool_calls": len(plan.tool_calls),
            "turns": plan.turns,
            "latency_seconds": plan.latency_seconds,
            "cost": plan.cost,
            "timed_out": plan.timed_out,
            "graph_backend": self.backend,
            "stategraph_compiled": stategraph_compiled,
            "thread_id": context.run_id,
            "state_history_count": state_history_count,
            "checkpoint_path": str(context.checkpoint_path),
        }

    def _write_checkpoint(self, context: "_RunContext", *, passed: bool, metrics: JsonDict) -> None:
        context.checkpoint_path.write_text(
            json.dumps(
                {
                    "run_id": context.run_id,
                    "task_id": context.logger.run_metadata.get("task_id"),
                    "backend": self.backend,
                    "stategraph_compiled": bool(metrics["stategraph_compiled"]),
                    "thread_id": context.run_id,
                    "state_history_count": int(metrics["state_history_count"]),
                    "checkpoints": context.checkpoints,
                    "passed": passed,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    @staticmethod
    def _log_node(context: "_RunContext", node: str, payload: JsonDict) -> None:
        event = context.logger.log_graph_node(node, payload)
        context.trace_events.append(event)
        context.checkpoints.append({"node": node, "sequence": event.sequence, "payload": dict(payload)})


@dataclass
class _RunContext:
    run_id: str
    trace_path: Path
    checkpoint_path: Path
    logger: TraceLogger
    sandbox: Any
    before_state: Any
    trace_events: list[TraceEvent]
    checkpoints: list[JsonDict]


def _route_after_retry(state: HarnessGraphState) -> str:
    return "finish"


def _plan_metrics(plan: AgentRunPlan) -> JsonDict:
    return {
        "cost": plan.cost,
        "latency_seconds": plan.latency_seconds,
        "turns": plan.turns,
        "timed_out": plan.timed_out,
    }


def _plan_to_dict(plan: AgentRunPlan) -> JsonDict:
    return {
        "agent_name": plan.agent_name,
        "final_answer": plan.final_answer,
        "reported_metrics": dict(plan.reported_metrics),
        "state_diff": dict(plan.state_diff),
        "turns": plan.turns,
        "latency_seconds": plan.latency_seconds,
        "cost": plan.cost,
        "timed_out": plan.timed_out,
        "final_answer_passed": plan.final_answer_passed,
    }


def _tool_call_to_dict(tool_call: Any) -> JsonDict:
    return {
        "tool_name": tool_call.tool_name,
        "arguments": dict(tool_call.arguments),
        "planned_result": dict(tool_call.result),
    }


def _state_history_count(graph: Any, config: Mapping[str, Any]) -> int:
    get_history = getattr(graph, "get_state_history", None)
    if get_history is None:
        return 0
    try:
        return len(list(get_history(config)))
    except TypeError:
        return 0
