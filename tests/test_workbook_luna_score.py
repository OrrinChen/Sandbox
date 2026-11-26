from pathlib import Path

import pytest


@pytest.fixture
def scorer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import score_workbook_luna

    return score_workbook_luna


def test_counts_luna_recoveries_within_the_original_and_previous_misses(scorer):
    tasks = ["old-solved-by-peer", "new-luna-only", "all-missed", "previously-passed"]
    grades = {
        "a": [(0, 1), (0, 0), (0, 0), (0, 0)],
        "b": [(1, 1), (0, 0), (1, 0), (0, 0)],
        "luna": [(1, 1), (0, 1), (1, 0), (0, 0)],
    }
    rows = [
        {
            "task_id": t,
            "model": m,
            "fixed": f,
            "browse": b,
            "old_both_failed": t != "previously-passed",
        }
        for m, pairs in grades.items()
        for t, (f, b) in zip(tasks, pairs)
    ]
    results = scorer.cross_model_outcomes(rows, ["a", "b"], "luna")
    assert results["previously_unsolved_now_passed_by_luna_browse"] == ["new-luna-only"]
    assert results["remaining_after_all_three_browse"] == ["all-missed"]
    assert results["all_three_failed_browse_across_full_roster"] == [
        "all-missed",
        "previously-passed",
    ]
    cut = results["luna_fixed_to_browse"]["old_misses_unsolved_by_prior_browse_models"]
    assert cut["lost"]["tasks"] == ["all-missed"]
    with pytest.raises(ValueError, match="one pair"):
        scorer.cross_model_outcomes(rows[:-1], ["a", "b"], "luna")


def test_prior_grade_loader_requires_unique_complete_boolean_verdicts(scorer):
    row = {"model": "first", "task_id": "x", "fixed": "0", "browse": "1"}
    assert scorer.archived_verdicts([row], ["first"], ["x"]) == {
        "first/fixed": {"x": False},
        "first/browse": {"x": True},
    }
    with pytest.raises(ValueError):
        scorer.archived_verdicts([row, row], ["first"], ["x"])
    with pytest.raises(ValueError):
        scorer.archived_verdicts([{**row, "fixed": "unknown"}], ["first"], ["x"])
    with pytest.raises(ValueError):
        scorer.archived_verdicts([row], ["first"], ["x", "missing"])


def test_clean_batch_pair_removes_affected_tasks_from_both_arms(scorer):
    groups = {"one": ["a", "b"], "two": ["c"]}
    rows = [{"task_id": t, "fixed": 0, "browse": 1} for t in ("a", "b", "c")]
    slots = [
        {
            "arm": a,
            "batch": b,
            "stage": t,
            "status": "accepted",
            "message_count": 1,
            "usage": {},
        }
        for a in ("fixed", "browse")
        for b in groups
        for t in ("inspect-1", "inspect-2", "submit")
    ]
    slots[0]["message_count"] = 2
    slots[-1].update(status="infrastructure_error", usage=None, message_count=0)
    report = scorer.collection_summary(slots, groups, rows)
    assert report["by_arm"]["fixed"]["accepted_turns_with_progress_messages"] == 1
    assert report["by_arm"]["browse"]["slots_with_unknown_usage"] == 1
    assert report["all_turns_accepted_in_both_arms"]["gained"]["tasks"] == ["a", "b"]
    with pytest.raises(ValueError, match="every registered"):
        scorer.collection_summary(slots[:-1], groups, rows)


def test_sensitivity_joins_missing_answers_and_new_cells_on_the_same_task(
    scorer, tmp_path
):
    import json

    groups = {"clean": ["x"], "affected": ["y"]}
    models = ["a", "b", scorer.luna.MODEL]
    rows = [
        {
            "task_id": t,
            "model": m,
            "old_both_failed": 1,
            "fixed": 0,
            "browse": int(m == models[-1]),
            "outcome": "gained" if m == models[-1] else "both_fail",
            "new_nonempty_cells": int(t == "y"),
        }
        for t in ("x", "y")
        for m in models
    ]
    slots = [
        {
            "status": "protocol_rejected",
            "arm": "browse",
            "batch": "affected",
            "stage": "inspect-2",
        }
    ]
    (tmp_path / "collection_accounting.json").write_text(json.dumps({"slots": slots}))
    evidence = tmp_path / "turns" / models[-1] / "browse/affected/inspect-2.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        json.dumps(
            {"cli_events": [{"external_tool_events": [{"item": "mcp_tool_call"}]}]}
        )
    )
    acc = {
        "by_arm": {
            "fixed": {"fully_accepted_batches": list(groups)},
            "browse": {"fully_accepted_batches": ["clean"]},
        }
    }
    records = [
        {"task_id": "y", "arm": "fixed", "submission_status": "missing_or_invalid_json"}
    ]
    s = scorer.sensitivity(rows, groups, acc, records, tmp_path)
    assert s["matched_complete_tasks"] == ["x"]
    assert s["same_task_passes"][models[-1]] == {"fixed": 0, "browse": 1}
    assert s["new_rescues_on_complete_tasks"] == ["x"]
    assert s["browse_gains_with_missing_fixed_answer"] == ["y"]
    assert s["browse_gains_with_missing_fixed_answer_and_new_cells"] == ["y"]
    assert s["nonaccepted_slots"][0]["out_of_protocol_item_types"] == ["mcp_tool_call"]
