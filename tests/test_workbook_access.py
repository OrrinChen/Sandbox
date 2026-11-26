import importlib
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("openpyxl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
runner = importlib.import_module("run_workbook_access")


def test_each_task_has_its_own_read_budget():
    observation = {"x": {"cells": [["A1", "one"], ["B2", "two"]], "dimensions": [2, 2]}}
    reader = runner.WorkbookReader.from_projection(observation)
    req = {"op": "find", "sheet": "x", "text": "one"}
    result = runner.inspect_round(
        ["a", "b", "c"],
        json.dumps({"a": [req] * 3, "b": []}),
        {"a": reader, "b": reader, "c": reader},
    )
    assert result["a"]["status"] == "over_budget" and len(result["a"]["reads"]) == 2
    assert result["b"] == {"status": "ok", "reads": []}
    assert result["c"] == {"status": "missing_or_invalid_plan", "reads": []}


def test_interactive_replay_rejects_transcript_or_tool_result_changes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "engine_info", lambda: {"cli": "local-test"})

    def fake(model, prompt):
        packets = json.loads(
            prompt.split("Public packets: ")[1].split("\nPrior inspections:")[0]
        )
        instruction = prompt.split("Stage: ")[-1]
        if instruction == "submit":
            result = {p["task_id"]: {"formulas": {}} for p in packets}
        else:
            result = {
                p["task_id"]: [
                    {"op": "range", "sheet": p["target_sheet"], "range": "A1:B2"}
                ]
                for p in packets
            }
        return {
            "model": model,
            "raw": json.dumps(result),
            "usage": {"output_tokens": 10},
        }

    monkeypatch.setattr(runner, "ask", fake)
    runner.record(tmp_path, 2, True)
    monkeypatch.setattr(runner, "ask", lambda *_: pytest.fail("Replay called a model"))
    assert all(row["calls"] == 2 for row in runner.verified_records(tmp_path))
    f = next((tmp_path / "turns").rglob("inspect-2.json"))
    row = json.loads(f.read_bytes())
    row["response"]["raw"] = "{}"
    f.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="prompt|diverged"):
        runner.verified_records(tmp_path)
