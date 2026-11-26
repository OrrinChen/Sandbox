"""Compare benchmark methods on the same questions within a single split."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
from random import Random
from statistics import mean, quantiles
from typing import Sequence

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.variants import FINANCIAL_METHODS, VARIANTS
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationRunRecord, EvaluationSummary
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import TaskSuite


_BOOTSTRAP_SEED = 20261113
_BOOTSTRAP_REPLICATES = 2_000


def write_report(summary: EvaluationSummary, suite: TaskSuite, *, split: str, corpus_version: str,
                 methods: Sequence[str] = FINANCIAL_METHODS) -> Path:
    """Write rates and task-paired comparisons with company-level resampling."""
    task_ids = suite.task_ids()
    families = defaultdict(list)
    groups = defaultdict(list)
    companies = set()
    for task in suite.tasks:
        question = task.initial_state["question"]
        metadata = suite.task_metadata[task.task_id]
        families[metadata["family"]].append(task.task_id)
        companies.update(question["company_tickers"])
        group = metadata["group_id"] if "group_id" in metadata else question["company_tickers"][0]
        groups[group].append(task.task_id)

    runs = {(run.baseline_name, run.task_id): run for run in summary.runs}
    expected = {(method, task_id) for method in methods for task_id in task_ids}
    if len(runs) != len(summary.runs) or runs.keys() != expected:
        raise ValueError("A paired comparison requires one run per task for each financial benchmark method.")

    draws = _cluster_draws(len(groups))
    comparisons = []
    for left, right in combinations(methods, 2):
        left_wins = right_wins = both_passed = both_failed = 0
        blocks = []
        for group in sorted(groups):
            block = groups[group]
            block_delta = 0
            for task_id in block:
                left_passed = runs[left, task_id].passed
                right_passed = runs[right, task_id].passed
                left_wins += left_passed and not right_passed
                right_wins += right_passed and not left_passed
                both_passed += left_passed and right_passed
                both_failed += not left_passed and not right_passed
                block_delta += left_passed - right_passed
            blocks.append((block_delta, len(block)))
        delta = (left_wins - right_wins) / len(task_ids)
        comparisons.append({
            "left_method": left,
            "right_method": right,
            "paired_task_count": len(task_ids),
            "left_wins": left_wins,
            "right_wins": right_wins,
            "both_passed": both_passed,
            "both_failed": both_failed,
            "strict_pass_rate_delta": delta,
            "strict_pass_rate_absolute_delta": abs(delta),
            "strict_pass_rate_delta_ci95": _cluster_interval(blocks, draws),
        })

    report = {
        "benchmark_kind": "synthetic_financial_disclosures",
        "split": split,
        "suite_id": suite.suite_id,
        "suite_version": suite.version,
        "corpus_version": corpus_version,
        "task_count": len(task_ids),
        "run_count": len(summary.runs),
        "company_group_count": len(companies),
        "bootstrap_group_count": len(groups),
        "top_k": 5,
        "primary_metric": "strict_pass_rate",
        "uncertainty": {
            "method": "paired_company_group_percentile_bootstrap",
            "confidence_level": 0.95,
            "replicates": _BOOTSTRAP_REPLICATES,
            "seed": _BOOTSTRAP_SEED,
            "interpretation": "Descriptive uncertainty within this synthetic split. Linked issuers share a resampling block. Pairwise intervals are unadjusted.",
        },
        "methods": {
            method: {
                "retrieval_method": VARIANTS[method][0],
                "reader_method": VARIANTS[method][1],
                **_rates([runs[method, task_id] for task_id in task_ids]),
                "by_family": {
                    family: _rates([runs[method, task_id] for task_id in members])
                    for family, members in sorted(families.items())
                },
            }
            for method in methods
        },
        "paired_comparisons": comparisons,
    }
    path = summary.output_dir / "financial_benchmark_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return path


def _rates(runs: Sequence[EvaluationRunRecord]) -> JsonDict:
    details = [next(score.details for score in run.validator_results if score.validator_name == "financial_benchmark") for run in runs]
    recall = [score["evidence_recall_at_k"] for score in details if score["evidence_recall_at_k"] is not None]
    abstentions = [score["abstention_correct"] for score in details if score["abstention_expected"]]
    return {
        "task_count": len(runs),
        "passed_count": sum(run.passed for run in runs),
        "strict_pass_rate": mean(run.passed for run in runs),
        "evidence_recall_at_5": mean(recall) if recall else None,
        "evidence_recall_task_count": len(recall),
        "citation_correctness": mean(score["citation_correct"] for score in details),
        "verdict_accuracy": mean(score["verdict_correct"] for score in details),
        "abstention_accuracy": mean(score["abstention_correct"] for score in details),
        "expected_abstention_accuracy": mean(abstentions) if abstentions else None,
        "expected_abstention_task_count": len(abstentions),
        "failure_taxonomy": dict(Counter(failure for score in details for failure in score["failure_types"])),
    }


def _cluster_draws(group_count: int) -> list[list[int]]:
    random = Random(_BOOTSTRAP_SEED)
    return [random.choices(range(group_count), k=group_count) for _ in range(_BOOTSTRAP_REPLICATES)]


def _cluster_interval(blocks: Sequence[tuple[int, int]], draws: Sequence[Sequence[int]]) -> list[float] | None:
    if len(blocks) < 2:
        return None
    rates = []
    for draw in draws:
        delta = size = 0
        for index in draw:
            block_delta, block_size = blocks[index]
            delta += block_delta
            size += block_size
        rates.append(delta / size)
    percentiles = quantiles(rates, n=40, method="inclusive")
    return [percentiles[0], percentiles[-1]]
