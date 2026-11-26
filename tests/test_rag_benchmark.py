import json
from pathlib import Path

import pytest

from sandboxed_agent_eval_harness.cli import main
from sandboxed_agent_eval_harness.tracing import load_trace_events


@pytest.fixture
def rag_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "evaluation"
    assert main(["rag-benchmark", "--smoke", "--output-dir", str(output_dir)]) == 0
    capsys.readouterr()
    return json.loads((output_dir / "summary.json").read_text())


def test_rag_benchmark_replays_both_failures(rag_summary, tmp_path, capsys):
    expected = {
        "rag-aapl-revenue-grounded": ("aapl-fy2024-revenue", set()),
        "rag-aapl-revenue-retrieval-miss": ("aapl-q4-fy2024-revenue", {"rag_retrieval_miss"}),
        "rag-aapl-revenue-invalid-citation": ("aapl-fy2024-revenue", {"rag_invalid_citation"}),
    }
    assert sorted(run["task_id"] for run in rag_summary["runs"]) == sorted(expected)
    assert rag_summary["metrics"]["failure_taxonomy"] == {
        "rag_invalid_citation": 1,
        "rag_retrieval_miss": 1,
    }

    for run in rag_summary["runs"]:
        evidence_id, failures = expected[run["task_id"]]
        assert run["passed"] == (not failures)
        assert {
            result["failure_type"] for result in run["validator_results"] if not result["passed"]
        } == failures

        trace_path = Path(run["trace_path"])
        events = load_trace_events(trace_path)
        (tool_result,) = [event.payload for event in events if event.event_type == "tool_result"]
        assert tool_result["tool_name"] == "rag.search"
        result = tool_result["result"]
        assert result["top_k"] == 1
        assert result["corpus_version"] == "a1-financial-evidence-v1"
        (hit,) = result["hits"]
        assert hit["evidence_id"] == evidence_id
        assert float(hit["score"]) > 0

        workspace = tmp_path / "replays" / run["run_id"]
        workspace.mkdir(parents=True)
        sentinel = workspace / "existing.txt"
        sentinel.write_text("existing workspace data")
        assert main(["replay", str(trace_path), "--workspace", str(workspace)]) == 0
        replay = json.loads(capsys.readouterr().out)
        assert replay["passed"] is True
        assert replay["replayed_tool_calls"] == 1
        assert replay["divergences"] == []
        assert replay["validator_results"] == run["validator_results"]
        assert sentinel.read_text() == "existing workspace data"


@pytest.mark.parametrize("event_type", ["tool_result", "validator_result", "final_answer"])
def test_rag_replay_detects_tampered_trace(rag_summary, tmp_path, capsys, event_type):
    failed_run = next(
        run
        for run in rag_summary["runs"]
        if any(result["failure_type"] == "rag_invalid_citation" for result in run["validator_results"])
    )
    events = [event.to_dict() for event in load_trace_events(failed_run["trace_path"])]
    if event_type == "tool_result":
        tool_result = next(event["payload"]["result"] for event in events if event["event_type"] == event_type)
        tool_result["hits"][0]["evidence_id"] = "aapl-q4-fy2024-revenue"
    elif event_type == "validator_result":
        failed_validator = next(
            event["payload"]
            for event in events
            if event["event_type"] == event_type and event["payload"]["failure_type"] == "rag_invalid_citation"
        )
        failed_validator["passed"] = True
        failed_validator["failure_type"] = None
    else:
        answer = next(event["payload"] for event in events if event["event_type"] == event_type)
        assert "[aapl-q4-fy2024-revenue]" in answer["content"]
        answer["content"] = answer["content"].replace("[aapl-q4-fy2024-revenue]", "[aapl-fy2024-revenue]")

    tampered_path = tmp_path / "tampered.jsonl"
    tampered_path.write_text("".join(json.dumps(event) + "\n" for event in events))
    assert main(["replay", str(tampered_path), "--workspace", str(tmp_path / "replay")]) != 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["passed"] is False
    expected_divergence = "tool_result_mismatch" if event_type == "tool_result" else "validator_result_mismatch"
    assert any(item["type"] == expected_divergence for item in replay["divergences"])
    if event_type == "final_answer":
        assert all(result["passed"] for result in replay["validator_results"])
    else:
        assert replay["validator_results"] == failed_run["validator_results"]
