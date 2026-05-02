import json
from pathlib import Path

from sandboxed_agent_eval_harness.evaluation.live_provider import main, run_live_provider_workflow
from sandboxed_agent_eval_harness.models import GenericHTTPModelAdapter
from sandboxed_agent_eval_harness.tasks import default_task_suite


def test_live_provider_cli_fails_closed_without_live_flag(tmp_path, capsys):
    exit_code = main(
        [
            "--model-provider",
            "openai",
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 2
    assert "status=failed_closed" in output
    assert "reason=live_flag_required" in output
    assert not (tmp_path / "summary.json").exists()


def test_live_provider_cli_skips_without_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "--live",
            "--model-provider",
            "openai",
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    summary = json.loads((tmp_path / "summary.json").read_text())

    assert exit_code == 0
    assert "status=skipped" in output
    assert "reason=missing_credentials" in output
    assert summary["status"] == "skipped"
    assert summary["reason"] == "missing_credentials"
    assert summary["api_key_env"] == "OPENAI_API_KEY"
    assert summary["record_count"] == 0
    assert not (tmp_path / "raw_outputs.jsonl").exists()


def test_live_provider_workflow_records_fixture_candidate_with_injected_transport(tmp_path):
    requests = []
    task = default_task_suite().tasks[0]

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
            "output_text": json.dumps(
                {
                    "task_id": task.task_id,
                    "final_answer": "revenue_usd_millions=383285 [aapl-2023-10k-income]",
                    "final_answer_passed": True,
                    "tool_calls": [
                        {
                            "tool_name": "financial_statement.lookup",
                            "arguments": {
                                "ticker": "AAPL",
                                "fiscal_year": 2023,
                                "statement": "income",
                            },
                        }
                    ],
                    "reported_metrics": {"revenue_usd_millions": 383285},
                    "cost": 0.001,
                    "latency_seconds": 0.2,
                    "turns": 2,
                }
            )
        }

    result = run_live_provider_workflow(
        live=True,
        model_provider="openai",
        api_key="test-key",
        model="gpt-test",
        suite_name="smoke",
        max_tasks=1,
        max_cost_usd=0.01,
        record_output=True,
        output_dir=tmp_path,
        transport=transport,
        timeout_seconds=9,
    )

    summary = json.loads((tmp_path / "summary.json").read_text())
    raw_lines = (tmp_path / "raw_outputs.jsonl").read_text().splitlines()
    candidate = json.loads((tmp_path / "recorded_fixture_candidate.json").read_text())

    assert result["status"] == "completed"
    assert summary["status"] == "completed"
    assert summary["model_provider"] == "openai"
    assert summary["record_count"] == 1
    assert summary["estimated_cost_usd"] == 0.001
    assert len(raw_lines) == 1
    assert "api_key" not in raw_lines[0].lower()
    assert candidate["adapters"][0]["name"] == "live_openai_recorded_candidate"
    assert candidate["adapters"][0]["model"] == "gpt-test"
    assert candidate["adapters"][0]["records"][0]["task_id"] == task.task_id
    assert requests[0]["url"] == "https://api.openai.com/v1/responses"
    assert requests[0]["headers"]["Authorization"] == "Bearer test-key"
    assert requests[0]["payload"]["model"] == "gpt-test"
    assert task.instruction in requests[0]["payload"]["input"]
    assert requests[0]["timeout_seconds"] == 9


def test_generic_http_adapter_uses_configurable_endpoint_without_network():
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
            "output_text": json.dumps(
                {
                    "final_answer": "no metrics",
                    "final_answer_passed": True,
                    "tool_calls": [],
                    "reported_metrics": {},
                }
            )
        }

    task = default_task_suite().tasks[0]
    adapter = GenericHTTPModelAdapter(
        endpoint="https://models.example.test/plan",
        api_key="generic-key",
        model="generic-test",
        transport=transport,
        timeout_seconds=11,
    )

    record = adapter.generate(task)

    assert record["task_id"] == task.task_id
    assert record["final_answer_passed"] is True
    assert requests[0]["url"] == "https://models.example.test/plan"
    assert requests[0]["headers"]["Authorization"] == "Bearer generic-key"
    assert requests[0]["payload"]["model"] == "generic-test"
    assert requests[0]["payload"]["task"]["task_id"] == task.task_id
    assert task.instruction in requests[0]["payload"]["prompt"]
    assert requests[0]["timeout_seconds"] == 11
