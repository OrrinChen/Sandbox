"""Compare the reader inputs while holding the retrieved top five fixed."""

from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path
from typing import Callable, Sequence

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.report import (
    _BOOTSTRAP_REPLICATES,
    _BOOTSTRAP_SEED,
    _cluster_draws,
    _cluster_interval,
)
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.variants import VARIANTS
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationRunRecord, EvaluationSummary
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import TaskSuite
from sandboxed_agent_eval_harness.tracing import TraceReplay


_METRIC_DEFINITIONS = {
    "evidence_complete_at_5": (
        "Every reference evidence ID is in the top five. Tasks with no reference evidence are excluded."
    ),
    "citation_support": (
        "Citations are distinct, equal the reference set, and occur in the top five. "
        "Empty reference sets require empty citations."
    ),
    "answer_correct": "Verdict, exact value (including null), and unit all match the reference.",
    "strict_pass": "The existing strict evaluation passed.",
}


def write_reader_report(summary: EvaluationSummary, suite: TaskSuite, *, split: str, corpus_version: str,
                        methods: Sequence[str]) -> Path:
    """Require identical search traces and summarize paired scoring outcomes."""
    task_ids = suite.task_ids()
    runs = {(run.baseline_name, run.task_id): run for run in summary.runs}
    expected = {
        (arm, task_id) for method in methods for arm in (method, f"{method}_text_only") for task_id in task_ids
    }
    if len(runs) != len(summary.runs) or runs.keys() != expected:
        raise ValueError("Reader comparison requires one run per task, method, and input arm.")

    draws = lru_cache(maxsize=None)(_cluster_draws)
    method_reports = {}
    for method in methods:
        text_method = f"{method}_text_only"
        retriever, reader = VARIANTS[method]
        outcomes = {metric: [] for metric in _METRIC_DEFINITIONS}
        for task_id in task_ids:
            structured, text_only = runs[method, task_id], runs[text_method, task_id]
            structured_search = _search_trace(structured, retriever, corpus_version)
            text_only_search = _search_trace(text_only, retriever, corpus_version)
            if structured_search != text_only_search:
                raise ValueError(f"Reader comparison search traces differ for {method}/{task_id}.")
            left, right = _outcomes(structured), _outcomes(text_only)
            if left["evidence_complete_at_5"] != right["evidence_complete_at_5"]:
                raise ValueError(f"Evidence completeness differs despite identical retrieval for {method}/{task_id}.")
            group = suite.task_metadata[task_id]["group_id"]
            for metric in outcomes:
                structured_outcome, text_outcome = left[metric], right[metric]
                if structured_outcome is not None and text_outcome is not None:
                    outcomes[metric].append((group, structured_outcome, text_outcome))

        method_reports[method] = {
            "retrieval_method": retriever,
            "reader_method": reader,
            "structured_baseline": method,
            "text_only_baseline": text_method,
            "identical_retrieval_pair_count": len(task_ids),
            "metrics": {metric: _paired_metric(pairs, len(task_ids), draws) for metric, pairs in outcomes.items()},
        }

    report = {
        "benchmark_kind": "synthetic_financial_disclosures",
        "experiment": "reader_input_comparison",
        "split": split,
        "suite_id": suite.suite_id,
        "suite_version": suite.version,
        "corpus_version": corpus_version,
        "task_count": len(task_ids),
        "run_count": len(summary.runs),
        "top_k": 5,
        "identical_retrieval_pair_count": len(task_ids) * len(methods),
        "metric_definitions": _METRIC_DEFINITIONS,
        "uncertainty": {
            "method": "paired_company_group_percentile_bootstrap",
            "confidence_level": 0.95,
            "replicates": _BOOTSTRAP_REPLICATES,
            "seed": _BOOTSTRAP_SEED,
            "interpretation": (
                "Descriptive intervals within the synthetic split, with linked issuers resampled together "
                "and applicable tasks only."
            ),
        },
        "methods": method_reports,
    }
    path = summary.output_dir / "financial_reader_comparison.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return path


def _search_trace(run: EvaluationRunRecord, retriever: str, corpus_version: str) -> tuple[JsonDict, JsonDict]:
    trace = TraceReplay.from_jsonl(run.trace_path)
    calls = trace.events_by_type("tool_call")
    results = trace.events_by_type("tool_result")
    if (trace.metadata.get("run_id") != run.run_id or trace.metadata.get("task_id") != run.task_id
            or len(calls) != 1 or len(results) != 1
            or calls[0].payload.get("tool_name") != "rag.search" or results[0].payload.get("tool_name") != "rag.search"
            or calls[0].sequence >= results[0].sequence):
        raise ValueError(f"Expected one completed rag.search for {run.run_id}.")
    arguments = calls[0].payload["arguments"]
    result = results[0].payload["result"]
    if (arguments.get("top_k") != 5 or result.get("top_k") != 5 or result.get("corpus_version") != corpus_version
            or arguments.get("method") != retriever or result.get("method") != retriever
            or not isinstance(result.get("hits"), list) or len(result["hits"]) > 5):
        raise ValueError(f"Invalid top-five retrieval for {run.run_id}.")
    return arguments, result


def _outcomes(run: EvaluationRunRecord) -> dict[str, bool | None]:
    (score,) = (score for score in run.validator_results if score.validator_name == "financial_benchmark")
    details = score.details
    return {
        "evidence_complete_at_5": not details["missing_evidence_ids"] if details["expected_evidence_ids"] else None,
        "citation_support": details["citation_correct"],
        "answer_correct": all(details[key] for key in ("verdict_correct", "numeric_correct", "unit_correct")),
        "strict_pass": run.passed,
    }


def _paired_metric(pairs: Sequence[tuple[str, bool, bool]], task_count: int,
                   draws: Callable[[int], list[list[int]]]) -> JsonDict:
    counts = Counter((structured, text_only) for _, structured, text_only in pairs)
    groups = defaultdict(list)
    for group, structured, text_only in pairs:
        groups[group].append(text_only - structured)
    blocks = [(sum(groups[group]), len(groups[group])) for group in sorted(groups)]
    both_passed, both_failed = counts[True, True], counts[False, False]
    structured_only, text_only_only = counts[True, False], counts[False, True]
    structured_passed, text_only_passed = both_passed + structured_only, both_passed + text_only_only
    count = len(pairs)
    return {
        "paired_task_count": count,
        "not_applicable_task_count": task_count - count,
        "structured_pass_count": structured_passed,
        "text_only_pass_count": text_only_passed,
        "structured_rate": structured_passed / count if count else None,
        "text_only_rate": text_only_passed / count if count else None,
        "structured_only": structured_only,
        "text_only_only": text_only_only,
        "both_passed": both_passed,
        "both_failed": both_failed,
        "text_only_minus_structured": (text_only_only - structured_only) / count if count else None,
        "text_only_minus_structured_ci95": _cluster_interval(blocks, draws(len(blocks))) if len(blocks) >= 2 else None,
    }
