from dataclasses import replace
import json

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.reader_report import write_reader_report
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer
from sandboxed_agent_eval_harness.evaluation.runner import EvaluationRunRecord, EvaluationSummary
from sandboxed_agent_eval_harness.schemas import TaskSpec
from sandboxed_agent_eval_harness.tasks import TaskSuite
from sandboxed_agent_eval_harness.tracing import TraceLogger


@pytest.fixture
def paired_runs(tmp_path):
    tasks = []
    metadata = {}
    runs = []
    arguments = {"method": "hybrid", "query": "Question", "top_k": 5}
    hits = [{"evidence_id": "e1", "score": 2, "text": "one"}, {"evidence_id": "e2", "score": 1, "text": "two"}]
    result = {"corpus_version": "fixture", "method": "hybrid", "top_k": 5, "hits": hits}
    examples = (
        (["e1", "e2"], "20", "20", ["e1", "e2"], "21", ["e1", "e2"]),
        (["e1"], "20", "20", ["e2"], "20", ["e1"]),
        (["missing"], "20", "20", [], "20", []),
        ([], None, None, [], None, []),
    )
    for i, (evidence, expected, structured_value, structured_citations, text_value, text_citations) in enumerate(examples):
        task_id = f"task-{i}"
        tasks.append(TaskSpec(
            task_id=task_id, domain="financial_benchmark", instruction="Question", available_tools=["rag.search"],
            initial_state={}, hidden_expected_state={}, visible_files=[], success_criteria=["Ground the answer"],
            validator_list=["financial_benchmark"], max_turns=2, max_cost=0.0, timeout_seconds=5,
        ))
        metadata[task_id] = {"group_id": "ACME" if i in (0, 3) else "PEER"}
        verdict = "answer" if evidence else "insufficient"
        label = {"verdict": verdict, "unit": "usd", "answer_value": expected, "evidence_ids": evidence}
        for arm, value, citations in (("hybrid_verified", structured_value, structured_citations),
                                      ("hybrid_verified_text_only", text_value, text_citations)):
            run_id = f"{arm}-{task_id}"
            trace_path = tmp_path / f"{run_id}.jsonl"
            logger = TraceLogger(trace_path, {"run_id": run_id, "task_id": task_id})
            logger.log_tool_call("rag.search", arguments)
            logger.log_tool_result("rag.search", result)
            answer = json.dumps({"verdict": verdict, "unit": "usd", "answer_value": value, "citations": citations})
            score = score_answer(label, answer, hits, 5)
            runs.append(EvaluationRunRecord(run_id, task_id, arm, 0, score.passed, trace_path, [score], {}))
    return EvaluationSummary(runs, {}, {}, tmp_path), TaskSuite("fixture", "1", tasks, metadata)


def test_reader_comparison_counts_each_scoring_dimension(paired_runs):
    summary, suite = paired_runs
    path = write_reader_report(summary, suite, split="test", corpus_version="fixture", methods=("hybrid_verified",))
    report = json.loads(path.read_text())
    assert report["task_count"] == report["identical_retrieval_pair_count"] == 4
    assert report["run_count"] == 8
    method = report["methods"]["hybrid_verified"]
    assert method["retrieval_method"] == "hybrid"
    assert method["reader_method"] == "full_engine"
    scores = method["metrics"]
    evidence = scores["evidence_complete_at_5"]
    assert evidence["structured_rate"] == evidence["text_only_rate"] == 2 / 3
    assert evidence["paired_task_count"] == 3
    assert evidence["not_applicable_task_count"] == 1
    assert evidence["text_only_minus_structured_ci95"] == [0, 0]
    assert scores["citation_support"]["text_only_only"] == 1
    assert scores["citation_support"]["text_only_minus_structured"] == 0.25
    assert scores["answer_correct"]["structured_only"] == 1
    assert scores["answer_correct"]["text_only_minus_structured"] == -0.25
    assert scores["strict_pass"]["structured_only"] == scores["strict_pass"]["text_only_only"] == 1
    assert scores["strict_pass"]["text_only_minus_structured_ci95"] == [-0.5, 0.5]


def test_reader_comparison_rejects_changed_ranking_and_missing_pairs(paired_runs):
    summary, suite = paired_runs
    incomplete = replace(summary, runs=summary.runs[:-1])
    with pytest.raises(ValueError, match="one run per task"):
        write_reader_report(incomplete, suite, split="test", corpus_version="fixture", methods=("hybrid_verified",))

    path = summary.runs[1].trace_path
    call, result = [json.loads(line) for line in path.read_text().splitlines()]
    result["payload"]["result"]["hits"].reverse()
    path.write_text(json.dumps(call) + "\n" + json.dumps(result) + "\n")
    with pytest.raises(ValueError, match="search traces differ"):
        write_reader_report(summary, suite, split="test", corpus_version="fixture", methods=("hybrid_verified",))
