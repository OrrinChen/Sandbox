"""Report and regression views for evaluation summaries."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import TaskSuite, default_task_suite
from sandboxed_agent_eval_harness.tracing import TraceReplay, TraceReplayError
from sandboxed_agent_eval_harness.evaluation.gates import replay_divergence_summary_from_results


VERSION_FIELDS = ("task_version", "tool_version", "prompt_version", "model", "fixture_version")
ROOT_CAUSE_CATEGORIES = [
    "TOOL_SELECTION_ERROR",
    "TOOL_ARGUMENT_ERROR",
    "TOOL_RESULT_MISUSE",
    "STATE_MUTATION_ERROR",
    "NUMERIC_MISMATCH",
    "CITATION_UNSUPPORTED",
    "CONSTRAINT_VIOLATION",
    "TRACE_REPLAY_DIVERGENCE",
    "TIMEOUT",
    "COST_LIMIT_EXCEEDED",
    "FINAL_ANSWER_OVERCLAIM",
]
_ROOT_CAUSE_BY_FAILURE_TYPE = {
    "tool_sequence_mismatch": "TOOL_SELECTION_ERROR",
    "unexpected_tool": "TOOL_SELECTION_ERROR",
    "missing_required_tool": "TOOL_SELECTION_ERROR",
    "invalid_tool_arguments": "TOOL_ARGUMENT_ERROR",
    "invalid_tool_call_payload": "TOOL_ARGUMENT_ERROR",
    "schema_mismatch": "TOOL_ARGUMENT_ERROR",
    "tool_execution_error": "TOOL_RESULT_MISUSE",
    "unit_tests_missing": "TOOL_RESULT_MISUSE",
    "unit_tests_failed": "TOOL_RESULT_MISUSE",
    "state_mismatch": "STATE_MUTATION_ERROR",
    "numeric_mismatch": "NUMERIC_MISMATCH",
    "invalid_numeric_value": "NUMERIC_MISMATCH",
    "invalid_numeric_tolerance": "NUMERIC_MISMATCH",
    "unsupported_citation": "CITATION_UNSUPPORTED",
    "missing_citation": "CITATION_UNSUPPORTED",
    "constraint_violation": "CONSTRAINT_VIOLATION",
    "invalid_constraint": "CONSTRAINT_VIOLATION",
    "policy_violation": "CONSTRAINT_VIOLATION",
    "tool_result_mismatch": "TRACE_REPLAY_DIVERGENCE",
    "state_diff_mismatch": "TRACE_REPLAY_DIVERGENCE",
    "missing_recorded_tool_result": "TRACE_REPLAY_DIVERGENCE",
    "replay_execution_error": "TRACE_REPLAY_DIVERGENCE",
    "timeout": "TIMEOUT",
    "cost_limit_exceeded": "COST_LIMIT_EXCEEDED",
    "final_answer_overclaim": "FINAL_ANSWER_OVERCLAIM",
}


@dataclass(frozen=True)
class EvaluationReport:
    summary: JsonDict
    executive_summary: str
    domain_success: JsonDict
    final_answer_vs_validator: JsonDict
    failure_type_distribution: JsonDict
    root_cause_summary: JsonDict
    failure_insights: list[JsonDict]
    pass_at_k_curve: list[JsonDict]
    cost_latency_summary: JsonDict
    replay_divergence_summary: JsonDict
    worst_traces: list[JsonDict]
    version_matrix: JsonDict
    regression_comparison: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "summary": dict(self.summary),
            "executive_summary": self.executive_summary,
            "domain_success": dict(self.domain_success),
            "final_answer_vs_validator": dict(self.final_answer_vs_validator),
            "failure_type_distribution": dict(self.failure_type_distribution),
            "root_cause_summary": dict(self.root_cause_summary),
            "failure_insights": [dict(item) for item in self.failure_insights],
            "pass_at_k_curve": [dict(item) for item in self.pass_at_k_curve],
            "cost_latency_summary": dict(self.cost_latency_summary),
            "replay_divergence_summary": dict(self.replay_divergence_summary),
            "worst_traces": [dict(item) for item in self.worst_traces],
            "version_matrix": dict(self.version_matrix),
            "regression_comparison": dict(self.regression_comparison),
        }


def build_evaluation_report(
    summary: Any,
    suite: Optional[TaskSuite] = None,
    previous_summary: Optional[Any] = None,
    replay_results: Optional[Sequence[Any]] = None,
    worst_trace_limit: int = 10,
) -> EvaluationReport:
    summary_dict = _summary_to_dict(summary)
    previous_dict = _summary_to_dict(previous_summary) if previous_summary is not None else None
    task_suite = suite or default_task_suite()
    task_domains = {task.task_id: task.domain for task in task_suite.tasks}
    runs = _runs(summary_dict)

    domain_success = _domain_success(runs, task_domains)
    final_answer_vs_validator = _final_answer_vs_validator(runs)
    failure_type_distribution = _failure_type_distribution(runs)
    worst_traces = _worst_traces(runs, worst_trace_limit)
    root_cause_summary = _root_cause_summary(
        runs,
        task_domains=task_domains,
        final_answer_vs_validator=final_answer_vs_validator,
        replay_results=replay_results,
        trace_limit=worst_trace_limit,
    )
    version_matrix = _version_matrix(runs)
    regression_comparison = _regression_comparison(summary_dict, previous_dict)

    return EvaluationReport(
        summary=_report_summary(summary_dict),
        executive_summary=root_cause_summary["executive_summary"],
        domain_success=domain_success,
        final_answer_vs_validator=final_answer_vs_validator,
        failure_type_distribution=failure_type_distribution,
        root_cause_summary=root_cause_summary,
        failure_insights=_failure_insights(runs),
        pass_at_k_curve=_pass_at_k_curve(runs),
        cost_latency_summary=_cost_latency_summary(runs),
        replay_divergence_summary=_replay_divergence_summary(replay_results),
        worst_traces=worst_traces,
        version_matrix=version_matrix,
        regression_comparison=regression_comparison,
    )


def write_evaluation_report(report: EvaluationReport, output_dir: Path | str) -> JsonDict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_json_path = output_path / "report.json"
    report_markdown_path = output_path / "report.md"
    report_json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
    report_markdown_path.write_text(_render_markdown(report) + "\n")
    return {
        "json_path": str(report_json_path),
        "markdown_path": str(report_markdown_path),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an evaluation report from a summary artifact.")
    parser.add_argument("--summary", required=True, help="Path to a current summary.json artifact.")
    parser.add_argument("--previous-summary", help="Optional previous summary.json artifact for regression comparison.")
    parser.add_argument("--replay-result", action="append", default=[], help="Optional replay execution result JSON.")
    parser.add_argument("--output-dir", default="artifacts/reports/latest")
    parser.add_argument("--worst-trace-limit", type=int, default=10)
    args = parser.parse_args(argv)

    summary = _load_json(args.summary)
    previous = _load_json(args.previous_summary) if args.previous_summary else None
    replay_results = [_load_json(path) for path in args.replay_result]
    report = build_evaluation_report(
        summary,
        suite=default_task_suite(),
        previous_summary=previous,
        replay_results=replay_results if replay_results else None,
        worst_trace_limit=args.worst_trace_limit,
    )
    paths = write_evaluation_report(report, args.output_dir)
    print(
        f"report={paths['json_path']} "
        f"domains={len(report.domain_success)} "
        f"worst_traces={len(report.worst_traces)}"
    )
    return 0


def _summary_to_dict(summary: Any) -> JsonDict:
    if hasattr(summary, "to_dict"):
        return summary.to_dict()
    if isinstance(summary, Mapping):
        return dict(summary)
    raise TypeError("summary must be an EvaluationSummary or mapping")


def _load_json(path: Path | str) -> JsonDict:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"summary artifact must contain a JSON object: {path}")
    return payload


def _runs(summary: Mapping[str, Any]) -> list[JsonDict]:
    raw_runs = summary.get("runs", [])
    if not isinstance(raw_runs, list):
        raise ValueError("summary runs must be a list")
    return [dict(run) for run in raw_runs]


def _report_summary(summary: Mapping[str, Any]) -> JsonDict:
    metrics = dict(summary.get("metrics", {}))
    return {
        "run_count": metrics.get("run_count", len(_runs(summary))),
        "task_success_rate": metrics.get("task_success_rate", 0.0),
        "pass_at_k": metrics.get("pass_at_k", {}),
        "output_dir": summary.get("output_dir"),
    }


def _domain_success(runs: Sequence[Mapping[str, Any]], task_domains: Mapping[str, str]) -> JsonDict:
    totals: dict[str, Counter] = defaultdict(Counter)
    for run in runs:
        domain = task_domains.get(str(run.get("task_id")), "unknown")
        totals[domain]["run_count"] += 1
        if run.get("passed") is True:
            totals[domain]["passed_count"] += 1
    return {
        domain: {
            "run_count": counts["run_count"],
            "passed_count": counts["passed_count"],
            "success_rate": _safe_rate(counts["passed_count"], counts["run_count"]),
        }
        for domain, counts in sorted(totals.items())
    }


def _final_answer_vs_validator(runs: Sequence[Mapping[str, Any]]) -> JsonDict:
    run_count = len(runs)
    final_answer_passed = sum(1 for run in runs if _final_answer_passed(run))
    validator_passed = sum(1 for run in runs if run.get("passed") is True)
    silent_failures = sum(1 for run in runs if _final_answer_passed(run) and run.get("passed") is not True)
    final_answer_pass_rate = _safe_rate(final_answer_passed, run_count)
    validator_pass_rate = _safe_rate(validator_passed, run_count)
    return {
        "run_count": run_count,
        "final_answer_passed": final_answer_passed,
        "validator_passed": validator_passed,
        "silent_failure_count": silent_failures,
        "silent_failure_rate": _safe_rate(silent_failures, run_count),
        "answer_overclaim_rate": _safe_rate(silent_failures, final_answer_passed),
        "final_answer_pass_rate": final_answer_pass_rate,
        "validator_pass_rate": validator_pass_rate,
        "validator_gap": final_answer_pass_rate - validator_pass_rate,
    }


def _final_answer_passed(run: Mapping[str, Any]) -> bool:
    metrics = run.get("metrics", {})
    if isinstance(metrics, Mapping) and "final_answer_passed" in metrics:
        return metrics["final_answer_passed"] is True
    return True


def _failure_type_distribution(runs: Sequence[Mapping[str, Any]]) -> JsonDict:
    failures = Counter(
        result["failure_type"]
        for run in runs
        for result in _validator_results(run)
        if result.get("passed") is not True and result.get("failure_type")
    )
    return dict(sorted(failures.items()))


def _failure_insights(runs: Sequence[Mapping[str, Any]]) -> list[JsonDict]:
    by_failure: dict[str, JsonDict] = {}
    for run in runs:
        for failure_type in _failure_types(run):
            insight = by_failure.setdefault(
                failure_type,
                {
                    "failure_type": failure_type,
                    "count": 0,
                    "affected_baselines": set(),
                    "affected_tasks": set(),
                    "example_trace_path": run.get("trace_path"),
                },
            )
            insight["count"] += 1
            insight["affected_baselines"].add(run.get("baseline_name"))
            insight["affected_tasks"].add(run.get("task_id"))
    return [
        {
            "failure_type": item["failure_type"],
            "count": item["count"],
            "affected_baselines": sorted(value for value in item["affected_baselines"] if value),
            "affected_tasks": sorted(value for value in item["affected_tasks"] if value),
            "example_trace_path": item["example_trace_path"],
        }
        for item in sorted(by_failure.values(), key=lambda item: (-item["count"], item["failure_type"]))
    ]


def _root_cause_summary(
    runs: Sequence[Mapping[str, Any]],
    *,
    task_domains: Mapping[str, str],
    final_answer_vs_validator: Mapping[str, Any],
    replay_results: Optional[Sequence[Any]],
    trace_limit: int,
) -> JsonDict:
    categories: dict[str, JsonDict] = {
        category: {"count": 0, "failure_types": {}}
        for category in ROOT_CAUSE_CATEGORIES
    }
    by_domain: dict[str, Counter] = defaultdict(Counter)
    by_tool: dict[str, Counter] = defaultdict(Counter)
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_validator: dict[str, Counter] = defaultdict(Counter)

    for run in runs:
        domain = task_domains.get(str(run.get("task_id")), "unknown")
        model = _model_for_run(run)
        tools = _trace_tool_names(str(run.get("trace_path"))) or ["unknown"]

        if _final_answer_passed(run) and run.get("passed") is not True:
            _record_root_cause(
                category="FINAL_ANSWER_OVERCLAIM",
                failure_type="final_answer_overclaim",
                domain=domain,
                model=model,
                validator_name="final_answer",
                tools=tools,
                categories=categories,
                by_domain=by_domain,
                by_tool=by_tool,
                by_model=by_model,
                by_validator=by_validator,
            )

        for result in _validator_results(run):
            if result.get("passed") is True or not result.get("failure_type"):
                continue
            category = root_cause_category_for_validator_result(result)
            _record_root_cause(
                category=category,
                failure_type=str(result.get("failure_type")),
                domain=domain,
                model=model,
                validator_name=str(result.get("validator_name", "unknown")),
                tools=tools,
                categories=categories,
                by_domain=by_domain,
                by_tool=by_tool,
                by_model=by_model,
                by_validator=by_validator,
            )

    for replay_result in replay_results or []:
        result = replay_result.to_dict() if hasattr(replay_result, "to_dict") else dict(replay_result)
        task_id = str(result.get("task_id", "unknown"))
        domain = task_domains.get(task_id, "unknown")
        for divergence in result.get("divergences", []):
            if not isinstance(divergence, Mapping):
                continue
            _record_root_cause(
                category="TRACE_REPLAY_DIVERGENCE",
                failure_type=str(divergence.get("type", "trace_replay_divergence")),
                domain=domain,
                model="unknown",
                validator_name="replay",
                tools=[str(divergence.get("tool_name", "unknown"))],
                categories=categories,
                by_domain=by_domain,
                by_tool=by_tool,
                by_model=by_model,
                by_validator=by_validator,
            )

    silent_failure_count = int(final_answer_vs_validator.get("silent_failure_count", 0))
    run_count = int(final_answer_vs_validator.get("run_count", len(runs)))
    validator_gap = float(final_answer_vs_validator.get("validator_gap", 0.0))
    return {
        "executive_summary": _executive_summary(final_answer_vs_validator),
        "run_count": run_count,
        "silent_failure_count": silent_failure_count,
        "silent_failure_rate": float(final_answer_vs_validator.get("silent_failure_rate", 0.0)),
        "answer_overclaim_rate": float(final_answer_vs_validator.get("answer_overclaim_rate", 0.0)),
        "validator_gap": validator_gap,
        "categories": _json_counter_table(categories),
        "failure_by_domain": _nested_counter_dict(by_domain),
        "failure_by_tool": _nested_counter_dict(by_tool),
        "failure_by_model": _nested_counter_dict(by_model),
        "failure_by_validator": _nested_counter_dict(by_validator),
        "top_replayable_failure_traces": _top_replayable_failure_traces(runs, trace_limit),
    }


def root_cause_category_for_validator_result(result: Mapping[str, Any]) -> str:
    failure_type = str(result.get("failure_type", ""))
    if failure_type == "cost_latency_violation":
        details = result.get("details", {})
        violations = details.get("violations", []) if isinstance(details, Mapping) else []
        if "cost" in violations:
            return "COST_LIMIT_EXCEEDED"
        if "timed_out" in violations or "latency_seconds" in violations:
            return "TIMEOUT"
        return "TIMEOUT"
    return _ROOT_CAUSE_BY_FAILURE_TYPE.get(failure_type, "TOOL_RESULT_MISUSE")


def _record_root_cause(
    *,
    category: str,
    failure_type: str,
    domain: str,
    model: str,
    validator_name: str,
    tools: Sequence[str],
    categories: dict[str, JsonDict],
    by_domain: dict[str, Counter],
    by_tool: dict[str, Counter],
    by_model: dict[str, Counter],
    by_validator: dict[str, Counter],
) -> None:
    category_record = categories.setdefault(category, {"count": 0, "failure_types": {}})
    category_record["count"] += 1
    failure_types = category_record.setdefault("failure_types", {})
    failure_types[failure_type] = int(failure_types.get(failure_type, 0)) + 1
    by_domain[domain][category] += 1
    for tool_name in tools:
        by_tool[tool_name][category] += 1
    by_model[model][category] += 1
    by_validator[validator_name][category] += 1


def _executive_summary(final_answer_vs_validator: Mapping[str, Any]) -> str:
    gap_points = float(final_answer_vs_validator.get("validator_gap", 0.0)) * 100
    silent_failure_count = int(final_answer_vs_validator.get("silent_failure_count", 0))
    run_count = int(final_answer_vs_validator.get("run_count", 0))
    return (
        "Final-answer-only grading overestimated validated correctness by "
        f"{gap_points:.1f} percentage points; deterministic validators caught "
        f"{silent_failure_count}/{run_count} silent failures."
    )


def _json_counter_table(categories: Mapping[str, JsonDict]) -> JsonDict:
    return {
        category: {
            "count": int(payload.get("count", 0)),
            "failure_types": dict(sorted(dict(payload.get("failure_types", {})).items())),
        }
        for category, payload in sorted(categories.items())
    }


def _nested_counter_dict(counters: Mapping[str, Counter]) -> JsonDict:
    return {
        key: {category: int(counter.get(category, 0)) for category in ROOT_CAUSE_CATEGORIES if counter.get(category, 0)}
        for key, counter in sorted(counters.items())
        if counter
    }


def _top_replayable_failure_traces(runs: Sequence[Mapping[str, Any]], limit: int) -> list[JsonDict]:
    run_by_id = {run.get("run_id"): run for run in runs}
    traces = []
    for trace in _worst_traces(runs, limit):
        if not trace["replay_ready"]:
            continue
        source_run = run_by_id.get(trace.get("run_id"), {})
        categories = sorted(
            {
                root_cause_category_for_validator_result({"failure_type": failure_type})
                for failure_type in trace["failure_types"]
            }
        )
        if _final_answer_passed(source_run) and "FINAL_ANSWER_OVERCLAIM" not in categories:
            categories.append("FINAL_ANSWER_OVERCLAIM")
        trace_with_causes = dict(trace)
        trace_with_causes["root_cause_categories"] = sorted(categories)
        traces.append(trace_with_causes)
    return traces


def _pass_at_k_curve(runs: Sequence[Mapping[str, Any]]) -> list[JsonDict]:
    if not runs:
        return []
    max_k = max(int(run.get("trial_index", 0)) for run in runs) + 1
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[(str(run.get("baseline_name")), str(run.get("task_id")))].append(run)
    curve: list[JsonDict] = []
    for k in range(1, max_k + 1):
        successful_groups = 0
        for group in grouped.values():
            first_k = [run for run in group if int(run.get("trial_index", 0)) < k]
            if any(run.get("passed") is True for run in first_k):
                successful_groups += 1
        curve.append({"k": k, "value": _safe_rate(successful_groups, len(grouped))})
    return curve


def _cost_latency_summary(runs: Sequence[Mapping[str, Any]]) -> JsonDict:
    return {
        "average_cost": _average_metric(runs, "cost"),
        "average_latency_seconds": _average_metric(runs, "latency_seconds"),
        "average_turns": _average_metric(runs, "turns"),
        "timeout_rate": _safe_rate(sum(1 for run in runs if _metric(run, "timed_out") is True), len(runs)),
        "by_baseline": _cost_latency_by_baseline(runs),
    }


def _cost_latency_by_baseline(runs: Sequence[Mapping[str, Any]]) -> JsonDict:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[str(run.get("baseline_name"))].append(run)
    return {
        baseline_name: {
            "average_cost": _average_metric(baseline_runs, "cost"),
            "average_latency_seconds": _average_metric(baseline_runs, "latency_seconds"),
            "average_turns": _average_metric(baseline_runs, "turns"),
            "timeout_rate": _safe_rate(
                sum(1 for run in baseline_runs if _metric(run, "timed_out") is True),
                len(baseline_runs),
            ),
        }
        for baseline_name, baseline_runs in sorted(grouped.items())
    }


def _replay_divergence_summary(replay_results: Optional[Sequence[Any]]) -> JsonDict:
    if replay_results is None:
        return {
            "available": False,
            "replayed_traces": 0,
            "passed_trace_count": 0,
            "divergent_trace_count": 0,
            "divergence_count": 0,
            "divergence_types": {},
        }
    return replay_divergence_summary_from_results(replay_results)


def _worst_traces(runs: Sequence[Mapping[str, Any]], limit: int) -> list[JsonDict]:
    failed_runs = [run for run in runs if run.get("passed") is not True]
    ranked = sorted(
        failed_runs,
        key=lambda run: (
            -len(_failure_types(run)),
            str(run.get("baseline_name")),
            str(run.get("task_id")),
            int(run.get("trial_index", 0)),
        ),
    )
    worst: list[JsonDict] = []
    for run in ranked[: max(0, limit)]:
        trace_path = str(run.get("trace_path"))
        versions = _trace_versions(trace_path)
        worst.append(
            {
                "run_id": run.get("run_id"),
                "task_id": run.get("task_id"),
                "baseline_name": run.get("baseline_name"),
                "trial_index": run.get("trial_index"),
                "trace_path": trace_path,
                "failure_count": len(_failure_types(run)),
                "failure_types": _failure_types(run),
                "replay_ready": bool(versions),
                "versions": versions,
            }
        )
    return worst


def _version_matrix(runs: Sequence[Mapping[str, Any]]) -> JsonDict:
    versions = {field: set() for field in VERSION_FIELDS}
    for run in runs:
        for field, value in _trace_versions(str(run.get("trace_path"))).items():
            if field in versions and value:
                versions[field].add(value)
    return {field: sorted(values) for field, values in versions.items()}


def _regression_comparison(
    current_summary: Mapping[str, Any],
    previous_summary: Optional[Mapping[str, Any]],
) -> JsonDict:
    if previous_summary is None:
        return {
            "available": False,
            "reason": "No previous summary artifact supplied.",
        }
    current_metrics = dict(current_summary.get("metrics", {}))
    previous_metrics = dict(previous_summary.get("metrics", {}))
    return {
        "available": True,
        "task_success_rate": _metric_delta(current_metrics, previous_metrics, "task_success_rate"),
        "pass_at_k": _pass_at_k_delta(current_metrics, previous_metrics),
        "failure_taxonomy_delta": _counter_delta(
            current_metrics.get("failure_taxonomy", {}),
            previous_metrics.get("failure_taxonomy", {}),
        ),
        "baseline_task_success_rate": _baseline_success_delta(current_summary, previous_summary),
        "current_versions": _version_matrix(_runs(current_summary)),
        "previous_versions": _version_matrix(_runs(previous_summary)),
    }


def _baseline_success_delta(
    current_summary: Mapping[str, Any],
    previous_summary: Mapping[str, Any],
) -> JsonDict:
    current = dict(current_summary.get("baseline_metrics", {}))
    previous = dict(previous_summary.get("baseline_metrics", {}))
    baselines = sorted(set(current) | set(previous))
    return {
        baseline: _optional_metric_delta(
            current.get(baseline, {}),
            previous.get(baseline, {}),
            "task_success_rate",
        )
        for baseline in baselines
    }


def _render_markdown(report: EvaluationReport) -> str:
    payload = report.to_dict()
    lines = [
        "# Sandboxed Agent Evaluation Report",
        "",
        "## Executive Summary",
        payload["executive_summary"],
        "",
        "## Summary",
        f"- Runs: {payload['summary']['run_count']}",
        f"- Task success rate: {payload['summary']['task_success_rate']:.3f}",
        f"- pass@k: {payload['summary'].get('pass_at_k', {}).get('value', 0.0):.3f}",
        "",
        "## Domain Success",
    ]
    for domain, metrics in payload["domain_success"].items():
        lines.append(
            f"- {domain}: {metrics['passed_count']}/{metrics['run_count']} "
            f"({metrics['success_rate']:.3f})"
        )
    lines.extend(["", "## Final Answer Vs Validator"])
    final_metrics = payload["final_answer_vs_validator"]
    lines.append(f"- Final-answer pass rate: {final_metrics['final_answer_pass_rate']:.3f}")
    lines.append(f"- Validator pass rate: {final_metrics['validator_pass_rate']:.3f}")
    lines.append(f"- Validator gap: {final_metrics['validator_gap']:.3f}")
    lines.append(f"- Silent failure rate: {final_metrics['silent_failure_rate']:.3f}")
    lines.append(f"- Silent failures: {final_metrics['silent_failure_count']}")
    lines.extend(["", "## Root Cause Summary"])
    for category, metrics in payload["root_cause_summary"]["categories"].items():
        if metrics["count"]:
            lines.append(f"- {category}: {metrics['count']}")
    lines.extend(["", "## Failure Distribution"])
    for failure_type, count in payload["failure_type_distribution"].items():
        lines.append(f"- {failure_type}: {count}")
    lines.extend(["", "## Pass@k Curve"])
    for point in payload["pass_at_k_curve"]:
        lines.append(f"- k={point['k']}: {point['value']:.3f}")
    lines.extend(["", "## Cost And Latency"])
    cost_latency = payload["cost_latency_summary"]
    lines.append(f"- Average latency seconds: {cost_latency['average_latency_seconds']:.3f}")
    lines.append(f"- Average cost: {cost_latency['average_cost']:.3f}")
    lines.append(f"- Timeout rate: {cost_latency['timeout_rate']:.3f}")
    lines.extend(["", "## Replay Divergence"])
    replay_summary = payload["replay_divergence_summary"]
    if replay_summary["available"]:
        lines.append(f"- Replayed traces: {replay_summary['replayed_traces']}")
        lines.append(f"- Divergent traces: {replay_summary['divergent_trace_count']}")
        lines.append(f"- Divergences: {replay_summary['divergence_count']}")
    else:
        lines.append("- Replay divergence data was not supplied.")
    lines.extend(["", "## Worst Traces"])
    for trace in payload["worst_traces"]:
        lines.append(
            f"- {trace['baseline_name']} / {trace['task_id']}: "
            f"{', '.join(trace['failure_types'])} ({trace['trace_path']})"
        )
    lines.extend(["", "## Regression Comparison"])
    comparison = payload["regression_comparison"]
    if comparison.get("available"):
        delta = comparison["task_success_rate"]["delta"]
        lines.append(f"- Task success rate delta: {delta:.3f}")
    else:
        lines.append(f"- {comparison['reason']}")
    return "\n".join(lines)


def _validator_results(run: Mapping[str, Any]) -> list[JsonDict]:
    raw_results = run.get("validator_results", [])
    return [dict(result) for result in raw_results if isinstance(result, Mapping)]


def _failure_types(run: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            result["failure_type"]
            for result in _validator_results(run)
            if result.get("passed") is not True and result.get("failure_type")
        }
    )


def _trace_versions(path: str) -> JsonDict:
    if not path:
        return {}
    try:
        replay = TraceReplay.from_jsonl(path)
    except (OSError, TraceReplayError, ValueError):
        return {}
    return {field: replay.metadata.get(field) for field in VERSION_FIELDS if replay.metadata.get(field)}


def _model_for_run(run: Mapping[str, Any]) -> str:
    versions = _trace_versions(str(run.get("trace_path")))
    model = versions.get("model")
    return str(model or run.get("baseline_name") or "unknown")


def _trace_tool_names(path: str) -> list[str]:
    if not path:
        return []
    try:
        replay = TraceReplay.from_jsonl(path)
    except (OSError, TraceReplayError, ValueError):
        return []
    names = []
    for event in replay.events:
        if event.event_type != "tool_call":
            continue
        tool_name = event.payload.get("tool_name")
        if isinstance(tool_name, str) and tool_name not in names:
            names.append(tool_name)
    return names


def _metric(run: Mapping[str, Any], name: str) -> Any:
    metrics = run.get("metrics", {})
    return metrics.get(name) if isinstance(metrics, Mapping) else None


def _average_metric(runs: Sequence[Mapping[str, Any]], name: str) -> float:
    values = [_metric(run, name) for run in runs]
    numeric_values = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return sum(numeric_values) / len(numeric_values) if numeric_values else 0.0


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _metric_delta(current: Mapping[str, Any], previous: Mapping[str, Any], key: str) -> JsonDict:
    current_value = float(current.get(key, 0.0))
    previous_value = float(previous.get(key, 0.0))
    return {
        "previous": previous_value,
        "current": current_value,
        "delta": current_value - previous_value,
    }


def _optional_metric_delta(current: Mapping[str, Any], previous: Mapping[str, Any], key: str) -> JsonDict:
    current_value = current.get(key) if isinstance(current, Mapping) else None
    previous_value = previous.get(key) if isinstance(previous, Mapping) else None
    return {
        "previous": previous_value,
        "current": current_value,
        "delta": current_value - previous_value if current_value is not None and previous_value is not None else None,
    }


def _pass_at_k_delta(current: Mapping[str, Any], previous: Mapping[str, Any]) -> JsonDict:
    current_pass_at_k = current.get("pass_at_k", {})
    previous_pass_at_k = previous.get("pass_at_k", {})
    current_value = float(current_pass_at_k.get("value", 0.0)) if isinstance(current_pass_at_k, Mapping) else 0.0
    previous_value = float(previous_pass_at_k.get("value", 0.0)) if isinstance(previous_pass_at_k, Mapping) else 0.0
    return {
        "previous": previous_value,
        "current": current_value,
        "delta": current_value - previous_value,
    }


def _counter_delta(current: Any, previous: Any) -> JsonDict:
    current_counter = Counter(current if isinstance(current, Mapping) else {})
    previous_counter = Counter(previous if isinstance(previous, Mapping) else {})
    keys = sorted(set(current_counter) | set(previous_counter))
    return {
        key: {
            "previous": previous_counter.get(key, 0),
            "current": current_counter.get(key, 0),
            "delta": current_counter.get(key, 0) - previous_counter.get(key, 0),
        }
        for key in keys
    }


if __name__ == "__main__":
    raise SystemExit(main())
