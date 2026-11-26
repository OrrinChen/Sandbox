from collections import Counter
import json
from pathlib import Path

from sandboxed_agent_eval_harness.benchmarks.financial_evidence import full_data
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_benchmark import (
    FullFinancialEvidenceBaseline,
    full_task_suite,
)
from sandboxed_agent_eval_harness.cli import main
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor
from sandboxed_agent_eval_harness.tracing import load_trace_events


METHOD_NAMES = ("bm25", "dense_proxy", "hybrid", "graph", "full_engine")
TICKERS = ("aapl", "msft", "nvda", "amzn", "googl", "meta", "jpm", "wmt", "tsla", "nflx")
TASK_FAMILIES = (
    "single_company_trend", "cross_company_comparison", "management_claim_verification",
    "risk_contradiction", "guidance_vs_actuals", "chart_table_reconciliation",
)


def test_full_a1_cli_runs_every_method_and_replays_a_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["rag-benchmark", "--output-dir", "a1"]) == 0
    capsys.readouterr()
    summary = json.loads(Path("a1/summary.json").read_text())
    runs = summary["runs"]
    task_ids = {f"phase6:{ticker}:{family}" for ticker in TICKERS for family in TASK_FAMILIES}
    assert len(runs) == 300
    assert {(run["task_id"], run["baseline_name"]) for run in runs} == {
        (task_id, method) for task_id in task_ids for method in METHOD_NAMES
    }

    rankings = {method: {} for method in METHOD_NAMES}
    for run in runs:
        events = load_trace_events(run["trace_path"])
        (retrieval,) = [event.payload["result"] for event in events if event.event_type == "tool_result"]
        assert retrieval["method"] == run["baseline_name"]
        assert retrieval["top_k"] == 5
        rankings[run["baseline_name"]][run["task_id"]] = tuple(hit["evidence_id"] for hit in retrieval["hits"])
        assert run["validator_results"][0]["validator_name"] == "a1_rag"
    assert len({json.dumps(rankings[method], sort_keys=True) for method in METHOD_NAMES}) == 4
    assert rankings["graph"] == rankings["full_engine"]

    report = json.loads(Path("a1/rag_report.json").read_text())
    assert set(report["methods"]) == set(METHOD_NAMES)
    assert report["corpus_coverage"]["evidence_requirements_available"] == 140
    assert report["corpus_coverage"]["evidence_requirements_total"] == 200
    assert len(report["corpus_reference_conflicts"]) == 9
    for method in report["methods"].values():
        assert sum(method["evidence_gap_runs"].values()) == 60
        assert method["absent_from_corpus_requirements"] == 60

    comparisons = {
        run["task_id"]: run for run in runs
        if run["baseline_name"] == "full_engine" and run["task_id"].endswith(":cross_company_comparison")
    }
    assert len(comparisons) == report["corpus_coverage"]["fully_covered_tasks"] == 10
    supported_task = "phase6:nflx:cross_company_comparison"
    assert {item["task_id"] for item in report["corpus_reference_conflicts"]} == comparisons.keys() - {supported_task}
    for task_id, run in comparisons.items():
        score = run["validator_results"][0]["details"]
        assert score["absent_from_corpus_requirement_ids"] == []
        assert score["outside_top_k_requirement_ids"] == []
        assert score["evidence_requirements_matched"] == score["evidence_requirements_total"] == 4
        assert score["citation_requirements_matched"] == len(score["citations"]) == 4
        assert score["invalid_citations"] == []
        assert score["expected_verdict"] == "support"
        if task_id == supported_task:
            assert score["predicted_verdict"] == "support"
            assert score["failure_types"] == []
            assert run["passed"] is True
        else:
            assert score["predicted_verdict"] == "contradict"
            assert score["failure_types"] == ["a1_verdict_mismatch"]
            assert run["passed"] is False

    failed_run = comparisons["phase6:aapl:cross_company_comparison"]
    trace = failed_run["trace_path"]
    assert main(["replay", trace, "--workspace", "replay"]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["passed"] is True
    assert replay["replayed_tool_calls"] == 1
    assert replay["divergences"] == []
    assert replay["validator_results"] == failed_run["validator_results"]

    events = [event.to_dict() for event in load_trace_events(trace)]
    verdict = next(event["payload"] for event in events if event["event_type"] == "validator_result")
    verdict.update(passed=True, failure_type=None)
    Path("tampered.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
    assert main(["replay", "tampered.jsonl", "--workspace", "replay"]) == 1
    tampered = json.loads(capsys.readouterr().out)
    assert tampered["validator_results"] == failed_run["validator_results"]
    assert [item["type"] for item in tampered["divergences"]] == ["validator_result_mismatch"]


def test_a1_retrieval_and_answer_do_not_load_scoring_labels(tmp_path, monkeypatch):
    read = full_data._load
    opened_resources = Counter()

    def read_public_only(name):
        assert name != "a1_labels.json", "Scoring labels were accessed during inference"
        opened_resources[name] += 1
        return read(name)

    monkeypatch.setattr(full_data, "_load", read_public_only)
    suite = full_task_suite()
    task = next(task for task in suite.tasks if task.task_id == "phase6:nflx:cross_company_comparison")
    assert all(not task.hidden_expected_state for task in suite.tasks)
    executor = FixtureToolExecutor()
    workspace = executor.create_sandbox(task, tmp_path / "workspace")

    for method in METHOD_NAMES:
        baseline = FullFinancialEvidenceBaseline(method)
        plan = baseline.run(task)
        (call,) = plan.tool_calls
        assert set(call.arguments) == {"method", "query", "top_k", "tickers", "fiscal_periods", "source_types"}
        result = executor.execute(call.tool_name, call.arguments, workspace)
        assert result["hits"]
        for hit in result["hits"]:
            assert {"evidence_id", "text", "company_ticker", "fiscal_period", "score"} <= hit.keys()
            assert not {"is_distractor", "distractor_reason", "requirement_id", "expected_verdict"} & hit.keys()
        observation = TraceEvent("test-result", "tool_result", 0, {"tool_name": call.tool_name, "result": result})
        answer = json.loads(baseline.finalize(task, plan, [observation]).final_answer)
        assert answer["verdict"] in {"support", "contradict", "insufficient"}
        assert set(answer["citations"]) <= {hit["evidence_id"] for hit in result["hits"]}

    assert set(opened_resources) == {"a1_questions.json", "a1_raw_corpus.json"}
