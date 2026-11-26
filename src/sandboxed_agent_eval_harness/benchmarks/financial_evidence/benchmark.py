"""Offline regression cases built from A1 financial evidence fixtures."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from sandboxed_agent_eval_harness.agents import AgentBaseline, AgentRunPlan, PlannedToolCall
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.retrieval import load_corpus
from sandboxed_agent_eval_harness.schemas import TaskSpec, TraceEvent
from sandboxed_agent_eval_harness.tasks import TaskSuite


_QUESTION = "What was Apple's FY2024 annual revenue in USD? Cite the source."
_ANNUAL_ID = "aapl-fy2024-revenue"
_QUARTER_ID = "aapl-q4-fy2024-revenue"


def rag_task_suite() -> TaskSuite:
    corpus_version = load_corpus()["version"]
    annual_query = "Apple AAPL FY2024 annual revenue"
    cases = (
        ("grounded", annual_query, "", "correct evidence and citation"),
        ("retrieval-miss", "Apple AAPL Q4 FY2024 quarterly revenue", "", "quarterly evidence for an annual question"),
        ("invalid-citation", annual_query, _QUARTER_ID, "citation points to evidence absent from the tool results"),
    )
    tasks = []
    metadata = {}
    for case_id, query, citation_override, trap in cases:
        task_id = f"rag-aapl-revenue-{case_id}"
        tasks.append(TaskSpec(
            task_id=task_id,
            domain="financial_evidence",
            instruction=_QUESTION,
            available_tools=["rag.search"],
            initial_state={"query": query, "citation_override": citation_override, "fixture_version": corpus_version},
            hidden_expected_state={"evidence_ids": [_ANNUAL_ID]},
            visible_files=[],
            success_criteria=["Retrieve and cite Apple's annual FY2024 revenue evidence."],
            validator_list=["rag_grounding"],
            max_turns=2,
            max_cost=0.0,
            timeout_seconds=5,
        ))
        metadata[task_id] = {
            "gold_outputs": {"citations": [_ANNUAL_ID]},
            "known_failure_traps": [trap],
            "final_answer_only_risk": True,
        }
    return TaskSuite("a1-rag-benchmark", "a1-rag-tasks-v1", tasks, metadata)


class FinancialEvidenceBaseline(AgentBaseline):
    """Deterministic response to live local search results with scripted regressions."""

    name = "a1-bm25"
    model = "deterministic-extractive"
    prompt_version = "a1-rag-v1"

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        return AgentRunPlan(
            agent_name=self.name,
            final_answer="",
            tool_calls=[PlannedToolCall("rag.search", {"query": task.initial_state["query"], "top_k": 1}, {})],
            reported_metrics={},
            state_diff={},
            turns=2,
            latency_seconds=0.0,
            cost=0.0,
            final_answer_passed=False,
        )

    def finalize(self, task: TaskSpec, plan: AgentRunPlan, tool_results: Sequence[TraceEvent]) -> AgentRunPlan:
        hits = tool_results[0].payload["result"]["hits"] if tool_results else []
        if not hits:
            return replace(plan, final_answer="No revenue evidence was returned.")
        hit = hits[0]
        citation = task.initial_state["citation_override"] or hit["evidence_id"]
        answer = f"Apple's FY2024 annual revenue was {hit['value']} {hit['unit']} [{citation}]."
        return replace(plan, final_answer=answer, final_answer_passed=True)
