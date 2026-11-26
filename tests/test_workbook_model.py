import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import workbook_model


def check(events, status=0, diagnostic=""):
    return workbook_model._read_events(
        "\n".join(json.dumps(e) for e in events),
        model=workbook_model.MODELS[0],
        exit_code=status,
        diagnostic=diagnostic,
    )


def test_workbook_model_rejects_undeclared_tool_even_when_only_started():
    with pytest.raises(workbook_model.PolicyTurnError, match="Undeclared"):
        check(
            [{"type": "item.started", "item": {"type": "command_execution"}}], 1, "503"
        )


def test_workbook_model_keeps_malformed_participant_answer_and_usage():
    raw = "missing spreadsheet formula"
    message = {"type": "item.completed", "item": {"type": "agent_message", "text": raw}}
    usage = {"input_tokens": 8, "output_tokens": 4}
    record = check(
        [
            {"type": "thread.started", "thread_id": "fake"},
            {"type": "turn.started"},
            message,
            {"type": "turn.completed", "usage": usage},
        ]
    )
    assert record["raw"] == raw
    assert record["usage"] == usage
    with pytest.raises(workbook_model.PolicyTurnError) as err:
        check([message], 1, "connection reset")
    assert not isinstance(err.value, workbook_model.TransportError)


def test_workbook_model_distinguishes_transport_before_answer():
    with pytest.raises(workbook_model.TransportError):
        check([{"type": "turn.failed", "error": {"message": "503 unavailable"}}], 1)
    with pytest.raises(workbook_model.PolicyTurnError, match="Model changed"):
        check([{"type": "turn.started", "model": "different-model"}])


def test_only_numeric_retry_notice_counts_survive_transport_retry(monkeypatch):
    import subprocess

    model = workbook_model.MODELS[0]
    completed = [
        {"type": "thread.started", "thread_id": "example"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}},
        {"type": "turn.completed", "usage": {"input_tokens": 8, "output_tokens": 1}},
    ]
    events = "\n".join(json.dumps(e) for e in completed)
    proc = iter(
        [
            subprocess.CompletedProcess(
                [], 1, "", "private diagnostics: retrying sampling request, status 429"
            ),
            subprocess.CompletedProcess(
                [],
                0,
                events,
                "retrying sampling request, status 503\nunrelated note 429",
            ),
        ]
    )

    def run(*args, **kwargs):
        assert kwargs["timeout"] == 600
        return next(proc)

    monkeypatch.setattr(workbook_model.subprocess, "run", run)
    result = workbook_model.ask(model, "Example prompt")
    assert result["transport_attempts"] == 2
    assert result["cli_retry_notices"] == 2
    assert result["cli_429_retry_notices"] == 1
    assert "private diagnostics" not in json.dumps(result)
