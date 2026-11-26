from pathlib import Path
import json
import os
import runpy
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_financial_self_audit_pilot.py"
BUILDER = SCRIPT.with_name("build_financial_self_audit_pilot.py")


def test_all_pilot_questions_have_exactly_five_excerpts_and_scored_answers():
    fixture = runpy.run_path(str(BUILDER))
    questions, labels = fixture["build"]()
    fixture["verify"](questions, labels)


def test_implicit_pilot_builds_short_questions_with_complete_evidence(tmp_path):
    subprocess.run([sys.executable, str(BUILDER.with_name("build_financial_self_audit_implicit.py")),
                    "--output", str(tmp_path)], check=True,
                   env={**os.environ, "PYTHONPATH": str(SCRIPT.parents[1] / "src")})
    questions = json.loads((tmp_path / "public/questions.json").read_text())
    labels = json.loads((tmp_path / "private/labels.json").read_text())
    assert len(questions) == len(labels) == 32
    assert len({label["family"] for label in labels}) == 8
    assert all(row["question"].count("?") == 1 and len(row["evidence"]) == 5 for row in questions)


def test_staged_inputs_reject_evidence_drift_and_keep_retry_independent(tmp_path):
    script = runpy.run_path(str(SCRIPT))
    rows = [{"row": row, "question": "q", "evidence": [{"ref": ref, "text": ref} for ref in "ABCDE"]}
            for row in range(1, 33)]
    initial = {row["row"]: {"row": row["row"], "answer_value": "4"} for row in rows}
    script["prepare"](tmp_path, "audit", rows, initial)
    script["prepare"](tmp_path, "retry", rows, None)
    read = script["read"]
    assert read(tmp_path / "retry/inputs-1.json") == rows[:16]
    audit_input = read(tmp_path / "audit/inputs-1.json")
    assert audit_input[0]["initial_answer"] == initial[1]
    audit_input[0]["evidence"][0]["text"] = "changed"
    script["write"](tmp_path / "audit/inputs-1.json", audit_input)
    with pytest.raises(ValueError, match="Evidence or prior answer drift"):
        script["stage_results"](tmp_path, "audit", rows, initial)


def test_diagnosis_requires_correct_field_slot_and_evidence():
    script = runpy.run_path(str(SCRIPT))
    label = {"evidence_ids": ["C"], "operands": [{"ref": "C", "value": "10", "unit": "usd"}]}
    response = {"operands": [{"ref": "A", "value": "10.0", "unit": "usd"}]}
    score = {"verdict_correct": True, "numeric_correct": True, "unit_correct": True, "citation_correct": False}
    targets = script["diagnostic_targets"](response, label, score)
    assert targets == {("operand_ref", 1): {"C"}, ("citations", None): {"C"}}
    issues = [{"field": "operand_ref", "slot": 1, "ref": "C"},
              {"field": "operand_ref", "slot": 2, "ref": "C"},
              {"field": "operand_ref", "slot": 1, "ref": "A"}]
    assert script["diagnosis_hits"](issues, targets) == 1


def test_implicit_diagnosis_ignores_reordering_and_detects_sign_error():
    script = runpy.run_path(str(SCRIPT))
    gold = [{"ref": "C", "value": "10", "unit": "usd", "sign": 1},
            {"ref": "D", "value": "3", "unit": "usd", "sign": -1}]
    label = {"evidence_ids": ["C", "D"], "operands": gold}
    response = {"operands": [{**gold[1], "sign": 1}, gold[0]]}
    score = {"verdict_correct": True, "numeric_correct": False, "unit_correct": True, "citation_correct": True}
    targets = script["diagnostic_targets"](response, label, score, implicit=True)
    assert targets == {("answer_value", None): {"C", "D"}, ("operand_sign", 1): {"D"}}
    assert "480 output tokens" in script["stage_prompt"]("audit", True)
    assert "480 output tokens" in script["stage_prompt"]("retry", True)
    assert "220 output tokens" in script["stage_prompt"]("audit", False)
