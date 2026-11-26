import shutil

import pytest

from sandboxed_agent_eval_harness.benchmarks.independent import spreadsheets as sheets


def test_offline_cell_projection():
    assert sheets.safe_formula("=IF(A2>0,SUM(B2:B5),0)")
    assert not sheets.safe_formula('=HYPERLINK("https://example.org","text")')
    assert not sheets.safe_formula("=NOSUCHFUNCTION(A2)")
    assert not sheets.equivalent({"A3": ["s", "10"]}, {"A3": ["n", "10"]})
    assert sheets.equivalent({"A3": ["n", "10.0"]}, {"A3": ["n", "10"]})


def test_sheet_data_and_public_packet(tmp_path):
    rows = sheets.records()
    assert rows and len(rows) == len({r["source_group"] for r in rows})
    task = rows[0]["task_id"]
    sheets.materialize(task, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {"input.xlsx", "formula_support.txt"}
    assert all(
        "gold" not in r and "reference" not in r and "wrong_edit" not in r for r in rows
    )
    assert not sheets.grade(task, {"formulas": {"XFD1048576": "=1"}})
    assert not sheets.grade(task, sheets.run_negative(task)["formulas"])


@pytest.mark.skipif(
    not (shutil.which("soffice") or shutil.which("libreoffice")), reason="Calc required"
)
def test_executed_reference_and_stale_edit():
    task = next(r["task_id"] for r in sheets.records() if r["split"] == "dev")
    assert sheets.calibration([task]) == {task: (True, False)}
    other = sheets.run_reference(task)
    other["formulas"] = {
        addr: "=(" + formula[1:] + ")" for addr, formula in other["formulas"].items()
    }
    assert sheets.grade(task, other)


@pytest.mark.skipif(
    not (shutil.which("soffice") or shutil.which("libreoffice")), reason="Calc required"
)
def test_memorized_first_workbook_does_not_pass_second_input():
    task = next(
        r["task_id"]
        for r in sheets.records()
        if r["split"] == "dev"
        and all(
            tag == "n" for tag, _ in sheets._private()[r["task_id"]]["gold"].values()
        )
    )
    stored = {
        cell: "=" + value
        for cell, (_, value) in sheets._private()[task]["gold"].items()
    }
    assert not sheets.grade(task, {"formulas": stored})


def test_failed_conversion_isolated_from_valid_neighbours(monkeypatch):
    tasks = [r["task_id"] for r in sheets.records()[:3]]
    first, broken, malformed = tasks
    failed = []

    def engine(jobs, home):
        assert not (home / "result").exists()
        if any(t == broken and label == "candidate" for t, label, _ in jobs):
            failed.append(len(jobs))
            raise sheets.WorkbookConversionError("simulated Calc exit")
        (home / "result").mkdir()
        return {(t, label): True for t, label, _ in jobs}

    monkeypatch.setattr(sheets, "_batch", engine)
    result = sheets.batch_grade(
        {
            first: sheets.run_reference(first),
            broken: sheets.run_reference(broken),
            malformed: {"formulas": {"A1": "=1\x01"}},
        }
    )
    assert result == {first: True, broken: False, malformed: False}
    assert failed == [2, 1]


def test_conversion_outage_is_reported(monkeypatch):
    def unavailable(*_):
        raise sheets.WorkbookConversionError(
            "Calc failed even on the known-good control"
        )

    monkeypatch.setattr(sheets, "_batch", unavailable)
    task = sheets.records()[0]["task_id"]
    with pytest.raises(sheets.WorkbookConversionError):
        sheets.batch_grade({task: sheets.run_reference(task)})
    assert sheets.batch_grade({"not-a-registered-task": None}) == {
        "not-a-registered-task": False
    }
