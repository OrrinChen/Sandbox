"""Recorded model matrix study for fixture-safe behavior-profile comparisons."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.agents import ModelAdapterAgent
from sandboxed_agent_eval_harness.evaluation.model_study import _aggregate_comparison, _key_finding, _model_comparison
from sandboxed_agent_eval_harness.evaluation.report import build_evaluation_report, write_evaluation_report
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationSummary, run_evaluation
from sandboxed_agent_eval_harness.models import load_recorded_model_adapters
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import task_suite_by_name


CSV_COLUMNS = [
    "model",
    "baseline_name",
    "run_count",
    "final_answer_pass_rate",
    "validator_pass_rate",
    "silent_failure_count",
    "validator_gap",
    "top_root_cause",
    "failure_signature",
]


def run_recorded_model_matrix(
    recorded_output_path: Path | str = "fixtures/model_outputs/model_matrix.json",
    output_dir: Path | str = "artifacts/eval_runs/model_matrix",
    suite_name: str = "benchmark",
) -> JsonDict:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    suite = task_suite_by_name(suite_name)
    adapters = load_recorded_model_adapters(recorded_output_path)
    summary = run_evaluation(
        suite=suite,
        baselines=[ModelAdapterAgent(adapter) for adapter in adapters],
        trials_per_task=1,
        output_dir=output_path,
    )
    report = build_evaluation_report(summary, suite=suite)
    report_paths = write_evaluation_report(report, output_path / "report")

    rows = _matrix_rows(summary, report.root_cause_summary)
    matrix = {
        "study_id": "phase19-recorded-model-matrix",
        "recorded_output_path": str(recorded_output_path),
        "suite": suite_name,
        "summary_path": str(output_path / "summary.json"),
        "report_path": report_paths["json_path"],
        "markdown_path": str(output_path / "model_comparison_report.md"),
        "csv_path": str(output_path / "silent_failure_by_model.csv"),
        "model_count": len(rows),
        "run_count": sum(int(row["run_count"]) for row in rows),
        "distinct_failure_signature_count": len({tuple(row["failure_signature"]) for row in rows}),
        "models": rows,
        "aggregate": _aggregate_comparison(rows),
        "root_cause_summary": report.root_cause_summary,
        "key_finding": _key_finding(rows),
        "artifacts": {
            "summary_json": str(output_path / "summary.json"),
            "report_json": report_paths["json_path"],
            "report_markdown": report_paths["markdown_path"],
            "model_matrix_summary_json": str(output_path / "model_matrix_summary.json"),
            "model_comparison_markdown": str(output_path / "model_comparison_report.md"),
            "silent_failure_by_model_csv": str(output_path / "silent_failure_by_model.csv"),
        },
    }

    matrix_path = output_path / "model_matrix_summary.json"
    markdown_path = output_path / "model_comparison_report.md"
    csv_path = output_path / "silent_failure_by_model.csv"
    matrix_path.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(_render_model_comparison_markdown(matrix) + "\n")
    _write_model_csv(rows, csv_path)
    return {
        "matrix_path": str(matrix_path),
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "summary_path": str(output_path / "summary.json"),
        "report_path": report_paths["json_path"],
        "models": rows,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a fixture-backed recorded model matrix study.")
    parser.add_argument("--recorded-output", default="fixtures/model_outputs/model_matrix.json")
    parser.add_argument("--output-dir", default="artifacts/eval_runs/model_matrix")
    parser.add_argument("--suite", default="benchmark", choices=["smoke", "benchmark"])
    args = parser.parse_args(argv)

    result = run_recorded_model_matrix(args.recorded_output, args.output_dir, suite_name=args.suite)
    rows = result["models"]
    max_gap = max((float(row["validator_gap"]) for row in rows), default=0.0)
    distinct_signatures = len({tuple(row["failure_signature"]) for row in rows})
    run_count = sum(int(row["run_count"]) for row in rows)
    print(
        f"models={len(rows)} "
        f"run_count={run_count} "
        f"distinct_signatures={distinct_signatures} "
        f"max_validator_gap={max_gap:.3f}"
    )
    return 0


def _matrix_rows(summary: EvaluationSummary, root_cause_summary: Mapping[str, Any]) -> list[JsonDict]:
    by_model = root_cause_summary.get("failure_by_model", {})
    rows = []
    for row in _model_comparison(summary):
        model = str(row["model"])
        root_causes = dict(by_model.get(model, {})) if isinstance(by_model, Mapping) else {}
        failure_signature = _failure_signature(row, root_causes)
        matrix_row = dict(row)
        matrix_row["validator_gap"] = float(row["overstatement_rate"])
        matrix_row["root_cause_categories"] = dict(sorted(root_causes.items()))
        matrix_row["top_root_cause"] = _top_root_cause(root_causes)
        matrix_row["failure_signature"] = failure_signature
        rows.append(matrix_row)
    return sorted(
        rows,
        key=lambda item: (
            -float(item["validator_gap"]),
            -int(item["silent_failure_count"]),
            str(item["model"]),
        ),
    )


def _failure_signature(row: Mapping[str, Any], root_causes: Mapping[str, Any]) -> list[str]:
    parts = [
        f"root:{category}:{count}"
        for category, count in sorted(root_causes.items())
        if int(count) > 0
    ]
    taxonomy = row.get("failure_taxonomy", {})
    if isinstance(taxonomy, Mapping):
        parts.extend(
            f"failure:{failure_type}:{count}"
            for failure_type, count in sorted(taxonomy.items())
            if int(count) > 0
        )
    if not parts:
        parts.append("pass:all")
    return parts


def _top_root_cause(root_causes: Mapping[str, Any]) -> str:
    if not root_causes:
        return "NONE"
    explanatory_causes = {
        category: count
        for category, count in root_causes.items()
        if category != "FINAL_ANSWER_OVERCLAIM"
    }
    if explanatory_causes:
        root_causes = explanatory_causes
    category, count = max(
        root_causes.items(),
        key=lambda item: (int(item[1]), str(item[0])),
    )
    return str(category) if int(count) > 0 else "NONE"


def _write_model_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "model": row["model"],
                    "baseline_name": row["baseline_name"],
                    "run_count": row["run_count"],
                    "final_answer_pass_rate": f"{float(row['final_answer_pass_rate']):.6f}",
                    "validator_pass_rate": f"{float(row['validator_pass_rate']):.6f}",
                    "silent_failure_count": row["silent_failure_count"],
                    "validator_gap": f"{float(row['validator_gap']):.6f}",
                    "top_root_cause": row["top_root_cause"],
                    "failure_signature": ";".join(row["failure_signature"]),
                }
            )


def _render_model_comparison_markdown(matrix: Mapping[str, Any]) -> str:
    lines = [
        "# Recorded Model Matrix",
        "",
        "## Executive Summary",
        str(matrix["key_finding"]),
        "",
        "## Summary",
        f"- Suite: {matrix['suite']}",
        f"- Models: {matrix['model_count']}",
        f"- Runs: {matrix['run_count']}",
        f"- Distinct failure signatures: {matrix['distinct_failure_signature_count']}",
        "",
        "## Model Comparison",
        (
            "| model | final-answer pass | validator pass | silent failures | "
            "validator gap | top root cause |"
        ),
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in matrix["models"]:
        lines.append(
            "| {model} | {final_answer_pass_rate:.3f} | {validator_pass_rate:.3f} | "
            "{silent_failure_count} | {validator_gap:.3f} | {top_root_cause} |".format(**row)
        )
    lines.extend(["", "## Failure Signatures"])
    for row in matrix["models"]:
        lines.append(f"- {row['model']}: {'; '.join(row['failure_signature'])}")
    lines.extend(
        [
            "",
            "## Limitations",
            "- This matrix uses recorded fixture profiles only; it makes no live provider calls.",
            "- Profiles represent controlled behavior signatures, not claims about specific public model providers.",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
