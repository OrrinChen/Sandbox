from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_workbook_access_luna as luna


def test_luna_addition_uses_frozen_inputs_and_private_model_allowlist(
    tmp_path, monkeypatch
):
    runtime = luna.host.load(luna.PARENT / "engine.json")
    version = runtime.pop("openpyxl")
    monkeypatch.setitem(sys.modules, "openpyxl", SimpleNamespace(__version__=version))
    monkeypatch.setattr(luna.shared.engine, "engine_info", lambda: runtime)
    cfg = luna.registration(tmp_path, create=True)
    parent = luna.host.load(luna.PARENT / "registration.json")
    assert cfg["models"] == ["gpt-6-luna"]
    assert cfg["arms"] == parent["arms"] == ["fixed", "browse"]
    assert cfg["groups"] == parent["groups"] and len(cfg["tasks"]) == 100
    assert cfg["input_hashes"] == parent["input_hashes"]
    collector = luna.collector()
    assert collector.ask.__globals__["MODELS"] == (luna.MODEL,)
    assert luna.MODEL not in luna.host.ask.__globals__["MODELS"]
    assert collector.ask.__globals__["EFFORT"] == "medium"
    batch = next(iter(cfg["groups"]))
    (tmp_path / "inputs" / (batch + ".json")).write_text("[]")
    with pytest.raises(ValueError, match="differs from source"):
        luna.registration(tmp_path)


def test_luna_cannot_target_archived_study_directory():
    for parent in (luna.PARENT, luna.paired.MID, luna.shared.PARENT):
        with pytest.raises(ValueError, match="separate Luna archive"):
            luna.registration(parent / "accidental-output", create=True)


def test_luna_official_final_selection_preserves_tool_and_model_checks():
    import json

    import run_workbook_access_luna_complete as complete
    import workbook_model

    def event(typ, **extra):
        return json.dumps({"type": typ, **extra})

    def message(text, **extra):
        return event(
            "item.completed", item={"type": "agent_message", "text": text}, **extra
        )

    events = [
        event("thread.started", thread_id="fixture"),
        message("progress"),
        message("malformed JSON is still the final"),
        event("turn.completed", usage={"input_tokens": 8, "output_tokens": 2}),
    ]
    stdout = "\n".join(events)
    result = complete.final_event_stream(
        stdout, "malformed JSON is still the final\n", ValueError
    )
    expected = workbook_model._read_events(
        result, model=luna.MODEL, exit_code=0, diagnostic=""
    )
    assert expected["raw"] == "malformed JSON is still the final"
    with pytest.raises(ValueError, match="disagrees"):
        complete.final_event_stream(stdout, "progress", ValueError)
    with pytest.raises(ValueError, match="missing"):
        complete.final_event_stream(stdout, None, ValueError)
    events.insert(1, event("item.completed", item={"type": "command_execution"}))
    output = complete.final_event_stream("\n".join(events), expected["raw"], ValueError)
    with pytest.raises(workbook_model.PolicyTurnError, match="Undeclared tool"):
        workbook_model._read_events(
            output, model=luna.MODEL, exit_code=0, diagnostic=""
        )
    events.pop(1)
    events[1] = message("progress", model="wrong")
    output = complete.final_event_stream("\n".join(events), expected["raw"], ValueError)
    with pytest.raises(workbook_model.PolicyTurnError, match="Model changed"):
        workbook_model._read_events(
            output, model=luna.MODEL, exit_code=0, diagnostic=""
        )


def test_luna_cli_audit_retains_public_messages_and_usage_only():
    import json

    import run_workbook_access_luna_complete as complete

    stdout = "\n".join(
        json.dumps(e)
        for e in [
            {"type": "thread.started", "thread_id": "abc"},
            {
                "type": "item.completed",
                "item": {"type": "reasoning", "text": "private data"},
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "progress"},
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "final"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 7, "output_tokens": 2},
            },
        ]
    )
    receipt = complete.event_receipt(stdout, "final\n", 0)
    assert "private data" not in json.dumps(receipt)
    assert [i.get("text") for i in receipt["items"]] == [None, "progress", "final"]
    summary = complete.slot_summary(
        {
            "binding": {"arm": "fixed", "batch": "batch", "stage": "submit"},
            "status": "accepted",
            "cli_events": [receipt],
        }
    )
    assert summary["message_count"] == 2 and summary["thread_id"] == "abc"
    assert summary["usage"] == {"input_tokens": 7, "output_tokens": 2}
