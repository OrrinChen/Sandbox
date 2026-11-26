"""Exercise the held-out fixture lock, comparison isolation, and diagnostic fields."""
import json
from pathlib import Path
import runpy

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return runpy.run_path(str(SCRIPTS / "run_financial_self_audit_blind.py"))


def test_frozen_fixture_and_public_projection(tmp_path, runner):
    prior = [{"question": "Unrelated Issuer. What is the balance?",
              "evidence": [{"ref": "A", "text": "Previously used disclosure."}]}]
    for directory in ("financial-self-audit-dev", "financial-self-audit-implicit-dev",
                      "financial-self-audit-natural-errors/sample"):
        path = tmp_path / directory / "public/questions.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(prior), encoding="utf-8")
    root = tmp_path / "blind"
    runner["freeze"](root, tmp_path)
    manifest = runner["read"](root / "freeze.json")
    rows = runner["frozen_public"](root, manifest)
    assert manifest["issuer_count"] == 60
    assert manifest["original_document_count"] == 300
    assert all(value == 0 for value in manifest["overlap"].values())
    assert all(list(row) == ["row", "question", "evidence"] and
               all(set(hit) == {"ref", "text"} for hit in row["evidence"]) for row in rows)
    fixture = root / "initial/inputs-1.json"
    fixture.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after locking"):
        runner["frozen_public"](root, manifest)


def test_same_evidence_and_retry_hides_initial(tmp_path, runner):
    questions = [{"row": n, "question": f"Question {n}", "evidence": []} for n in range(1, 61)]
    runner["stage_files"](tmp_path, "initial", questions)
    submitted = {}
    for batch in range(1, 7):
        rows = questions[(batch - 1) * 10:batch * 10]
        responses = [{"row": row["row"], "verdict": "answer", "answer_value": "1"} for row in rows]
        submitted.update((response["row"], response) for response in responses)
        runner["write_once"](tmp_path / "initial" / f"responses-{batch}.json", responses)
    runner["write_once"](tmp_path / "freeze.json", {})
    runner["lock_initial"](tmp_path, questions)
    for batch in range(1, 7):
        name = f"inputs-{batch}.json"
        assert (tmp_path / "initial" / name).read_bytes() == (tmp_path / "retry" / name).read_bytes()
        for row in runner["read"](tmp_path / "audit" / name):
            assert row["initial_answer"] == submitted[row["row"]]
    runner["verify_hashes"](tmp_path, runner["read"](tmp_path / "initial_lock.json"))


def test_diagnoses_match_only_failed_field_and_appropriate_reference(runner):
    initial = {"details": {"expected_evidence_ids": ["B", "C"], "cited_evidence_ids": ["A", "C"],
                           "verdict_correct": True, "numeric_correct": False,
                           "unit_correct": True, "citation_correct": False}}
    issues = [
        {"field": "citations", "ref": "C", "explanation": "An unrelated complaint."},
        {"field": "citations", "ref": "B", "explanation": "Required source missing."},
        {"field": "answer_value", "ref": "C", "explanation": "The amount is inconsistent with the schedule."},
        {"field": "unit", "ref": "B", "explanation": "An incorrect flag."},
    ]
    flagged, verified = runner["grade_diagnoses"]({"row": 1, "decision": "revise", "issues": issues}, initial)
    assert flagged is True
    assert verified == issues[1:3]
