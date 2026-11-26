"""Run the complete A1 seed suite using only public inputs at inference time."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
from typing import Sequence

from sandboxed_agent_eval_harness.agents import AgentBaseline, AgentRunPlan, PlannedToolCall
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.answer import build_answer
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_data import load_full_corpus, load_questions
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationSummary, run_evaluation
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec, TraceEvent
from sandboxed_agent_eval_harness.tasks import TaskSuite


_TOOL_VERSION = "a1-rag-search-v3"


def full_task_suite() -> TaskSuite:
    questions = load_questions()
    corpus_version = load_full_corpus()["version"]
    tasks = [
        TaskSpec(
            task_id=public["task_id"],
            domain="financial_evidence",
            instruction=public["question"],
            available_tools=["rag.search"],
            initial_state={"question": public, "fixture_version": corpus_version, "tool_version": _TOOL_VERSION},
            hidden_expected_state={},
            visible_files=[],
            success_criteria=["Find and cite evidence for the financial claim and return a verdict."],
            validator_list=["a1_rag"],
            max_turns=2,
            max_cost=0.0,
            timeout_seconds=5,
        )
        for public in questions["tasks"].values()
    ]
    return TaskSuite(questions["task_set_id"], questions["version"], tasks, {task.task_id: {} for task in tasks})


class FullFinancialEvidenceBaseline(AgentBaseline):
    """Retrieve evidence for one A1 method and answer from the returned hits."""

    model = "deterministic-a1-rag"
    prompt_version = "a1-rag-full-v3"

    def __init__(self, method: str, top_k: int = 5) -> None:
        self.name = method
        self.top_k = top_k

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        question = task.initial_state["question"]
        query = " ".join((
            question["claim_text"], question["question"],
            *question["company_tickers"], *question["fiscal_periods"],
        ))
        arguments = {
            "method": self.name,
            "query": query,
            "top_k": self.top_k,
            "tickers": question["company_tickers"],
            "fiscal_periods": question["fiscal_periods"],
            "source_types": question["allowed_source_types"],
        }
        return AgentRunPlan(
            agent_name=self.name,
            final_answer="",
            tool_calls=[PlannedToolCall("rag.search", arguments, {})],
            reported_metrics={},
            state_diff={},
            turns=2,
            latency_seconds=0.0,
            cost=0.0,
            final_answer_passed=False,
        )

    def finalize(self, task: TaskSpec, plan: AgentRunPlan, tool_results: Sequence[TraceEvent]) -> AgentRunPlan:
        hits = tool_results[0].payload["result"]["hits"] if tool_results else []
        answer = build_answer(task.initial_state["question"], hits, method=self.name)
        return replace(plan, final_answer=answer)


def run_full_benchmark(output_dir: Path, methods: Sequence[str]) -> EvaluationSummary:
    from sandboxed_agent_eval_harness.benchmarks.financial_evidence.scoring import (
        corpus_evidence_coverage,
        corpus_reference_conflicts,
    )

    suite = full_task_suite()
    baselines = [FullFinancialEvidenceBaseline(method) for method in methods]
    summary = run_evaluation(suite=suite, baselines=baselines, output_dir=output_dir)
    corpus = load_full_corpus()
    report = {
        "task_set_id": suite.suite_id,
        "task_version": suite.version,
        "prompt_version": FullFinancialEvidenceBaseline.prompt_version,
        "tool_version": _TOOL_VERSION,
        "corpus_version": corpus["version"],
        "upstream_commit": corpus["provenance"]["commit"],
        "task_count": len(suite.tasks),
        "run_count": len(summary.runs),
        "corpus_documents": len(corpus["documents"]),
        "corpus_coverage": corpus_evidence_coverage(corpus["documents"]),
        "corpus_reference_conflicts": corpus_reference_conflicts(
            [task.initial_state["question"] for task in suite.tasks], corpus["documents"],
        ),
        "top_k": baselines[0].top_k,
        "methods": {
            method: _method_report(summary, method)
            for method in methods
        },
    }
    (output_dir / "rag_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _method_report(summary: EvaluationSummary, method: str) -> JsonDict:
    runs = [run for run in summary.runs if run.baseline_name == method]
    scores = [result.details for run in runs for result in run.validator_results if result.validator_name == "a1_rag"]
    total = sum(score["evidence_requirements_total"] for score in scores)
    failure_counts = Counter(failure for score in scores for failure in score["failure_types"])
    gaps = Counter({"corpus_only": 0, "top_k_only": 0, "both": 0, "evidence_complete": 0})
    absent_total = 0
    outside_total = 0
    for score in scores:
        absent = score["absent_from_corpus_requirement_ids"]
        outside = score["outside_top_k_requirement_ids"]
        absent_total += len(absent)
        outside_total += len(outside)
        if absent and outside:
            gaps["both"] += 1
        elif absent:
            gaps["corpus_only"] += 1
        elif outside:
            gaps["top_k_only"] += 1
        else:
            gaps["evidence_complete"] += 1
    return {
        "task_count": len(runs),
        "passed_count": sum(run.passed for run in runs),
        "evidence_recall_at_k": sum(score["evidence_requirements_matched"] for score in scores) / total,
        "citation_exactness": sum(score["citation_requirements_matched"] for score in scores) / total,
        "verdict_accuracy": sum(score["verdict_correct"] for score in scores) / len(runs),
        "numeric_checks_scored": sum(score["numeric_checks_scored"] for score in scores),
        "numeric_checks_total": sum(score["numeric_checks_total"] for score in scores),
        "failure_taxonomy": dict(failure_counts),
        "evidence_gap_runs": dict(gaps),
        "absent_from_corpus_requirements": absent_total,
        "outside_top_k_requirements": outside_total,
    }
