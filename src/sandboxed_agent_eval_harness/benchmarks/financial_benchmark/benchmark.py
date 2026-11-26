"""Run the frozen financial tasks with the shared Sandbox retrieval methods."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Literal, Mapping, Sequence

from sandboxed_agent_eval_harness.agents import AgentBaseline, AgentRunPlan, PlannedToolCall
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.data import CROSS_SOURCE_SPLITS, load_corpus, load_manifest, load_questions
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.reader import read_answer
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.report import write_report
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.variants import FINANCIAL_METHODS, SPLIT_METHOD, VARIANTS
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationSummary, run_evaluation
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec, TraceEvent
from sandboxed_agent_eval_harness.tasks import TaskSuite
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor


READER_COMPARISON_PROMPTS = {
    "structured": "financial-benchmark-reader-comparison-structured-v1",
    "text_only": "financial-benchmark-reader-comparison-text-only-v1",
}
TEXT_ONLY_SUFFIX = "_text_only"


def task_suite(split: str) -> TaskSuite:
    challenge = split == "challenge"
    cross_source = split in CROSS_SOURCE_SPLITS
    corpus_version = load_corpus(split=split)["version"]
    tool_version = "financial-cross-source-search-v1" if cross_source else (
        "financial-challenge-search-v1" if challenge else "financial-benchmark-search-v1"
    )
    questions = load_questions(split)
    tasks = [
        TaskSpec(
            task_id=question["task_id"],
            domain="financial_benchmark",
            instruction=question["question"],
            available_tools=["rag.search"],
            initial_state={"question": {key: value for key, value in question.items() if key not in {"family", "task_id"}},
                           "split": split, "fixture_version": corpus_version,
                           "tool_version": tool_version},
            hidden_expected_state={},
            visible_files=[],
            success_criteria=["Answer using the requested units and cite only the relevant retrieved evidence."],
            validator_list=["financial_benchmark"],
            max_turns=2,
            max_cost=0,
            timeout_seconds=5,
        )
        for question in questions
    ]
    manifest = load_manifest(split=split)
    groups = manifest["company_pair_groups"]
    metadata = {q["task_id"]: {"family": q["family"], "group_id": groups[q["company_tickers"][0]]} for q in questions}
    return TaskSuite(f"financial-benchmark-{split}", manifest["dataset_version"], tasks, metadata)


class FinancialBenchmarkBaseline(AgentBaseline):
    model = "deterministic-financial-reader"
    prompt_version = "financial-benchmark-reader-v1"

    def __init__(self, method: str, *, reader_arm: Literal["structured", "text_only"] | None = None) -> None:
        self.reader_arm = reader_arm
        self.name = method + TEXT_ONLY_SUFFIX if reader_arm == "text_only" else method
        self.retrieval_method, self.reader_method = VARIANTS[method]
        if reader_arm is not None:
            self.prompt_version = READER_COMPARISON_PROMPTS[reader_arm]

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        question = task.initial_state["question"]
        split = task.initial_state["split"]
        challenge = split == "challenge"
        cross_source = split in CROSS_SOURCE_SPLITS
        query = question["question"] if challenge or cross_source else " ".join((
            question["question"], *question["company_tickers"], *question["fiscal_periods"],
        ))
        arguments = {
            "corpus": split if cross_source else ("financial-challenge" if challenge else "financial-benchmark"),
            "method": self.retrieval_method,
            "query": query,
            "top_k": 5,
            "tickers": question["company_tickers"],
            "fiscal_periods": question["fiscal_periods"],
            "source_types": question["allowed_source_types"],
        }
        return AgentRunPlan(
            agent_name=self.name, final_answer="", tool_calls=[PlannedToolCall("rag.search", arguments, {})],
            reported_metrics={}, state_diff={}, turns=2, latency_seconds=0, cost=0, final_answer_passed=False,
        )

    def finalize(self, task: TaskSpec, plan: AgentRunPlan, tool_results: Sequence[TraceEvent]) -> AgentRunPlan:
        hits = tool_results[0].payload["result"]["hits"] if tool_results else []
        if self.reader_arm == "text_only":
            from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.text_reader import read_text_answer

            snippets = [(hit["evidence_id"], hit["text"]) for hit in hits]
            answer = read_text_answer(task.instruction, snippets, method=self.reader_method)
        else:
            answer = read_answer(task.initial_state["question"], hits, method=self.reader_method)
        return replace(plan, final_answer=answer)


class _SharedFinancialSearch(FixtureToolExecutor):
    """Reuse each validated, read-only search result within a reader comparison."""

    def __init__(self) -> None:
        super().__init__()
        self._results: dict[str, JsonDict] = {}

    def _rag_search(self, arguments: JsonDict) -> JsonDict:
        key = json.dumps(arguments, sort_keys=True)
        if key not in self._results:
            self._results[key] = super()._rag_search(arguments)
        return deepcopy(self._results[key])


def comparison_baseline(metadata: Mapping) -> FinancialBenchmarkBaseline | None:
    """Resolve the reader policy recorded in a comparison trace."""
    version = metadata.get("prompt_version")
    name = metadata.get("agent_id")
    if version not in READER_COMPARISON_PROMPTS.values():
        if isinstance(name, str) and name.endswith(TEXT_ONLY_SUFFIX):
            raise ValueError("unrecognized text-only reader comparison version")
        return None
    text_only = version == READER_COMPARISON_PROMPTS["text_only"]
    if not isinstance(name, str) or name.endswith(TEXT_ONLY_SUFFIX) != text_only:
        raise ValueError("reader comparison trace arm does not match its baseline name")
    method = name.removesuffix(TEXT_ONLY_SUFFIX) if text_only else name
    if method not in VARIANTS:
        raise ValueError("unknown financial reader comparison baseline")
    return FinancialBenchmarkBaseline(method, reader_arm="text_only" if text_only else "structured")


def run_benchmark(split: str, output_dir: Path, *, compare_readers: bool = False) -> EvaluationSummary:
    suite = task_suite(split)
    methods = (*FINANCIAL_METHODS, SPLIT_METHOD) if split in CROSS_SOURCE_SPLITS else FINANCIAL_METHODS
    corpus_version = load_corpus(split=split)["version"]
    if compare_readers:
        from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.reader_report import write_reader_report

        baselines = [FinancialBenchmarkBaseline(method, reader_arm=arm)
                     for method in methods for arm in ("structured", "text_only")]
        summary = run_evaluation(suite=suite, baselines=baselines, output_dir=output_dir,
                                 executor=_SharedFinancialSearch())
        write_reader_report(summary, suite, split=split, corpus_version=corpus_version, methods=methods)
        return summary
    summary = run_evaluation(suite=suite, baselines=[FinancialBenchmarkBaseline(method) for method in methods], output_dir=output_dir)
    write_report(summary, suite, split=split, corpus_version=corpus_version, methods=methods)
    return summary
