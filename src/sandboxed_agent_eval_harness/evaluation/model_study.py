"""Run recorded model-output studies and summarize silent failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.agents import ModelAdapterAgent
from sandboxed_agent_eval_harness.evaluation.report import build_evaluation_report, write_evaluation_report
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationSummary, run_evaluation
from sandboxed_agent_eval_harness.models import load_recorded_model_adapters
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import task_suite_by_name


def run_silent_failure_study(
    recorded_output_path: Path | str = "fixtures/model_outputs/silent_failure_study.json",
    output_dir: Path | str = "artifacts/eval_runs/silent_failure_study",
    suite_name: str = "smoke",
) -> JsonDict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    suite = task_suite_by_name(suite_name)
    adapters = load_recorded_model_adapters(recorded_output_path)
    baselines = [ModelAdapterAgent(adapter) for adapter in adapters]
    summary = run_evaluation(
        suite=suite,
        baselines=baselines,
        trials_per_task=1,
        output_dir=output_path,
    )
    report = build_evaluation_report(summary, suite=suite)
    report_paths = write_evaluation_report(report, output_path / "report")
    model_comparison = _model_comparison(summary)
    study = {
        "study_id": "phase15-silent-failure-study",
        "recorded_output_path": str(recorded_output_path),
        "suite": suite_name,
        "summary_path": str(output_path / "summary.json"),
        "report_path": report_paths["json_path"],
        "model_comparison": model_comparison,
        "key_finding": _key_finding(model_comparison),
    }
    study_path = output_path / "silent_failure_study.json"
    study_path.write_text(json.dumps(study, indent=2, sort_keys=True) + "\n")
    return {
        "study_path": str(study_path),
        "summary_path": str(output_path / "summary.json"),
        "report_path": report_paths["json_path"],
        "model_comparison": model_comparison,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a recorded model silent-failure study.")
    parser.add_argument("--recorded-output", default="fixtures/model_outputs/silent_failure_study.json")
    parser.add_argument("--output-dir", default="artifacts/eval_runs/silent_failure_study")
    parser.add_argument("--suite", default="smoke", choices=["smoke", "benchmark"])
    args = parser.parse_args(argv)

    result = run_silent_failure_study(args.recorded_output, args.output_dir, suite_name=args.suite)
    comparison = result["model_comparison"]
    aggregate = _aggregate_comparison(comparison)
    print(
        f"models={len(comparison)} "
        f"final_answer_pass_rate={aggregate['final_answer_pass_rate']:.3f} "
        f"validator_pass_rate={aggregate['validator_pass_rate']:.3f} "
        f"silent_failures={aggregate['silent_failure_count']}"
    )
    return 0


def _model_comparison(summary: EvaluationSummary) -> list[JsonDict]:
    rows: list[JsonDict] = []
    for baseline_name, metrics in sorted(summary.baseline_metrics.items()):
        runs = [run for run in summary.runs if run.baseline_name == baseline_name]
        final_answer_passed = sum(1 for run in runs if run.metrics.get("final_answer_passed") is True)
        validator_passed = sum(1 for run in runs if run.passed)
        silent_failures = sum(
            1
            for run in runs
            if run.metrics.get("final_answer_passed") is True and run.passed is not True
        )
        run_count = len(runs)
        final_rate = _safe_rate(final_answer_passed, run_count)
        validator_rate = _safe_rate(validator_passed, run_count)
        rows.append(
            {
                "baseline_name": baseline_name,
                "model": _model_for_runs(runs),
                "run_count": run_count,
                "final_answer_pass_rate": final_rate,
                "validator_pass_rate": validator_rate,
                "overstatement_rate": final_rate - validator_rate,
                "silent_failure_count": silent_failures,
                "failure_taxonomy": dict(metrics.get("failure_taxonomy", {})),
                "average_cost": metrics.get("average_cost", 0.0),
                "average_latency_seconds": metrics.get("average_latency_seconds", 0.0),
            }
        )
    return rows


def _aggregate_comparison(rows: Sequence[Mapping[str, Any]]) -> JsonDict:
    if not rows:
        return {
            "final_answer_pass_rate": 0.0,
            "validator_pass_rate": 0.0,
            "silent_failure_count": 0,
        }
    run_count = sum(int(row.get("run_count", 0)) for row in rows)
    silent_failure_count = sum(int(row.get("silent_failure_count", 0)) for row in rows)
    final_answer_passed = sum(float(row.get("final_answer_pass_rate", 0.0)) * int(row.get("run_count", 0)) for row in rows)
    validator_passed = sum(float(row.get("validator_pass_rate", 0.0)) * int(row.get("run_count", 0)) for row in rows)
    return {
        "final_answer_pass_rate": final_answer_passed / run_count if run_count else 0.0,
        "validator_pass_rate": validator_passed / run_count if run_count else 0.0,
        "silent_failure_count": silent_failure_count,
    }


def _key_finding(rows: Sequence[Mapping[str, Any]]) -> str:
    aggregate = _aggregate_comparison(rows)
    return (
        "Final-answer-only scoring overstated validated correctness by "
        f"{aggregate['final_answer_pass_rate'] - aggregate['validator_pass_rate']:.3f}; "
        f"deterministic validators caught {aggregate['silent_failure_count']} silent failures."
    )


def _model_for_runs(runs: Sequence[Any]) -> str:
    if not runs:
        return "unknown"
    trace_path = Path(runs[0].trace_path)
    try:
        first_line = trace_path.read_text().splitlines()[0]
        metadata = json.loads(first_line).get("metadata", {})
    except (OSError, IndexError, json.JSONDecodeError):
        return "unknown"
    return str(metadata.get("model", "unknown"))


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
