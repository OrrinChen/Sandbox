import json

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.benchmark import FinancialBenchmarkBaseline, task_suite
from sandboxed_agent_eval_harness.schemas import TraceEvent


def test_hybrid_verified_uses_hybrid_top_five_and_checks_source_conflicts():
    suite = task_suite("dev")
    task = next(task for task in suite.tasks if suite.task_metadata[task.task_id]["family"] == "source_conflict")
    hybrid = FinancialBenchmarkBaseline("hybrid")
    candidate = FinancialBenchmarkBaseline("hybrid_verified")
    hybrid_plan, candidate_plan = hybrid.run(task), candidate.run(task)
    assert candidate_plan.tool_calls == hybrid_plan.tool_calls
    assert candidate_plan.tool_calls[0].arguments["top_k"] == 5
    question = task.initial_state["question"]
    operand = question["operands"][0]
    common = {"company_ticker": operand["ticker"], "fiscal_period": operand["period"],
              "metric": operand["metric"], "currency": "USD", "unit": "USD"}
    hits = [{**common, "source_type": source, "evidence_id": f"fact-{i}", "numeric_value": str(i + 1)}
            for i, source in enumerate(question["allowed_source_types"])]
    event = TraceEvent("result", "tool_result", 0, {"tool_name": "rag.search", "result": {"hits": hits}})
    assert json.loads(hybrid.finalize(task, hybrid_plan, [event]).final_answer)["verdict"] == "answer"
    result = json.loads(candidate.finalize(task, candidate_plan, [event]).final_answer)
    assert result == {"verdict": "conflict", "answer_value": None, "unit": question["unit"],
                      "citations": [hit["evidence_id"] for hit in hits]}
