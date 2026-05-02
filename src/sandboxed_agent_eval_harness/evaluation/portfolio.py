"""Static portfolio report generation for recruiter and interview review."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.evaluation.model_matrix import run_recorded_model_matrix
from sandboxed_agent_eval_harness.evaluation.report import root_cause_category_for_validator_result
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite
from sandboxed_agent_eval_harness.tracing import TraceReplayError, load_trace_events


DEFAULT_RECORDED_OUTPUT = "fixtures/model_outputs/model_matrix.json"
DEFAULT_OUTPUT_DIR = "reports"
DEFAULT_EVIDENCE_DIR = "artifacts/eval_runs/portfolio_model_matrix"


def run_portfolio_report(
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    evidence_dir: Path | str = DEFAULT_EVIDENCE_DIR,
    recorded_output_path: Path | str = DEFAULT_RECORDED_OUTPUT,
    suite_name: str = "benchmark",
    case_study_count: int = 3,
) -> JsonDict:
    output_path = Path(output_dir)
    evidence_path = Path(evidence_dir)
    tables_path = output_path / "tables"
    examples_path = output_path / "examples"
    output_path.mkdir(parents=True, exist_ok=True)
    tables_path.mkdir(parents=True, exist_ok=True)
    examples_path.mkdir(parents=True, exist_ok=True)
    _clear_generated_examples(examples_path)

    matrix_result = run_recorded_model_matrix(
        recorded_output_path=recorded_output_path,
        output_dir=evidence_path,
        suite_name=suite_name,
    )
    matrix = _load_json(matrix_result["matrix_path"])
    report = _load_json(matrix_result["report_path"])
    summary = _load_json(matrix_result["summary_path"])
    suite = benchmark_task_suite()

    model_matrix_csv = tables_path / "model_matrix.csv"
    failure_taxonomy_csv = tables_path / "failure_taxonomy.csv"
    domain_breakdown_csv = tables_path / "domain_breakdown.csv"
    _write_model_matrix_csv(matrix, model_matrix_csv)
    _write_failure_taxonomy_csv(report, failure_taxonomy_csv)
    _write_domain_breakdown_csv(report, domain_breakdown_csv)

    case_studies = _write_case_studies(
        report=report,
        summary=summary,
        examples_dir=examples_path,
        count=case_study_count,
    )

    portfolio = _portfolio_payload(
        matrix=matrix,
        report=report,
        suite_task_count=len(suite.tasks),
        case_studies=case_studies,
        output_path=output_path,
        evidence_path=evidence_path,
    )
    report_json = output_path / "portfolio_report.json"
    report_markdown = output_path / "portfolio_report.md"
    report_json.write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n")
    report_markdown.write_text(_render_portfolio_markdown(portfolio) + "\n")

    return {
        "portfolio_report_md": str(report_markdown),
        "portfolio_report_json": str(report_json),
        "model_matrix_csv": str(model_matrix_csv),
        "failure_taxonomy_csv": str(failure_taxonomy_csv),
        "domain_breakdown_csv": str(domain_breakdown_csv),
        "case_studies": case_studies,
        "model_count": matrix["model_count"],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a static portfolio evidence report.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--evidence-dir", default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--recorded-output", default=DEFAULT_RECORDED_OUTPUT)
    parser.add_argument("--suite", default="benchmark", choices=["benchmark"])
    parser.add_argument("--case-studies", type=int, default=3)
    args = parser.parse_args(argv)

    result = run_portfolio_report(
        output_dir=args.output_dir,
        evidence_dir=args.evidence_dir,
        recorded_output_path=args.recorded_output,
        suite_name=args.suite,
        case_study_count=args.case_studies,
    )
    print(
        f"portfolio_report={result['portfolio_report_md']} "
        f"case_studies={len(result['case_studies'])} "
        f"models={result['model_count']}"
    )
    return 0


def _portfolio_payload(
    *,
    matrix: Mapping[str, Any],
    report: Mapping[str, Any],
    suite_task_count: int,
    case_studies: Sequence[Mapping[str, Any]],
    output_path: Path,
    evidence_path: Path,
) -> JsonDict:
    final_metrics = dict(report["final_answer_vs_validator"])
    root_cause = dict(report["root_cause_summary"])
    return {
        "title": "Sandboxed Tool-Use Agent Evaluation Harness",
        "problem": {
            "headline": "Final-answer-only eval misses silent tool-use failures",
            "description": (
                "The harness evaluates whether tool-using agents used the right tools, "
                "arguments, state mutations, numeric outputs, citations, and constraints, "
                "not just whether the final answer sounds plausible."
            ),
        },
        "system": {
            "pipeline": [
                "typed task schema",
                "typed tool registry",
                "workspace/container evaluation isolation",
                "JSONL trace capture",
                "deterministic validators",
                "trace replay",
                "regression gates",
                "static reports",
            ],
            "validators": [
                "schema",
                "tool_sequence",
                "argument",
                "state",
                "numeric",
                "citation",
                "constraint",
                "unit_test",
                "policy",
                "cost_latency",
            ],
        },
        "evidence": {
            "recorded_offline": True,
            "live_provider_benchmark": False,
            "key_finding": matrix["key_finding"],
            "run_count": matrix["run_count"],
            "final_answer_pass_rate": final_metrics["final_answer_pass_rate"],
            "validator_pass_rate": final_metrics["validator_pass_rate"],
            "validator_gap": final_metrics["validator_gap"],
            "silent_failure_count": final_metrics["silent_failure_count"],
        },
        "benchmark": {
            "suite": matrix["suite"],
            "task_count": suite_task_count,
            "domains": sorted(report["domain_success"]),
            "fixture_backed": True,
        },
        "model_matrix": {
            "model_count": matrix["model_count"],
            "distinct_failure_signature_count": matrix["distinct_failure_signature_count"],
            "models": list(matrix["models"]),
        },
        "failure_taxonomy": {
            "categories": root_cause["categories"],
            "failure_by_domain": root_cause["failure_by_domain"],
            "failure_by_tool": root_cause["failure_by_tool"],
            "failure_by_model": root_cause["failure_by_model"],
            "failure_by_validator": root_cause["failure_by_validator"],
        },
        "case_studies": [dict(case) for case in case_studies],
        "reproducibility": {
            "command": "make portfolio-report",
            "ci_command": "make ci",
            "default_requires_credentials": False,
            "artifact_dir": str(output_path),
            "evidence_dir": str(evidence_path),
        },
        "limitations": [
            "This report is generated from recorded offline model profiles; it is not a live-provider benchmark.",
            "Benchmark tasks are deterministic and fixture-backed; they are evidence for harness behavior, not broad production claims.",
            "Docker support is evaluation isolation and reproducibility support, not a security product.",
            "Live provider runs remain opt-in and credentials-gated; default validation does not call external APIs.",
        ],
        "artifacts": {
            "portfolio_report_md": str(output_path / "portfolio_report.md"),
            "portfolio_report_json": str(output_path / "portfolio_report.json"),
            "model_matrix_csv": str(output_path / "tables" / "model_matrix.csv"),
            "failure_taxonomy_csv": str(output_path / "tables" / "failure_taxonomy.csv"),
            "domain_breakdown_csv": str(output_path / "tables" / "domain_breakdown.csv"),
            "model_matrix_summary_json": str(evidence_path / "model_matrix_summary.json"),
            "evidence_summary_json": str(evidence_path / "summary.json"),
        },
        "key_result": matrix["key_finding"],
    }


def _write_model_matrix_csv(matrix: Mapping[str, Any], path: Path) -> None:
    rows = list(matrix["models"])
    columns = [
        "model",
        "run_count",
        "final_answer_pass_rate",
        "validator_pass_rate",
        "silent_failure_count",
        "validator_gap",
        "top_root_cause",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "model": row["model"],
                    "run_count": row["run_count"],
                    "final_answer_pass_rate": f"{float(row['final_answer_pass_rate']):.6f}",
                    "validator_pass_rate": f"{float(row['validator_pass_rate']):.6f}",
                    "silent_failure_count": row["silent_failure_count"],
                    "validator_gap": f"{float(row['validator_gap']):.6f}",
                    "top_root_cause": row["top_root_cause"],
                }
            )


def _write_failure_taxonomy_csv(report: Mapping[str, Any], path: Path) -> None:
    categories = report["root_cause_summary"]["categories"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["category", "count", "failure_types"])
        writer.writeheader()
        for category, payload in sorted(categories.items()):
            writer.writerow(
                {
                    "category": category,
                    "count": int(payload.get("count", 0)),
                    "failure_types": json.dumps(payload.get("failure_types", {}), sort_keys=True),
                }
            )


def _write_domain_breakdown_csv(report: Mapping[str, Any], path: Path) -> None:
    domain_success = report["domain_success"]
    failure_by_domain = report["root_cause_summary"]["failure_by_domain"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "domain",
                "run_count",
                "passed_count",
                "success_rate",
                "silent_failure_count",
                "top_root_cause",
            ],
        )
        writer.writeheader()
        for domain, metrics in sorted(domain_success.items()):
            failures = dict(failure_by_domain.get(domain, {}))
            writer.writerow(
                {
                    "domain": domain,
                    "run_count": metrics["run_count"],
                    "passed_count": metrics["passed_count"],
                    "success_rate": f"{float(metrics['success_rate']):.6f}",
                    "silent_failure_count": int(failures.get("FINAL_ANSWER_OVERCLAIM", 0)),
                    "top_root_cause": _top_category(failures),
                }
            )


def _write_case_studies(
    *,
    report: Mapping[str, Any],
    summary: Mapping[str, Any],
    examples_dir: Path,
    count: int,
) -> list[JsonDict]:
    traces = _select_case_study_traces(report, summary=summary, count=count)
    case_studies: list[JsonDict] = []
    for index, trace in enumerate(traces, start=1):
        trace_path = str(trace["trace_path"])
        events = _load_events(trace_path)
        instruction = _first_payload_text(events, "user_message")
        tool_sequence = _tool_sequence(events)
        result_summary = {
            "case_id": f"replayable_failure_{index:02d}",
            "task_id": trace["task_id"],
            "model_or_baseline": trace["baseline_name"],
            "trace_path": trace_path,
            "failure_types": list(trace["failure_types"]),
            "root_cause_categories": list(trace.get("root_cause_categories", [])),
            "tool_sequence": tool_sequence,
            "case_study_path": str(examples_dir / f"replayable_failure_{index:02d}_{_slug(trace['task_id'])}.md"),
        }
        Path(result_summary["case_study_path"]).write_text(
            _render_case_study_markdown(result_summary, instruction=instruction) + "\n"
        )
        case_studies.append(result_summary)
    return case_studies


def _clear_generated_examples(examples_dir: Path) -> None:
    for path in examples_dir.glob("replayable_failure_*.md"):
        path.unlink()


def _select_case_study_traces(
    report: Mapping[str, Any],
    *,
    summary: Mapping[str, Any],
    count: int,
) -> list[JsonDict]:
    candidates = _case_study_traces_from_summary(summary)
    candidates.extend(
        dict(trace)
        for trace in report["root_cause_summary"].get("top_replayable_failure_traces", [])
        if trace.get("trace_path")
    )
    selected: list[JsonDict] = []
    seen_primary_causes: set[str] = set()
    for trace in candidates:
        primary = _primary_root_cause(trace)
        if primary in seen_primary_causes and len(candidates) >= count:
            continue
        selected.append(trace)
        seen_primary_causes.add(primary)
        if len(selected) >= count:
            break
    for trace in candidates:
        if len(selected) >= count:
            break
        if trace not in selected:
            selected.append(trace)
    return selected[:count]


def _case_study_traces_from_summary(summary: Mapping[str, Any]) -> list[JsonDict]:
    raw_runs = summary.get("runs", [])
    if not isinstance(raw_runs, list):
        return []
    candidates: list[JsonDict] = []
    for run in raw_runs:
        if not isinstance(run, Mapping) or run.get("passed") is True or not run.get("trace_path"):
            continue
        failure_types: list[str] = []
        categories: set[str] = set()
        for result in run.get("validator_results", []):
            if not isinstance(result, Mapping) or result.get("passed") is True:
                continue
            failure_type = result.get("failure_type")
            if failure_type:
                failure_types.append(str(failure_type))
                categories.add(root_cause_category_for_validator_result(result))
        metrics = run.get("metrics", {})
        if isinstance(metrics, Mapping) and metrics.get("final_answer_passed") is True:
            categories.add("FINAL_ANSWER_OVERCLAIM")
        if not failure_types:
            continue
        candidates.append(
            {
                "run_id": run.get("run_id"),
                "task_id": run.get("task_id"),
                "baseline_name": run.get("baseline_name"),
                "trial_index": run.get("trial_index"),
                "trace_path": run.get("trace_path"),
                "failure_count": len(set(failure_types)),
                "failure_types": sorted(set(failure_types)),
                "root_cause_categories": sorted(categories),
                "replay_ready": True,
            }
        )
    return sorted(
        candidates,
        key=lambda trace: (
            _primary_root_cause(trace),
            -int(trace.get("failure_count", 0)),
            str(trace.get("baseline_name")),
            str(trace.get("task_id")),
        ),
    )


def _render_portfolio_markdown(portfolio: Mapping[str, Any]) -> str:
    evidence = portfolio["evidence"]
    benchmark = portfolio["benchmark"]
    model_matrix = portfolio["model_matrix"]
    lines = [
        "# Sandboxed Tool-Use Agent Evaluation Harness",
        "",
        "## Problem",
        portfolio["problem"]["description"],
        "",
        "## System",
        "Pipeline: " + " -> ".join(portfolio["system"]["pipeline"]),
        "",
        "Validators: " + ", ".join(portfolio["system"]["validators"]),
        "",
        "## Evidence",
        portfolio["key_result"],
        "",
        f"- Recorded offline runs: {evidence['run_count']}",
        f"- Final-answer pass rate: {evidence['final_answer_pass_rate']:.3f}",
        f"- Validator pass rate: {evidence['validator_pass_rate']:.3f}",
        f"- Silent failures: {evidence['silent_failure_count']}",
        f"- Model profiles: {model_matrix['model_count']}",
        f"- Distinct failure signatures: {model_matrix['distinct_failure_signature_count']}",
        "",
        "## Benchmark",
        f"- Suite: {benchmark['suite']}",
        f"- Tasks: {benchmark['task_count']}",
        f"- Domains: {', '.join(benchmark['domains'])}",
        "- Fixture-backed deterministic benchmark; not a live-provider benchmark.",
        "",
        "## Failure Taxonomy",
    ]
    for category, payload in portfolio["failure_taxonomy"]["categories"].items():
        if int(payload.get("count", 0)):
            lines.append(f"- {category}: {payload['count']}")
    lines.extend(["", "## Case Studies"])
    for case in portfolio["case_studies"]:
        case_link = str(Path("examples") / Path(str(case["case_study_path"])).name)
        lines.append(
            f"- [{case['case_id']}]({case_link}): "
            f"{case['model_or_baseline']} / {case['task_id']} "
            f"({', '.join(case['root_cause_categories'])})"
        )
    lines.extend(
        [
            "",
            "## Reproducibility",
            f"- Generate this report: `{portfolio['reproducibility']['command']}`",
            f"- Run deterministic CI: `{portfolio['reproducibility']['ci_command']}`",
            "- Default report generation is key-free and network-free.",
            "",
            "## Limitations",
        ]
    )
    for limitation in portfolio["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines)


def _render_case_study_markdown(case: Mapping[str, Any], *, instruction: str) -> str:
    replay_command = (
        "PYTHONPATH=src python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor\n"
        f"result = TraceReplayExecutor().replay(Path({case['trace_path']!r}), workspace='/tmp/sandboxed-agent-eval-portfolio-replay')\n"
        "print(result.to_dict())\n"
        "PY"
    )
    return "\n".join(
        [
            f"# {case['case_id']}: {case['task_id']}",
            "",
            f"Model or baseline: {case['model_or_baseline']}",
            f"Trace path: {case['trace_path']}",
            "Root causes: " + ", ".join(case["root_cause_categories"]),
            "Failure types: " + ", ".join(case["failure_types"]),
            "Tool sequence: " + ", ".join(case["tool_sequence"]),
            "",
            "## Prompt",
            instruction or "Unavailable in trace.",
            "",
            "## Replay command",
            "Replay command:",
            "```bash",
            replay_command,
            "```",
        ]
    )


def _load_events(trace_path: str) -> list[Any]:
    try:
        return load_trace_events(trace_path)
    except (OSError, TraceReplayError, ValueError):
        return []


def _first_payload_text(events: Sequence[Any], event_type: str) -> str:
    for event in events:
        if event.event_type == event_type:
            content = event.payload.get("content")
            if isinstance(content, str):
                return content
    return ""


def _tool_sequence(events: Sequence[Any]) -> list[str]:
    sequence: list[str] = []
    for event in events:
        if event.event_type != "tool_call":
            continue
        tool_name = event.payload.get("tool_name")
        if isinstance(tool_name, str):
            sequence.append(tool_name)
    return sequence


def _primary_root_cause(trace: Mapping[str, Any]) -> str:
    categories = trace.get("root_cause_categories", [])
    if not isinstance(categories, list) or not categories:
        return "UNKNOWN"
    for category in categories:
        if category != "FINAL_ANSWER_OVERCLAIM":
            return str(category)
    return str(categories[0])


def _top_category(counts: Mapping[str, Any]) -> str:
    if not counts:
        return "NONE"
    category, count = max(counts.items(), key=lambda item: (int(item[1]), str(item[0])))
    return str(category) if int(count) > 0 else "NONE"


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")[:80] or "trace"


def _load_json(path: Path | str) -> JsonDict:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON artifact: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
