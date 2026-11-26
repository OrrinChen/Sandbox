import copy
from pathlib import Path

import pytest


@pytest.fixture
def score(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import score_workbook_access

    return score_workbook_access


def fixture_rows():
    models, tasks = ["small", "large"], ["sheet-a", "sheet-b", "sheet-c"]
    old = {
        "direct": dict.fromkeys(tasks, False),
        "self_check": dict.fromkeys(tasks, False),
    }
    old["direct"]["sheet-b"] = True
    records, verdicts = [], {}
    for model in models:
        for arm in ["fixed", "browse"]:
            verdicts[model + "/" + arm] = dict.fromkeys(tasks, False)
            verdicts[model + "/" + arm]["sheet-b" if arm == "fixed" else "sheet-a"] = (
                True
            )
            for task in tasks:
                novel = [["S", "A3"]] if task == "sheet-a" and arm == "browse" else []
                records.append(
                    {
                        "task_id": task,
                        "model": model,
                        "arm": arm,
                        "batch": "spreadsheets-000",
                        "calls": 1,
                        "model_calls": 3,
                        "usage": {"input_tokens": 200, "output_tokens": 12},
                        "trace": [{"result": {"ok": True}}],
                        "novel_cells": novel,
                    }
                )
    return (
        records,
        models,
        tasks,
        old,
        verdicts,
        {"sheet-a": 10, "sheet-b": 0, "sheet-c": 0},
    )


def test_paired_outcomes_and_batch_deduplication(score):
    args = fixture_rows()
    summary, rows = score.summarize(*args)
    assert len(rows) == 6
    assert summary["archived_both_failed"] == ["sheet-a", "sheet-c"]
    r = summary["by_model"]["small"]
    assert r["all"]["lost"]["tasks"] == ["sheet-b"]
    assert r["all"]["gained"]["tasks"] == ["sheet-a"]
    assert r["old_both_failed"]["both_fail"]["tasks"] == ["sheet-c"]
    assert r["initially_truncated"]["gained"]["count"] == 1
    assert r["old_failures_with_new_cells_returned"]["gained"]["tasks"] == ["sheet-a"]
    u = summary["usage"]["large/browse"]
    assert (u["tokens"]["input_tokens"], u["read_requests"], u["model_calls"]) == (
        200,
        3,
        3,
    )
    assert u["new_task_cell_pairs"] == u["tasks_with_new_cells"] == 1
    assert "sheet-c" in str(
        summary["by_model"]["large"]["old_failures_with_complete_input"]
    )


def test_fixed_cannot_reveal_new_cells_or_inherit_different_usage(score):
    args = fixture_rows()
    r = copy.deepcopy(args[0])
    r[0]["novel_cells"] = [["S", "B1"]]
    with pytest.raises(ValueError, match="fixed observation"):
        score.summarize(r, *args[1:])
    r = copy.deepcopy(args[0])
    r[0]["usage"]["input_tokens"] = 100
    with pytest.raises(ValueError, match="Batch usage"):
        score.summarize(r, *args[1:])


def test_missing_answer_is_not_silently_dropped(score):
    args = fixture_rows()
    with pytest.raises(ValueError, match="one sealed answer"):
        score.summarize(args[0][1:], *args[1:])


def test_complete_batch_control_accounts_for_truncated_peers(score):
    args = fixture_rows()
    for r in args[0]:
        if r["task_id"] == "sheet-c":
            r["batch"] = "spreadsheets-001"
    changes, rows = score.summarize(*args)
    assert changes["untruncated_tasks_with_truncated_batch_peer"] == ["sheet-b"]
    assert changes["all_complete_batches"] == ["spreadsheets-001"]
    group = changes["by_model"]["large"]["all_tasks_in_batch_initially_complete"]
    assert group["both_fail"]["tasks"] == ["sheet-c"]
    assert (
        next(r for r in rows if r["task_id"] == "sheet-b")[
            "any_workbook_in_batch_truncated"
        ]
        == 1
    )
