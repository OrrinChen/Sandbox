from datetime import datetime
from pathlib import Path
import importlib
import sys

import pytest

openpyxl = pytest.importorskip("openpyxl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
WorkbookReader = importlib.import_module("workbook_read_tool").WorkbookReader


def test_read_ranges_and_search_use_only_public_inputs(tmp_path):
    path = tmp_path / "public.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Plan"
    sheet["B1"] = datetime(2025, 3, 4)
    sheet["A2"] = "=SUM(C1:C3)"
    sheet["C2"] = "VALUE"
    sheet["D2"] = "value reached"
    sheet["F10"] = "x" * 360
    book.save(path)
    snapshot = path.read_bytes()
    with WorkbookReader(path) as reader:
        view = reader.apply({"op": "range", "sheet": "Plan", "range": "$A$1:c2"})
        assert view == {
            "ok": True,
            "op": "range",
            "sheet": "Plan",
            "range": "A1:C2",
            "range_size": 6,
            "cells": [
                ["B1", "2025-03-04 00:00:00"],
                ["A2", "=SUM(C1:C3)"],
                ["C2", "VALUE"],
            ],
            "total": 3,
            "truncated": False,
            "blank_count": 3,
        }
        search = {"op": "find", "sheet": "Plan", "text": "value"}
        assert reader.apply(search)["cells"] == [
            ["C2", "VALUE"],
            ["D2", "value reached"],
        ]
        assert reader.apply({**search, "exact": True})["cells"] == [["C2", "VALUE"]]
        assert reader.apply({"op": "range", "sheet": "Plan", "range": "F10"})[
            "cells"
        ] == [["F10", "x" * 350]]
        assert not reader.apply({**search, "path": "../another.xlsx"})["ok"]
    assert snapshot == path.read_bytes()


def test_caps_and_invalid_requests(tmp_path):
    path = tmp_path / "public.xlsx"
    book = openpyxl.Workbook()
    for n in range(1, 90):
        book.active.cell(n, 1, "seen")
    book.save(path)
    with WorkbookReader(path) as reader:
        area = {"op": "range", "sheet": "Sheet", "range": "A1:XFD1048576"}
        find = {"op": "find", "sheet": "Sheet", "text": "SEEN"}
        for query, count in ((area, 80), (find, 12)):
            result = reader.apply(query)
            assert result["total"] == 89 and result["truncated"]
            assert (
                len(result["cells"]) == count and result["cells"][-1][0] == f"A{count}"
            )
        for request in (
            None,
            {},
            {"op": "edit"},
            {**area, "range": "A:B"},
            {**area, "range": "C2:A1"},
            {**area, "range": "XFE1"},
            {**area, "sheet": ["Sheet"]},
            {**find, "text": ""},
            {**find, "exact": "false"},
            {**find, "text": "x" * 351},
        ):
            assert reader.apply(request)["ok"] is False


def test_projection_reorders_visible_cells_and_cannot_recover_hidden_cells(tmp_path):
    path = tmp_path / "public.xlsx"
    book = openpyxl.Workbook()
    for address, text in (("B1", "known"), ("A2", "visible"), ("C3", "withheld")):
        book.active[address] = text
    book.save(path)
    public = {
        "Sheet": {
            "dimensions": [3, 3],
            "nonempty_count": 3,
            "cells": [["A2", "visible"], ["B1", "known"]],
        }
    }
    with WorkbookReader(path) as full, WorkbookReader.from_projection(public) as fixed:
        query = {"op": "range", "sheet": "Sheet", "range": "A1:B2"}
        assert fixed.dimensions == full.dimensions == {"Sheet": (3, 3)}
        assert fixed.apply(query) == full.apply(query)
        assert fixed.apply({**query, "range": "C3"})["blank_count"] == 1
        find = {"op": "find", "sheet": "Sheet", "text": "withheld"}
        assert fixed.apply(find)["total"] == 0
        assert full.apply(find)["cells"] == [["C3", "withheld"]]


def test_coverage_counts_unseen_cells_and_rejects_changed_excerpt(tmp_path):
    coverage = importlib.import_module("audit_workbook_coverage").workbook_coverage
    path = tmp_path / "public.xlsx"
    book = openpyxl.Workbook()
    book.active["A1"], book.active["B3"] = "seen", "additional"
    book.save(path)
    observation = {
        "Sheet": {"dimensions": [3, 2], "nonempty_count": 2, "cells": [["A1", "seen"]]}
    }
    row = coverage("book", observation, path.read_bytes())
    assert row["overlap_identical"] and row["extra_cells"] == 1
    observation["Sheet"]["cells"][0][1] = "different"
    with pytest.raises(ValueError, match="Overlapping cell display mismatch"):
        coverage("book", observation, path.read_bytes())
