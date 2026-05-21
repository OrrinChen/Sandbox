"""Deterministic evaluation runner for fixture-backed agent baselines."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Optional, Sequence

from sandboxed_agent_eval_harness.agents import AgentBaseline, agent_baseline_by_name, default_agent_baselines
from sandboxed_agent_eval_harness.sandbox import sandbox_backend_by_name
from sandboxed_agent_eval_harness.schemas import JsonDict, RunResult, TaskSpec, TraceEvent, ValidatorResult
from sandboxed_agent_eval_harness.tasks import TaskSuite, default_task_suite, task_suite_by_name
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, ToolExecutionError, ToolRegistry, default_tool_registry
from sandboxed_agent_eval_harness.tracing import TraceLogger
from sandboxed_agent_eval_harness.validators import (
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


@dataclass(frozen=True)
class EvaluationRunRecord:
    run_id: str
    task_id: str
    baseline_name: str
    trial_index: int
    passed: bool
    trace_path: Path
    validator_results: list[ValidatorResult]
    metrics: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "baseline_name": self.baseline_name,
            "trial_index": self.trial_index,
            "passed": self.passed,
            "trace_path": str(self.trace_path),
            "validator_results": [result.to_dict() for result in self.validator_results],
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class EvaluationSummary:
    runs: list[EvaluationRunRecord]
    metrics: JsonDict
    baseline_metrics: dict[str, JsonDict]
    output_dir: Path

    def to_dict(self) -> JsonDict:
        return {
            "runs": [run.to_dict() for run in self.runs],
            "metrics": dict(self.metrics),
            "baseline_metrics": {name: dict(metrics) for name, metrics in self.baseline_metrics.items()},
            "output_dir": str(self.output_dir),
        }


def run_evaluation(
    suite: Optional[TaskSuite] = None,
    baselines: Optional[Sequence[AgentBaseline]] = None,
    trials_per_task: int = 1,
    output_dir: Path | str = "artifacts/eval_runs/smoke",
    registry: Optional[ToolRegistry] = None,
    executor: Optional[FixtureToolExecutor] = None,
    sandbox_backend_name: str = "workspace",
) -> EvaluationSummary:
    if trials_per_task <= 0:
        raise ValueError("trials_per_task must be positive")

    task_suite = suite or default_task_suite()
    agent_baselines = list(baselines or default_agent_baselines())
    tool_registry = registry or default_tool_registry()
    tool_executor = executor or FixtureToolExecutor(
        tool_registry,
        backend=sandbox_backend_by_name(sandbox_backend_name),
    )
    output_path = Path(output_dir)
    traces_path = output_path / "traces"
    workspaces_path = output_path / "workspaces"
    traces_path.mkdir(parents=True, exist_ok=True)
    workspaces_path.mkdir(parents=True, exist_ok=True)

    runs: list[EvaluationRunRecord] = []
    for baseline in agent_baselines:
        for task in task_suite.tasks:
            for trial_index in range(trials_per_task):
                runs.append(
                    _run_single_trial(
                        task,
                        baseline,
                        trial_index,
                        traces_path,
                        workspaces_path,
                        tool_registry,
                        tool_executor,
                        task_suite.version,
                    )
                )

    metrics = _aggregate_metrics(runs, trials_per_task)
    baseline_metrics = {
        baseline.name: _aggregate_metrics(
            [run for run in runs if run.baseline_name == baseline.name],
            trials_per_task,
        )
        for baseline in agent_baselines
    }
    summary = EvaluationSummary(runs=runs, metrics=metrics, baseline_metrics=baseline_metrics, output_dir=output_path)
    (output_path / "summary.json").write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run fixture-backed agent baseline evaluations.")
    parser.add_argument("--suite", default="smoke", choices=["smoke", "benchmark", "trading"])
    parser.add_argument("--baseline", action="append", help="Baseline name. Defaults to all baselines.")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--output-dir", default="artifacts/eval_runs/smoke")
    parser.add_argument("--sandbox-backend", default="workspace", choices=["workspace", "docker"])
    args = parser.parse_args(argv)

    baselines = [agent_baseline_by_name(name) for name in args.baseline] if args.baseline else default_agent_baselines()
    summary = run_evaluation(
        suite=task_suite_by_name(args.suite),
        baselines=baselines,
        trials_per_task=args.trials,
        output_dir=args.output_dir,
        sandbox_backend_name=args.sandbox_backend,
    )
    print(
        f"runs={summary.metrics['run_count']} "
        f"task_success_rate={summary.metrics['task_success_rate']:.3f} "
        f"pass_at_k={summary.metrics['pass_at_k']['value']:.3f} "
        f"sandbox_backend={args.sandbox_backend}"
    )
    return 0


def _run_single_trial(
    task: TaskSpec,
    baseline: AgentBaseline,
    trial_index: int,
    traces_path: Path,
    workspaces_path: Path,
    registry: ToolRegistry,
    executor: FixtureToolExecutor,
    task_version: str = "tasks-v1",
) -> EvaluationRunRecord:
    run_id = f"{baseline.name}-{task.task_id}-{trial_index:03d}"
    trace_path = traces_path / f"{run_id}.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    logger = TraceLogger(
        trace_path,
        run_metadata={
            "run_id": run_id,
            "task_id": task.task_id,
            "agent_id": baseline.name,
            "model": baseline.model,
            "prompt_version": baseline.prompt_version,
            "tool_version": "tools-v1",
            "tool_execution_mode": "fixture_adapter",
            "sandbox_backend": executor.sandbox_backend_name,
            "task_version": task_version,
            "fixture_version": str(task.initial_state.get("fixture_version", "fixtures-v1")),
        },
    )

    plan = baseline.run(task, attempt_index=trial_index)
    sandbox = executor.create_sandbox(task, workspaces_path / run_id)
    before_state = sandbox.snapshot()
    execution_errors: list[str] = []
    trace_events: list[TraceEvent] = [
        logger.log_user_message(task.instruction),
        logger.log_agent_message(f"{baseline.name} started task {task.task_id}."),
    ]
    for tool_call in plan.tool_calls:
        trace_events.append(logger.log_tool_call(tool_call.tool_name, tool_call.arguments))
        try:
            tool_result = executor.execute(tool_call.tool_name, tool_call.arguments, sandbox)
            trace_events.append(logger.log_tool_result(tool_call.tool_name, tool_result))
        except ToolExecutionError as exc:
            execution_errors.append(str(exc))
            trace_events.append(logger.log_error("tool_execution_error", str(exc)))
    state_diff = before_state.diff(sandbox.snapshot()).to_dict()
    trace_events.append(logger.log_state_diff(state_diff))
    if plan.timed_out:
        trace_events.append(logger.log_timeout("agent_run", timeout_seconds=task.timeout_seconds))

    plan_metrics = {
        "cost": plan.cost,
        "latency_seconds": plan.latency_seconds,
        "turns": plan.turns,
        "timed_out": plan.timed_out,
    }
    validator_results = _validate_plan(
        task,
        plan.final_answer,
        plan.reported_metrics,
        plan_metrics,
        state_diff,
        trace_events,
        registry,
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
    run_metrics = {
        "executed_tool_calls": len(plan.tool_calls) - len(execution_errors),
        "final_answer_passed": bool(plan.final_answer_passed),
        "latency_seconds": plan.latency_seconds,
        "tool_calls": len(plan.tool_calls),
        "tool_execution_mode": "fixture_adapter",
        "sandbox_backend": executor.sandbox_backend_name,
        "turns": plan.turns,
        "cost": plan.cost,
        "timed_out": plan.timed_out,
        "workspace_path": str(workspaces_path / run_id),
    }
    RunResult(
        run_id=run_id,
        task_id=task.task_id,
        agent_id=baseline.name,
        passed=passed,
        trace_events=trace_events,
        validator_results=validator_results,
        metrics=run_metrics,
        failure_labels=[result.failure_type for result in validator_results if result.failure_type],
    )
    return EvaluationRunRecord(
        run_id=run_id,
        task_id=task.task_id,
        baseline_name=baseline.name,
        trial_index=trial_index,
        passed=passed,
        trace_path=trace_path,
        validator_results=validator_results,
        metrics=run_metrics,
    )


def _validate_plan(
    task: TaskSpec,
    final_answer: str,
    reported_metrics: JsonDict,
    plan_metrics: JsonDict,
    state_diff: JsonDict,
    trace_events: Sequence[TraceEvent],
    registry: ToolRegistry,
) -> list[ValidatorResult]:
    results: list[ValidatorResult] = []
    for validator_name in task.validator_list:
        if validator_name == "schema":
            results.append(validate_schema("task", task.to_dict()))
        elif validator_name == "tool_sequence":
            results.append(
                validate_tool_sequence(
                    trace_events,
                    expected_sequence=task.hidden_expected_state.get("expected_tool_sequence", []),
                )
            )
        elif validator_name == "argument":
            results.append(validate_tool_arguments(trace_events, registry))
        elif validator_name == "state":
            results.append(validate_state(state_diff, task.hidden_expected_state.get("state_diff", {})))
        elif validator_name == "numeric":
            results.append(_validate_numeric_metrics(task, reported_metrics))
        elif validator_name == "citation":
            expected_citations = task.hidden_expected_state.get("citations", [])
            results.append(
                validate_citations(
                    final_answer,
                    supported_citations=expected_citations,
                    required_citations=expected_citations,
                )
            )
        elif validator_name == "constraint":
            results.append(validate_constraints(reported_metrics, task.hidden_expected_state.get("constraints", [])))
        elif validator_name == "unit_test":
            results.append(validate_unit_tests(trace_events, expected=task.hidden_expected_state.get("unit_tests", {})))
        elif validator_name == "policy":
            policy = task.hidden_expected_state.get("policy", {})
            results.append(
                validate_policy(
                    final_answer,
                    required_terms=policy.get("required_terms", []),
                    forbidden_terms=policy.get("forbidden_terms", []),
                )
            )
        elif validator_name == "cost_latency":
            results.append(
                validate_cost_latency(
                    plan_metrics,
                    max_cost=task.max_cost,
                    max_latency_seconds=task.timeout_seconds,
                    max_turns=task.max_turns,
                )
            )
        elif validator_name == "lookahead_validator":
            results.append(validate_lookahead(trace_events))
        elif validator_name == "pnl_consistency_validator":
            results.append(validate_pnl_consistency(trace_events, reported_metrics))
        elif validator_name == "cost_inclusion_validator":
            results.append(validate_cost_inclusion(trace_events))
        elif validator_name == "risk_limit_validator":
            results.append(validate_risk_limits(trace_events))
        elif validator_name == "artifact_grounding_validator":
            results.append(
                validate_artifact_grounding(
                    final_answer,
                    trace_events,
                    required_sources=task.hidden_expected_state.get("required_sources", []),
                )
            )
    return results


def _validate_numeric_metrics(task: TaskSpec, reported_metrics: JsonDict) -> ValidatorResult:
    expected_metrics = task.hidden_expected_state.get("numeric", {})
    details = {"metrics": {}}
    for metric, expected in expected_metrics.items():
        actual = reported_metrics.get(metric)
        result = validate_numeric(metric, actual=actual, expected=expected)
        details["metrics"][metric] = result.details
        if not result.passed:
            return ValidatorResult(
                validator_name="numeric",
                passed=False,
                failure_type=result.failure_type,
                message=result.message,
                details=result.details,
            )
    return ValidatorResult(
        validator_name="numeric",
        passed=True,
        message="All numeric metrics matched expected values.",
        details=details,
    )


def _aggregate_metrics(runs: Sequence[EvaluationRunRecord], trials_per_task: int) -> JsonDict:
    if not runs:
        return {}
    passed_count = sum(1 for run in runs if run.passed)
    validator_metrics = _per_validator_metrics(runs)
    failure_taxonomy = Counter(
        result.failure_type
        for run in runs
        for result in run.validator_results
        if not result.passed and result.failure_type
    )
    return {
        "run_count": len(runs),
        "passed_count": passed_count,
        "task_success_rate": passed_count / len(runs),
        "pass_at_k": _pass_at_k(runs, trials_per_task),
        "per_validator_metrics": validator_metrics,
        "failure_taxonomy": dict(sorted(failure_taxonomy.items())),
        "tool_selection_accuracy": _validator_pass_rate(validator_metrics, "tool_sequence"),
        "argument_correctness": _validator_pass_rate(validator_metrics, "argument"),
        "state_correctness": _validator_pass_rate(validator_metrics, "state"),
        "numeric_correctness": _validator_pass_rate(validator_metrics, "numeric"),
        "citation_correctness": _validator_pass_rate(validator_metrics, "citation"),
        "constraint_correctness": _validator_pass_rate(validator_metrics, "constraint"),
        "unit_test_correctness": _validator_pass_rate(validator_metrics, "unit_test"),
        "policy_correctness": _validator_pass_rate(validator_metrics, "policy"),
        "cost_latency_correctness": _validator_pass_rate(validator_metrics, "cost_latency"),
        "lookahead_correctness": _validator_pass_rate(validator_metrics, "lookahead_validator"),
        "pnl_consistency_correctness": _validator_pass_rate(validator_metrics, "pnl_consistency_validator"),
        "cost_inclusion_correctness": _validator_pass_rate(validator_metrics, "cost_inclusion_validator"),
        "risk_limit_correctness": _validator_pass_rate(validator_metrics, "risk_limit_validator"),
        "artifact_grounding_correctness": _validator_pass_rate(validator_metrics, "artifact_grounding_validator"),
        "average_turns": sum(run.metrics["turns"] for run in runs) / len(runs),
        "average_latency_seconds": sum(run.metrics["latency_seconds"] for run in runs) / len(runs),
        "average_cost": sum(run.metrics["cost"] for run in runs) / len(runs),
        "timeout_rate": sum(1 for run in runs if run.metrics["timed_out"]) / len(runs),
    }


def _per_validator_metrics(runs: Sequence[EvaluationRunRecord]) -> JsonDict:
    totals: dict[str, Counter] = defaultdict(Counter)
    for run in runs:
        for result in run.validator_results:
            totals[result.validator_name]["total"] += 1
            totals[result.validator_name]["passed" if result.passed else "failed"] += 1
    return {
        name: {
            "total": counts["total"],
            "passed": counts["passed"],
            "failed": counts["failed"],
            "pass_rate": counts["passed"] / counts["total"] if counts["total"] else 1.0,
        }
        for name, counts in sorted(totals.items())
    }


def _validator_pass_rate(validator_metrics: JsonDict, validator_name: str) -> float:
    metrics = validator_metrics.get(validator_name)
    return metrics["pass_rate"] if metrics else 1.0


def _pass_at_k(runs: Sequence[EvaluationRunRecord], trials_per_task: int) -> JsonDict:
    grouped: dict[tuple[str, str], list[EvaluationRunRecord]] = defaultdict(list)
    for run in runs:
        grouped[(run.baseline_name, run.task_id)].append(run)
    successful_groups = sum(1 for group in grouped.values() if any(run.passed for run in group))
    return {
        "k": trials_per_task,
        "value": successful_groups / len(grouped) if grouped else 0.0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
