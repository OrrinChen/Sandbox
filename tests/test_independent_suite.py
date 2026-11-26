import json

import pytest

from sandboxed_agent_eval_harness.benchmarks.independent import (
    relational,
    repairs,
    suite,
)


def test_release_counts_and_source_isolation():
    frozen = json.loads(suite.LOCK.read_bytes())
    assert suite.release_record() == frozen
    assert frozen["counts"] == {"dev": 100, "test": 500}
    assert len(frozen["domains"]["test"]) == 6
    records = [row for _, row in suite.inventory().values()]
    dev = {r["source_group"] for r in records if r["split"] == "dev"}
    test = {r["source_group"] for r in records if r["split"] == "test"}
    assert not (dev & test)


def test_public_relational_packet_does_not_open_key(tmp_path, monkeypatch):
    task_id = next(iter(relational.index()))
    get_index = relational.index

    def checked(private=False):
        assert not private
        return get_index(private)

    monkeypatch.setattr(relational, "index", checked)
    suite.export(task_id, tmp_path)
    packet = json.loads((tmp_path / "task.json").read_bytes())
    assert "tables" in packet and list(tmp_path.glob("*.csv"))
    assert not (
        set(packet) & {"reference", "negative", "alternate", "expected", "mistake"}
    )


def test_wrong_query_and_constant_submission_fail():
    task_id = next(iter(relational.index()))
    key = relational.index(True)[task_id]
    assert relational.grade(task_id, key["reference"])
    assert relational.grade(task_id, key["independent_reference"])
    assert not relational.grade(task_id, key["negative"])
    assert not relational.grade(task_id, "SELECT 1")
    assert not relational.grade(task_id, "DROP TABLE data")


def test_receipt_checks_actual_submission_and_verdict(tmp_path):
    row = relational.records()[0]
    task_id = row["task_id"]
    former = suite.receipt(task_id, relational.run_negative(task_id))
    assert not former["passed"]
    assert former == suite.receipt(task_id, former["candidate"])
    former["passed"] = True
    report = tmp_path / "trace.json"
    suite.write_json(report, former)
    from argparse import Namespace

    with pytest.raises(ValueError, match="Replay diverged"):
        suite.run(Namespace(independent_action="replay", receipt=report))


def test_repair_projection_contains_only_issue_and_starting_code(tmp_path):
    task_id = next(iter(repairs.index()))
    suite.export(task_id, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["subject.py", "task.json"]
    packet = json.loads((tmp_path / "task.json").read_bytes())
    assert (
        "probes" not in packet
        and "expected" not in packet
        and "reference" not in packet
    )
    assert (tmp_path / "subject.py").read_text() == repairs.run_negative(task_id)


def test_public_export_is_idempotent_and_preserves_other_work(tmp_path):
    first, second = sorted(relational.index())[:2]
    destination = tmp_path / "packet"
    suite.export(first, destination)
    suite.export(first, destination)
    original = (destination / "task.json").read_bytes()
    with pytest.raises(ValueError, match="different packet"):
        suite.export(second, destination)
    assert (destination / "task.json").read_bytes() == original


def test_empty_fill_and_invalid_fill_do_not_break_other_submissions(monkeypatch):
    from pathlib import Path

    pytest.importorskip("openpyxl")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_independent_comparison import expand

    edits = {"formulas": {"D1": "=A1+1"}}
    assert expand({**edits, "fills": []}) == edits
    assert expand({"fills": [{"range": "D1:D2", "formula": '=SUM("broken)'}]}) == {}
