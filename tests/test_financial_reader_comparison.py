from collections import Counter
from dataclasses import replace
import json

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark import benchmark, data, scoring, text_reader
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.variants import FINANCIAL_METHODS, VARIANTS
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor
from sandboxed_agent_eval_harness.tracing import TraceReplay, TraceReplayExecutor


def test_text_reader_boundary_passes_only_question_and_ordered_raw_snippets(monkeypatch):
    task = benchmark.task_suite("dev").tasks[0]
    baseline = benchmark.FinancialBenchmarkBaseline("hybrid_verified", reader_arm="text_only")
    plan = baseline.run(task)
    hits = [{"evidence_id": "z", "text": "first", "numeric_value": "999", "score": 3},
            {"evidence_id": "a", "text": "second", "source_type": "filing", "score": 1}]
    event = TraceEvent("result", "tool_result", 0, {"tool_name": "rag.search", "result": {"hits": hits}})

    def read(question, snippets, *, method):
        assert type(question) is str and question == task.instruction
        assert snippets == [("z", "first"), ("a", "second")]
        assert method == "full_engine"
        return "raw answer"

    def deny_labels(*args, **kwargs):
        raise AssertionError("reader tried to access labels")

    resource = data._resource

    def public_resource(name):
        assert not name.endswith("_labels")
        return resource(name)

    monkeypatch.setattr(scoring, "load_labels", deny_labels)
    monkeypatch.setattr(data, "_resource", public_resource)
    with monkeypatch.context() as boundary:
        boundary.setattr(text_reader, "read_text_answer", read)
        assert baseline.finalize(task, plan, [event]).final_answer == "raw answer"

    executor = FixtureToolExecutor()
    result = executor._rag_search(plan.tool_calls[0].arguments)
    real_event = replace(event, payload={"tool_name": "rag.search", "result": result})
    structured = benchmark.FinancialBenchmarkBaseline("hybrid_verified", reader_arm="structured")
    for arm in (baseline, structured):
        answer = arm.finalize(task, arm.run(task), [real_event]).final_answer
        assert json.loads(answer)["verdict"] in ("answer", "conflict", "insufficient")


def test_comparison_shares_search_and_replay_regenerates_answer(tmp_path, monkeypatch):
    full_suite = benchmark.task_suite("dev")
    tasks = [full_suite.tasks[0], full_suite.tasks[-1]]
    suite = replace(full_suite, tasks=tasks)
    monkeypatch.setattr(benchmark, "task_suite", lambda split: suite)
    calls = Counter()
    search = FixtureToolExecutor._rag_search

    def count_search(executor, arguments):
        calls[json.dumps(arguments, sort_keys=True)] += 1
        return search(executor, arguments)

    monkeypatch.setattr(FixtureToolExecutor, "_rag_search", count_search)
    summary = benchmark.run_benchmark("dev", tmp_path, compare_readers=True)
    assert len(summary.runs) == 2 * len(tasks) * len(FINANCIAL_METHODS)
    assert len(calls) == len(tasks) * len({VARIANTS[method][0] for method in FINANCIAL_METHODS})
    assert set(calls.values()) == {1}
    report = json.loads((tmp_path / "financial_reader_comparison.json").read_text())
    assert report["identical_retrieval_pair_count"] == len(summary.runs) // 2

    executor = TraceReplayExecutor(suite=suite)
    for suffix in ("", "_text_only"):
        run = next(run for run in summary.runs if run.baseline_name == f"hybrid_verified{suffix}")
        assert executor.replay(run.trace_path, tmp_path / "replay" / f"original{suffix}").passed
        events = TraceReplay.from_jsonl(run.trace_path).events
        answer = next(event for event in events if event.event_type == "final_answer")
        answer.payload["content"] += " "
        edited_trace = tmp_path / f"edited{suffix}.jsonl"
        edited_trace.write_text("\n".join(event.to_json_line() for event in events) + "\n")
        replay = executor.replay(edited_trace, tmp_path / "replay" / f"edited{suffix}")
        assert [divergence["type"] for divergence in replay.divergences] == ["reader_answer_mismatch"]
