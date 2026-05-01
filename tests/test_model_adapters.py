import json
from pathlib import Path

from sandboxed_agent_eval_harness.agents import ModelAdapterAgent
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.models import OpenAIResponsesAdapter, RecordedModelAdapter
from sandboxed_agent_eval_harness.tasks import default_task_suite


ROOT = Path(__file__).resolve().parents[1]
RECORDED_OUTPUT = ROOT / "fixtures" / "model_outputs" / "silent_failure_study.json"


def test_recorded_model_adapter_loads_fixture_records():
    adapter = RecordedModelAdapter.from_file(RECORDED_OUTPUT)

    record = adapter.plan_for("finance-nvda-datacenter-citation-2024")

    assert adapter.name == "recorded_gpt_style_agent"
    assert adapter.model == "recorded-gpt-style-v1"
    assert record["final_answer_passed"] is True
    assert "unsupported-source" in record["final_answer"]
    assert record["tool_calls"][0] == {
        "tool_name": "transcript.search",
        "arguments": {
            "ticker": "NVDA",
            "fiscal_period": "FY2024 Q4",
            "query": "data center revenue",
        },
        "result": {},
    }


def test_model_adapter_agent_runs_recorded_outputs_and_exposes_silent_failures(tmp_path):
    suite = default_task_suite()
    agent = ModelAdapterAgent(RecordedModelAdapter.from_file(RECORDED_OUTPUT))

    summary = run_evaluation(
        suite=suite,
        baselines=[agent],
        trials_per_task=1,
        output_dir=tmp_path,
    )

    assert summary.metrics["run_count"] == len(suite.tasks)
    assert summary.metrics["task_success_rate"] < 1.0
    assert all(run.metrics["final_answer_passed"] is True for run in summary.runs)
    assert summary.metrics["failure_taxonomy"]["unsupported_citation"] == 1
    assert summary.metrics["failure_taxonomy"]["tool_sequence_mismatch"] >= 1
    assert summary.metrics["failure_taxonomy"]["unit_tests_missing"] == 1
    assert summary.metrics["failure_taxonomy"]["constraint_violation"] == 1


def test_openai_responses_adapter_builds_request_without_network():
    requests = []

    def transport(url, headers, payload, timeout_seconds):
        requests.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "id": "resp_fixture",
            "output_text": json.dumps(
                {
                    "final_answer": "revenue_usd_millions=383285 [aapl-2023-10k-income]",
                    "tool_calls": [],
                    "reported_metrics": {"revenue_usd_millions": 383285},
                    "final_answer_passed": True,
                }
            ),
            "usage": {"total_tokens": 123},
        }

    task = default_task_suite().tasks[0]
    adapter = OpenAIResponsesAdapter(
        api_key="test-key",
        model="gpt-test",
        transport=transport,
        timeout_seconds=7,
    )

    record = adapter.generate(task)

    assert record["final_answer_passed"] is True
    assert record["reported_metrics"] == {"revenue_usd_millions": 383285}
    assert requests[0]["url"] == "https://api.openai.com/v1/responses"
    assert requests[0]["headers"]["Authorization"] == "Bearer test-key"
    assert requests[0]["payload"]["model"] == "gpt-test"
    assert task.instruction in requests[0]["payload"]["input"]
    assert requests[0]["timeout_seconds"] == 7
