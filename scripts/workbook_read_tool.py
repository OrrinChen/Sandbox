"""Bounded, deterministic queries over one public workbook supplied by the caller."""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

MAX_RANGE_CELLS = 80
MAX_FIND_MATCHES = 12
MAX_CELL_CHARS = 350
MAX_QUERY_CHARS = 350
A1 = r"\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}"
RANGE = re.compile(rf"{A1}(?::{A1})?", re.IGNORECASE | re.ASCII)

TOOL_HELP = (
    'Read a rectangular range with {"op":"range","sheet":"Sheet1","range":"B2:G20"} '
    'or search one sheet with {"op":"find","sheet":"Sheet1","text":"header","exact":false}. '
    "Sheet names are case-sensitive. Search is literal and case-insensitive, matching part of "
    "the cell text unless exact is true. Formulas are shown as formulas. Results list nonempty "
    "cells in row-column order. Range returns up to 80 cells and find returns up to 12 hits, "
    "with at most 350 characters per value. blank_count is the number of positions lacking a visible "
    "value in this view. If truncated is true use a narrower query."
)


class WorkbookReader:
    """Open one workbook once. Requests can neither select a different file nor edit a cell."""

    def __init__(self, path: Path):
        book = load_workbook(path, data_only=False, keep_links=False)
        self.dimensions = {}
        self._sheets = {}
        try:
            for sheet in book:
                cells = []
                for (row, col), cell in sorted(sheet._cells.items()):
                    value = cell.value
                    if value is None:
                        continue
                    if isinstance(value, ArrayFormula):
                        value = value.text or ""
                    elif isinstance(value, DataTableFormula):
                        value = f"TABLE({value.ref})"
                    cells.append(
                        (row, col, cell.coordinate, str(value)[:MAX_CELL_CHARS])
                    )
                self.dimensions[sheet.title] = (sheet.max_row, sheet.max_column)
                self._sheets[sheet.title] = cells
        finally:
            book.close()

    @classmethod
    def from_projection(cls, observation: dict) -> WorkbookReader:
        """Use exactly the originally visible cells; do not open the underlying workbook."""
        reader = cls.__new__(cls)
        reader.dimensions = {}
        reader._sheets = {}
        for name, sheet in observation.items():
            reader.dimensions[name] = tuple(sheet["dimensions"])
            reader._sheets[name] = sorted(
                (*coordinate_to_tuple(address), address, text[:MAX_CELL_CHARS])
                for address, text in sheet["cells"]
            )
        return reader

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._sheets.clear()

    def apply(self, request: dict) -> dict:
        if not isinstance(request, dict):
            return {"ok": False, "error": "Expected a JSON object."}
        op = request.get("op")
        if op not in ("range", "find"):
            return {"ok": False, "error": "Unknown operation. Use range or find."}
        fields = (
            {"op", "sheet", "range"}
            if op == "range"
            else {"op", "sheet", "text", "exact"}
        )
        if set(request) - fields:
            return {"ok": False, "error": "Unknown request fields."}
        sheet = request.get("sheet")
        if not isinstance(sheet, str) or sheet not in self._sheets:
            return {
                "ok": False,
                "error": "Sheet not found. Use a sheet name from the observation.",
            }
        sheet_cells = self._sheets[sheet]
        result = {"ok": True, "op": op, "sheet": sheet}
        if op == "range":
            area = request.get("range")
            if not isinstance(area, str) or not RANGE.fullmatch(area):
                return {
                    "ok": False,
                    "error": "Use a single cell or rectangular A1 range.",
                }
            left, top, right, bottom = range_boundaries(area.upper())
            if left > right or top > bottom or right > 16384 or bottom > 1048576:
                return {"ok": False, "error": "Invalid range bounds."}
            result["range"] = area.replace("$", "").upper()
            result["range_size"] = (right - left + 1) * (bottom - top + 1)
            limit = MAX_RANGE_CELLS
        else:
            text = request.get("text")
            exact = request.get("exact", False)
            if (
                not isinstance(text, str)
                or not 1 <= len(text) <= MAX_QUERY_CHARS
                or type(exact) is not bool
            ):
                return {
                    "ok": False,
                    "error": "Supply 1–350 search characters and an optional boolean exact flag.",
                }
            term = text.casefold()
            limit = MAX_FIND_MATCHES

        # Sparse traversal avoids materializing empty cells for a full-sheet request.
        cells, total = [], 0
        for row, col, address, display in sheet_cells:
            if op == "range" and not (top <= row <= bottom and left <= col <= right):
                continue
            if op == "find" and not (
                display.casefold() == term if exact else term in display.casefold()
            ):
                continue
            total += 1
            if len(cells) < limit:
                cells.append([address, display])

        result.update(cells=cells, total=total, truncated=total > limit)
        if op == "range":
            result["blank_count"] = result["range_size"] - total
        return result
