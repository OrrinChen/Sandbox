"""Deterministic agent baselines for local evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec


@dataclass(frozen=True)
class PlannedToolCall:
    tool_name: str
    arguments: JsonDict
    result: JsonDict


@dataclass(frozen=True)
class AgentRunPlan:
    agent_name: str
    final_answer: str
    tool_calls: list[PlannedToolCall]
    reported_metrics: JsonDict
    state_diff: JsonDict
    turns: int
    latency_seconds: float
    cost: float
    timed_out: bool = False


class AgentBaseline:
    """Base class for deterministic fixture-compatible agent baselines."""

    name = "agent_baseline"
    prompt_version = "baseline-v1"
    model = "deterministic-fixture-agent"

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        raise NotImplementedError


class OracleToolSelectionAgent(AgentBaseline):
    name = "oracle_tool_selection_agent"

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        return _make_plan(task, self.name, behavior="oracle")


class PlannerExecutorAgent(AgentBaseline):
    name = "planner_executor_agent"

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        return _make_plan(task, self.name, behavior="oracle", latency_seconds=0.03, turns_extra=1)


class ReActStyleAgent(AgentBaseline):
    name = "react_style_agent"

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        behavior = "unsupported_citation" if task.domain == "finance" else "oracle"
        return _make_plan(task, self.name, behavior=behavior, latency_seconds=0.04, turns_extra=2)


class SingleShotToolCallingAgent(AgentBaseline):
    name = "single_shot_tool_agent"

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        return _make_plan(task, self.name, behavior="single_shot_failure", latency_seconds=0.01)


def default_agent_baselines() -> list[AgentBaseline]:
    return [
        SingleShotToolCallingAgent(),
        ReActStyleAgent(),
        PlannerExecutorAgent(),
        OracleToolSelectionAgent(),
    ]


def agent_baseline_by_name(name: str) -> AgentBaseline:
    for baseline in default_agent_baselines():
        if baseline.name == name:
            return baseline
    raise ValueError(f"unknown agent baseline: {name}")


def _make_plan(
    task: TaskSpec,
    agent_name: str,
    behavior: str,
    latency_seconds: float = 0.02,
    turns_extra: int = 0,
) -> AgentRunPlan:
    expected_metrics = dict(task.hidden_expected_state.get("numeric", {}))
    expected_state = _expected_state_diff(task)
    expected_citations = list(task.hidden_expected_state.get("citations", []))
    tool_sequence = _tool_sequence_for_behavior(task, behavior)
    tool_calls = [_planned_tool_call(task, tool_name) for tool_name in tool_sequence]

    reported_metrics = dict(expected_metrics)
    state_diff = dict(expected_state)
    citations = list(expected_citations)
    if behavior == "unsupported_citation":
        citations = ["unsupported-source"]
    if behavior == "single_shot_failure":
        reported_metrics = _wrong_metrics(expected_metrics)
        state_diff = {"added": [], "modified": [], "deleted": []}
        if expected_citations:
            citations = ["unsupported-source"]

    final_answer = _final_answer(reported_metrics, citations)
    return AgentRunPlan(
        agent_name=agent_name,
        final_answer=final_answer,
        tool_calls=tool_calls,
        reported_metrics=reported_metrics,
        state_diff=state_diff,
        turns=max(1, len(tool_calls) + 1 + turns_extra),
        latency_seconds=latency_seconds,
        cost=0.0,
    )


def _tool_sequence_for_behavior(task: TaskSpec, behavior: str) -> list[str]:
    expected_sequence = list(task.hidden_expected_state.get("expected_tool_sequence", []))
    if behavior == "single_shot_failure" and len(expected_sequence) > 1:
        return expected_sequence[:1]
    return expected_sequence


def _planned_tool_call(task: TaskSpec, tool_name: str) -> PlannedToolCall:
    arguments = _arguments_for_tool(task, tool_name)
    return PlannedToolCall(tool_name=tool_name, arguments=arguments, result=_result_for_tool(task, tool_name, arguments))


def _arguments_for_tool(task: TaskSpec, tool_name: str) -> JsonDict:
    if tool_name == "financial_statement.lookup":
        if "aapl" in task.task_id:
            return {"ticker": "AAPL", "fiscal_year": 2023, "statement": "income"}
        if "msft" in task.task_id:
            return {"ticker": "MSFT", "fiscal_year": 2024, "statement": "segment"}
    if tool_name == "transcript.search":
        return {"ticker": "NVDA", "fiscal_period": "FY2024 Q4", "query": "data center revenue"}
    if tool_name == "csv.read":
        return {"path": task.visible_files[0]}
    if tool_name == "csv.group_metrics":
        return _csv_group_arguments(task)
    if tool_name == "code.patch":
        return {
            "path": "fixtures/code/discount.py",
            "replacements": [
                {
                    "old": "return sum(prices) - discount",
                    "new": "return sum(prices) * (1 - discount)",
                }
            ],
        }
    if tool_name == "python.unit_tests":
        return {"test_path": "fixtures/code/test_discount.py"}
    if tool_name == "optimization.solve_newsvendor":
        return {
            "path": "fixtures/optimization/newsvendor.json",
            "output_path": "newsvendor_solution.json",
        }
    return {}


def _csv_group_arguments(task: TaskSpec) -> JsonDict:
    if task.task_id == "data-sales-region-summary":
        return {
            "path": "fixtures/data/regional_sales.csv",
            "group_by": "region",
            "metric": "revenue",
            "output_path": "summary_by_region.csv",
        }
    if task.task_id == "data-churn-plan-rate":
        return {
            "path": "fixtures/data/customer_churn.csv",
            "group_by": "plan",
            "metric": "churn_rate",
            "output_path": "churn_by_plan.csv",
        }
    return {
        "path": "fixtures/data/inventory.csv",
        "group_by": "sku",
        "metric": "stockout_risk",
        "output_path": "stockout_report.csv",
    }


def _result_for_tool(task: TaskSpec, tool_name: str, arguments: Mapping[str, object]) -> JsonDict:
    if tool_name == "financial_statement.lookup":
        return {
            "ticker": arguments["ticker"],
            "fiscal_year": arguments["fiscal_year"],
            "statement": arguments["statement"],
            "source": _first_citation(task),
            "values": dict(task.hidden_expected_state.get("numeric", {})),
        }
    if tool_name == "transcript.search":
        return {
            "ticker": "NVDA",
            "fiscal_period": "FY2024 Q4",
            "source": _first_citation(task),
            "matches": [{"citation": _first_citation(task), "values": dict(task.hidden_expected_state.get("numeric", {}))}],
        }
    if tool_name == "csv.read":
        return {"path": arguments["path"], "columns": ["fixture"], "rows": 1}
    if tool_name == "csv.group_metrics":
        return {
            "rows": int(task.hidden_expected_state.get("numeric", {}).get("output_rows", 1)),
            "output_path": arguments["output_path"],
        }
    if tool_name == "code.patch":
        return {"path": arguments["path"], "replacements_applied": len(arguments["replacements"])}
    if tool_name == "python.unit_tests":
        return dict(task.hidden_expected_state.get("unit_tests", {"passed": True, "tests_run": 0, "failures": 0}))
    if tool_name == "optimization.solve_newsvendor":
        metrics = dict(task.hidden_expected_state.get("numeric", {}))
        return {
            "output_path": arguments["output_path"],
            "order_quantity": int(metrics.get("order_quantity", 0)),
            "service_level": float(metrics.get("service_level", 0.0)),
            "expected_cost": float(metrics.get("expected_cost", 0.0)),
            "source": "newsvendor-fixture-v1",
        }
    return {}


def _expected_state_diff(task: TaskSpec) -> JsonDict:
    return dict(task.hidden_expected_state.get("state_diff", {"added": [], "modified": [], "deleted": []}))


def _wrong_metrics(expected_metrics: Mapping[str, object]) -> JsonDict:
    wrong: JsonDict = {}
    for metric, value in expected_metrics.items():
        wrong[metric] = value + 1 if isinstance(value, (int, float)) and not isinstance(value, bool) else value
    return wrong


def _first_citation(task: TaskSpec) -> str:
    citations = task.hidden_expected_state.get("citations", [])
    return citations[0] if citations else "fixture-source"


def _final_answer(metrics: Mapping[str, object], citations: list[str]) -> str:
    metric_text = ", ".join(f"{name}={value}" for name, value in sorted(metrics.items())) or "no metrics"
    citation_text = " ".join(f"[{citation}]" for citation in citations)
    return f"{metric_text} {citation_text}".strip()
