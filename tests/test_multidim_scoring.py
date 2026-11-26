"""Check dimension scores, valid citation alternatives and conditional audit outcomes."""

from pathlib import Path
import runpy

import pytest

scorer = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/score_multidim_development.py"))
grade, report = scorer["grade"], scorer["make_report"]
GOLD = {"choice": "higher", "value": "1", "citations": [["B", "C"], ["A", "C"]]}


def test_strict_fields_and_equivalent_minimal_evidence():
    good = {"choice": "higher", "value": "1.00", "citations": ["C", "A"]}
    assert grade(good, GOLD) == []
    for refs in (["B", "C", "A"], ["A", "A", "C"], ["A", "D"], ["C"], ["F", "C"], ["A", {}], None):
        assert grade(dict(good, citations=refs), GOLD) == ["citations"]
    for value in (None, 1, "nan", "Infinity", "1_0", "", ".999"):
        assert grade(dict(good, value=value), GOLD) == ["value"]
    null_gold = dict(GOLD, choice=None, value=None)
    assert grade({"citations": ["B", "C"]}, null_gold) == ["choice", "value"]
    assert grade(dict(good, choice=None, value=None), null_gold) == []


def test_diagnoses_and_paired_change_counts():
    good = {"choice": "higher", "value": "1", "citations": ["C", "B"]}
    labels = {n: {"dimension": "association", "pair_id": f"pair{(n - 1) // 2}",
                  "side": (n - 1) % 2, "gold": GOLD} for n in range(1, 5)}
    correct = {n: dict(good, row=n) for n in labels}
    first = dict(correct)
    first[1] = dict(correct[1], citations=["B", "D"])
    first[4] = dict(correct[4], value=None)
    audit = {n: dict(answer, decision="keep", issues=[]) for n, answer in first.items()}
    def issue(field, ref):
        return {"field": field, "ref": ref, "why": "Test issue."}
    audit[1] = dict(correct[1], decision="revise", issues=[
        issue("citations", "D"), issue("citations", "B"), issue("citations", "C"), issue("value", "C")
    ])
    audit[2] = dict(correct[2], choice="lower", decision="revise", issues=[issue("choice", "C")])
    audit[4] = dict(correct[4], decision="revise", issues=[issue("value", "D")])
    retry = dict(first)
    retry[3] = dict(first[3], citations=[])
    result = report(labels, first, audit, retry)
    summary = result["by_dimension"]["association"]
    assert result["overall"] == summary
    assert summary["initial_passed"] == 2 and summary["audit_passed"] == 3
    assert summary["detected"] == 2 and summary["localized_and_repaired"] == 1
    assert summary["false_alarm"] == summary["spoiled"] == summary["retry_spoiled"] == 1
    assert summary["conditional_rates"]["repaired"] == {"count": 2, "denominator": 2, "rate": 1}
    assert summary["failed_field_counts"]["initial"] == {"choice": 0, "value": 1, "citations": 1}
    assert summary["audit_vs_retry"] == {"both_pass": 0, "audit_only": 3, "retry_only": 1, "both_fail": 0}
    row = result["per_question"][0]
    assert [issue["ref"] for issue in row["matched_issues"]] == ["D", "C"]
    assert result["pairs"][0]["result"] == {"initial": "right_only", "audit": "left_only", "retry": "right_only"}
    assert summary["pairs_both_passed"] == {"initial": 0, "audit": 1, "retry": 0}

    correct_audit = {n: dict(answer, decision="keep", issues=[]) for n, answer in correct.items()}
    no_errors = report(labels, correct, correct_audit, correct)["overall"]
    assert no_errors["conditional_rates"]["repaired"] == {"count": 0, "denominator": 0, "rate": None}
    with pytest.raises(ValueError, match="same nonempty"):
        report(labels, {}, correct_audit, correct)
