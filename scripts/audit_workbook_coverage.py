"""Compare the frozen public workbook excerpts with every cell in the original public XLSX."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

from run_independent_comparison import seal
from workbook_read_tool import MAX_CELL_CHARS

ROOT = Path(__file__).resolve().parents[1]
COMPARISON = ROOT / "scripts" / "independent_600" / "comparison"
ASSETS = ROOT / "src" / "sandboxed_agent_eval_harness" / "benchmarks" / "independent"


def workbook_coverage(task_id, observation, workbook):
    book = load_workbook(BytesIO(workbook), data_only=False, keep_links=False)
    sheets = {}
    try:
        if set(observation) != set(book.sheetnames):
            raise ValueError(f"Archived sheet inventory differs for {task_id}")
        for sheet in book:
            visible = observation[sheet.title]
            dimensions = [sheet.max_row, sheet.max_column]
            cells = {
                c.coordinate: c.value
                for c in sheet._cells.values()
                if c.value is not None
            }
            original = dict(visible["cells"])
            if (
                dimensions != list(visible["dimensions"])
                or len(cells) != visible["nonempty_count"]
            ):
                raise ValueError(
                    f"Archived sheet measurements differ for {task_id}/{sheet.title}"
                )
            if len(original) != len(visible["cells"]):
                raise ValueError(
                    f"Duplicate excerpt coordinates in {task_id}/{sheet.title}"
                )
            if any(
                a not in cells or str(cells[a])[:MAX_CELL_CHARS] != v
                for a, v in original.items()
            ):
                raise ValueError(
                    f"Overlapping cell display mismatch for {task_id}/{sheet.title}"
                )
            formula_objects = sum(
                isinstance(x, (ArrayFormula, DataTableFormula)) for x in cells.values()
            )
            if formula_objects:
                raise ValueError(
                    f"Archived display may contain unstable formula representation in {task_id}/{sheet.title}"
                )
            sheets[sheet.title] = {
                "dimensions": dimensions,
                "overlap_identical": True,
                "fixed_cells": len(original),
                "full_cells": len(cells),
                "extra_cells": len(cells) - len(original),
            }
    finally:
        book.close()
    return {
        "task_id": task_id,
        "public_xlsx_sha256": sha256(workbook).hexdigest(),
        "sheets": sheets,
        "overlap_identical": True,
        **{
            key: sum(sh[key] for sh in sheets.values())
            for key in ("fixed_cells", "full_cells", "extra_cells")
        },
    }


def audit():
    lock_path = COMPARISON / "input_lock.json"
    lock = json.loads(lock_path.read_bytes())
    release = ASSETS / "data" / "release.json"
    if sha256(release.read_bytes()).hexdigest() != lock["release_sha256"]:
        raise ValueError("Archived input lock points to another release")
    asset_hashes = json.loads(release.read_bytes())["assets"]
    for relative in ("sheet_data/public.json", "sheet_data/inputs.zip"):
        if (
            sha256((ASSETS / relative).read_bytes()).hexdigest()
            != asset_hashes[relative]
        ):
            raise ValueError(f"Changed public asset {relative}")
    records = json.loads((ASSETS / "sheet_data" / "public.json").read_bytes())
    groups = {r["task_id"]: r["source_group"] for r in records if r["split"] == "test"}
    rows = {}
    with ZipFile(ASSETS / "sheet_data" / "inputs.zip") as public:
        for batch, tasks in sorted(lock["batches"].items()):
            if not batch.startswith("spreadsheets-"):
                continue
            path = COMPARISON / "inputs" / (batch + ".json")
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != lock["input_hashes"][batch]:
                raise ValueError(f"Changed archived projection {batch}")
            packets = json.loads(raw)
            if [x["task_id"] for x in packets] != tasks:
                raise ValueError(f"Archived worksheet batch mismatch at {batch}")
            for record in packets:
                task = record["task_id"]
                if task in rows:
                    raise ValueError(f"Duplicate task {task}")
                workbook = public.read(groups[task] + ".xlsx")
                rows[task] = workbook_coverage(task, record["observation"], workbook)
    if set(rows) != set(groups):
        raise ValueError("Coverage of the frozen test set is incomplete")
    return {
        "release_sha256": lock["release_sha256"],
        "archived_input_lock_sha256": sha256(lock_path.read_bytes()).hexdigest(),
        "public_workbook_archive_sha256": asset_hashes["sheet_data/inputs.zip"],
        "definition": "Count each nonempty worksheet address once per task. Overlap compares the archived displayed string with the first 350 characters of the public cell display. Dimensions and the original disclosed nonempty counts must match.",
        "tasks": len(rows),
        "tasks_with_extra_cells": sum(r["extra_cells"] > 0 for r in rows.values()),
        **{
            k: sum(r[k] for r in rows.values())
            for k in ("fixed_cells", "full_cells", "extra_cells")
        },
        "rows": [rows[t] for t in sorted(rows)],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "scripts" / "workbook_access" / "public_coverage.json",
    )
    args = p.parse_args()
    coverage = audit()
    seal(args.out, coverage)
    print(
        json.dumps(
            {
                k: coverage[k]
                for k in (
                    "tasks",
                    "tasks_with_extra_cells",
                    "fixed_cells",
                    "full_cells",
                    "extra_cells",
                )
            }
        )
    )
