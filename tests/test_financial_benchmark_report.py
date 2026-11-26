import json
from dataclasses import replace
from itertools import combinations

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.report import write_report
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.variants import FINANCIAL_METHODS
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationRunRecord, EvaluationSummary
from sandboxed_agent_eval_harness.schemas import TaskSpec, ValidatorResult
from sandboxed_agent_eval_harness.tasks import TaskSuite


@pytest.fixture
def comparison(tmp_path):
    tasks = []
    runs = []
    metadata = {}
    for company in ("ACME", "PEER"):
        for family in ("single_source", "insufficient"):
            task_id = f"{company}-{family}"
            tasks.append(TaskSpec(
                task_id=task_id, domain="financial_benchmark", instruction="Question",
                available_tools=["rag.search"],
                initial_state={"question": {"company_tickers": [company if family == "single_source" else f"{company}-PEER"]}},
                hidden_expected_state={}, visible_files=[], success_criteria=["Ground the answer"],
                validator_list=["financial_benchmark"], max_turns=2, max_cost=0.0, timeout_seconds=5,
            ))
            metadata[task_id] = {"family": family, "group_id": company}
            for method in FINANCIAL_METHODS:
                expected_abstention = family == "insufficient"
                passed = (company == "ACME" if method == "bm25" else company == "PEER" and not expected_abstention)
                if method == "hybrid_verified":
                    passed = company == "ACME" or not expected_abstention
                score = ValidatorResult(
                    "financial_benchmark", passed, "Test result", failure_type=None if passed else "test_failure",
                    details={
                        "evidence_recall_at_k": None if expected_abstention else float(passed),
                        "citation_correct": passed, "verdict_correct": passed,
                        "abstention_expected": expected_abstention,
                        "abstention_correct": not expected_abstention or passed,
                        "failure_types": [] if passed else ["test_failure"],
                    },
                )
                runs.append(EvaluationRunRecord(
                    f"{method}-{task_id}", task_id, method, 0, passed, tmp_path / "trace.jsonl", [score], {},
                ))
    suite = TaskSuite("test-financial", "1", tasks, metadata)
    return EvaluationSummary(runs, {}, {}, tmp_path), suite


def test_paired_report_keeps_company_clusters_together(comparison):
    summary, suite = comparison
    path = write_report(summary, suite, split="test", corpus_version="test-corpus")
    report = json.loads(path.read_text())
    original_methods = ("bm25", "dense_proxy", "hybrid", "graph", "full_engine")
    expected_methods = (*original_methods, "hybrid_verified")
    pairs = {(row["left_method"], row["right_method"]): row for row in report["paired_comparisons"]}
    assert len(report["paired_comparisons"]) == 15
    assert set(pairs) == set(combinations(expected_methods, 2))
    assert report["company_group_count"] == 4
    assert report["bootstrap_group_count"] == 2
    assert report["task_count"] == 4
    assert report["run_count"] == 24
    first = pairs["bm25", "dense_proxy"]
    assert first["left_wins"] == 2
    assert first["right_wins"] == 1
    assert first["both_passed"] == 0
    assert first["both_failed"] == 1
    assert first["strict_pass_rate_delta"] == 0.25
    assert first["strict_pass_rate_absolute_delta"] == 0.25
    # The only resamples are two ACME groups, two PEER groups, or one of each.
    assert first["strict_pass_rate_delta_ci95"] == [-0.5, 1.0]

    candidate = pairs["hybrid", "hybrid_verified"]
    assert candidate["left_wins"] == 0
    assert candidate["right_wins"] == 2
    assert candidate["both_passed"] == candidate["both_failed"] == 1
    assert candidate["strict_pass_rate_delta"] == -0.5
    assert candidate["strict_pass_rate_delta_ci95"] == [-1.0, 0.0]

    bm25 = report["methods"]["bm25"]
    assert bm25["strict_pass_rate"] == bm25["citation_correctness"] == 0.5
    assert bm25["expected_abstention_task_count"] == 2
    assert bm25["expected_abstention_accuracy"] == 0.5
    assert bm25["abstention_accuracy"] == 0.75
    assert bm25["failure_taxonomy"] == {"test_failure": 2}
    assert bm25["by_family"]["insufficient"]["evidence_recall_at_5"] is None
    assert bm25["by_family"]["single_source"]["expected_abstention_accuracy"] is None
    methods = report["methods"]
    assert set(methods) == set(expected_methods)
    assert {name: (methods[name]["retrieval_method"], methods[name]["reader_method"]) for name in original_methods} == {
        name: (name, name) for name in original_methods
    }
    assert methods["hybrid_verified"]["retrieval_method"] == "hybrid"
    assert methods["hybrid_verified"]["reader_method"] == "full_engine"
    assert json.loads(write_report(summary, suite, split="test", corpus_version="test-corpus").read_text()) == report


@pytest.mark.parametrize("repeats", [False, True])
def test_report_rejects_incomplete_or_duplicate_pairs(comparison, repeats):
    summary, suite = comparison
    incomplete = summary.runs[:-1]
    malformed = replace(summary, runs=incomplete + [incomplete[0]] if repeats else incomplete)
    with pytest.raises(ValueError, match="one run per task"):
        write_report(malformed, suite, split="test", corpus_version="test-corpus")
