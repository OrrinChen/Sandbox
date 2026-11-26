"""Execute spreadsheet formula edits against stripped, immutable input workbooks.

The public artifact is a workbook plus the requested destination range. Targets
and the two reference edit plans live in scorer data opened only by scoring.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache
import gzip
import io
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

DATA = Path(__file__).with_name("sheet_data")
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
ADDRESS = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})\Z")
# Spreadsheet evaluation supports local cell calculations; external links,
# macros, dynamic data sources and paths are outside this task's tool surface.
FUNCTIONS = frozenset(
    """
ABS ACOS ADDRESS AGGREGATE AND AREAS ASIN ATAN ATAN2 AVERAGE AVERAGEA
AVERAGEIF AVERAGEIFS CEILING CEILING.MATH CEILING.PRECISE CHAR CHOOSE CLEAN CODE
COLUMN COLUMNS COMBIN CONCAT CONCATENATE COS COUNT COUNTA COUNTBLANK COUNTIF
COUNTIFS DATE DATEDIF DATEVALUE DAY DAYS DAYS360 DECIMAL DEGREES EDATE EOMONTH
EVEN EXACT EXP FACT FILTER FIND FIXED FLOOR FLOOR.MATH FLOOR.PRECISE FREQ FREQUENCY
HLOOKUP HOUR IF IFERROR IFNA IFS INDEX INDIRECT INT ISBLANK ISERR ISERROR ISEVEN
ISLOGICAL ISNA ISNUMBER ISODD ISREF ISTEXT LARGE LEFT LEN LN LOG LOG10 LOOKUP
LOWER MATCH MAX MAXIFS MEDIAN MID MIN MINIFS MINUTE MOD MODE MODE.SNGL MONTH
MROUND N NA NETWORKDAYS NETWORKDAYS.INTL NOT NUMBERVALUE ODD OFFSET OR
PERCENTILE PERCENTILE.INC PERCENTRANK PI POWER PRODUCT PROPER QUOTIENT RADIANS
RANK RANK.EQ REPLACE REPT RIGHT ROMAN ROUND ROUNDDOWN ROUNDUP ROW ROWS SEARCH
SECOND SIGN SIN SMALL SORT SQRT STDEV STDEV.S SUBSTITUTE SUBTOTAL SUM SUMIF
SUMIFS SUMPRODUCT SUMSQ SWITCH T TAN TEXT TEXTJOIN TIME TIMEVALUE TRANSPOSE
TRIM TRUE FALSE TRUNC TYPE UNIQUE UPPER VALUE VLOOKUP WEEKDAY WEEKNUM WORKDAY
WORKDAY.INTL XLOOKUP XMATCH YEAR YEARFRAC
""".split()
)


def safe_formula(formula: str) -> bool:
    if (
        not isinstance(formula, str)
        or not formula.startswith("=")
        or len(formula) > 2800
    ):
        return False
    if any(x in formula for x in ("|", "[", "]", "://", "\\", "\x00")):
        return False
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", formula):
        return False
    # Retain function recognition outside quoted strings and quoted sheet names.
    plain = re.sub(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'', "", formula.upper())
    return all(fn in FUNCTIONS for fn in re.findall(r"([A-Z_][A-Z_0-9.]*)\s*\(", plain))


@lru_cache(maxsize=1)
def _public():
    return {r["task_id"]: r for r in json.loads((DATA / "public.json").read_text())}


@lru_cache(maxsize=1)
def _private():
    with gzip.open(DATA / "scorer.json.gz", "rt", encoding="utf8") as stream:
        return json.load(stream)


def records():
    return [dict(r) for r in _public().values()]


def _input(task_id, filename="inputs.zip"):
    with zipfile.ZipFile(DATA / filename) as archive:
        return archive.read(_public()[task_id]["source_group"] + ".xlsx")


def materialize(task_id, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "input.xlsx").write_bytes(_input(task_id))
    (directory / "formula_support.txt").write_text(
        "Formula edits may use local references, arithmetic and these offline functions.\n"
        + ", ".join(sorted(FUNCTIONS))
        + "\n",
        encoding="utf-8",
    )


def run_reference(task_id):
    return {"formulas": dict(_private()[task_id]["reference"])}


def run_negative(task_id):
    formulas = run_reference(task_id)["formulas"]
    formulas.update(_private()[task_id]["wrong_edit"])
    return {"formulas": formulas}


def candidate_from_file(path):
    return json.loads(Path(path).read_text())


def save_candidate(task_id, candidate, path):
    Path(path).write_text(json.dumps(candidate, ensure_ascii=False) + "\n")


def _sheet_parts(archive, sheet):
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_id = next(
        x.attrib[REL] for x in workbook.iter(NS + "sheet") if x.get("name") == sheet
    )
    target = next(x.attrib["Target"] for x in rels if x.get("Id") == rel_id)
    member = (
        target.lstrip("/")
        if target.startswith("/")
        else posixpath.normpath("xl/" + target)
    )
    return member, ET.fromstring(archive.read(member))


def sheet_values(data, sheet, addresses):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        _, root = _sheet_parts(archive, sheet)
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [
                "".join(y.text or "" for y in x.iter(NS + "t"))
                for x in ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ]
        values = {}
        for cell in root.iter(NS + "c"):
            addr = cell.get("r")
            if addr not in addresses:
                continue
            tag, value = cell.get("t", "n"), cell.findtext(NS + "v")
            if tag == "inlineStr":
                tag = "s"
                value = "".join(x.text or "" for x in cell.iter(NS + "t"))
            elif tag == "s" and value is not None:
                value = shared[int(value)]
            elif tag == "str":
                tag = "s"
            if value not in (None, ""):
                values[addr] = [tag, value]
        return values


def _coord(address):
    match = ADDRESS.fullmatch(address)
    if not match:
        raise ValueError("Invalid cell address")
    col = 0
    for ch in match[1]:
        col = col * 26 + ord(ch) - 64
    return int(match[2]), col


def render(data, sheet, formulas):
    """Set only cell formulas. The workbook's remaining state comes from the input."""
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as dest,
    ):
        member, root = _sheet_parts(source, sheet)
        body = root.find(NS + "sheetData")
        rows = {int(r.get("r")): r for r in body.iter(NS + "row")}
        for addr, expr in formulas.items():
            row_id, col = _coord(addr)
            if not safe_formula(expr):
                raise ValueError("Use an offline local-cell formula")
            row = rows.get(row_id)
            if row is None:
                row = ET.Element(NS + "row", r=str(row_id))
                rows[row_id] = row
                offset = next(
                    (i for i, r in enumerate(body) if int(r.get("r")) > row_id),
                    len(body),
                )
                body.insert(offset, row)
            cell = next((c for c in row if c.get("r") == addr), None)
            if cell is None:
                cell = ET.Element(NS + "c", r=addr)
                offset = next(
                    (i for i, c in enumerate(row) if _coord(c.get("r"))[1] > col),
                    len(row),
                )
                row.insert(offset, cell)
            for child in list(cell):
                cell.remove(child)
            cell.attrib.pop("t", None)
            ET.SubElement(cell, NS + "f").text = expr[1:]
        for path in source.namelist():
            dest.writestr(
                source.getinfo(path),
                ET.tostring(root, encoding="utf-8")
                if path == member
                else source.read(path),
            )
    return buffer.getvalue()


def recalculate(files, output, timeout):
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        raise RuntimeError(
            "Spreadsheet formula execution requires LibreOffice Calc (soffice)."
        )
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sandbox-calc-profile-") as prof:
        subprocess.run(
            [
                binary,
                "-env:UserInstallation=" + Path(prof).as_uri(),
                "--headless",
                "--nologo",
                "--nodefault",
                "--norestore",
                "--convert-to",
                "xlsx:Calc MS Excel 2007 XML",
                "--outdir",
                str(output),
                *map(str, files),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
        )


def equivalent(actual, expected):
    if actual.keys() != expected.keys():
        return False
    for key, (tag, value) in expected.items():
        other_tag, other = actual[key]
        if tag != other_tag:
            return False
        if tag == "n":
            try:
                a, b = Decimal(other), Decimal(value)
                if not (a.is_finite() and b.is_finite()) or abs(a - b) > max(
                    Decimal("1e-9"), abs(b) * Decimal("1e-11")
                ):
                    return False
            except InvalidOperation:
                return False
        elif other != value:
            return False
    return True


SCENARIOS = (("inputs.zip", "gold"), ("scorer_variants.zip", "variant_gold"))


def _candidate_ok(task_id, candidate):
    if not isinstance(candidate, dict) or set(candidate) != {"formulas"}:
        return False
    formulas = candidate["formulas"]
    return (
        isinstance(formulas, dict)
        and bool(formulas)
        and set(formulas) <= set(_private()[task_id]["addresses"])
        and all(safe_formula(f) for f in formulas.values())
    )


class WorkbookConversionError(RuntimeError):
    """Calc failed to return the result of a particular set of edits."""


def _batch(jobs, home):
    """Run each candidate on both inputs, keeping the two gold grids in the parent."""
    files = []
    for task_id, label, candidate in jobs:
        row = _public()[task_id]
        for input_file, gold_key in SCENARIOS:
            path = home / f"{task_id}-{label}-{gold_key}.xlsx"
            path.write_bytes(
                render(
                    _input(task_id, input_file), row["worksheet"], candidate["formulas"]
                )
            )
            files.append(path)
    try:
        recalculate(files, home / "result", 180)
    except subprocess.SubprocessError as exc:
        raise WorkbookConversionError("Calc conversion failed") from exc
    results = {}
    for task_id, label, _ in jobs:
        public, private = _public()[task_id], _private()[task_id]
        ok = True
        for _, key in SCENARIOS:
            out = home / "result" / f"{task_id}-{label}-{key}.xlsx"
            if not out.is_file():
                raise WorkbookConversionError(
                    f"Calc did not recalculate {task_id} ({label}/{key})"
                )
            try:
                values = sheet_values(
                    out.read_bytes(), public["worksheet"], set(private["addresses"])
                )
            except (
                zipfile.BadZipFile,
                ET.ParseError,
                KeyError,
                IndexError,
                ValueError,
                StopIteration,
            ) as exc:
                raise WorkbookConversionError(
                    f"Unreadable Calc output for {task_id}"
                ) from exc
            ok = equivalent(values, private[key]) and ok
        results[task_id, label] = ok
    return results


def _isolated_results(jobs):
    try:
        with tempfile.TemporaryDirectory(prefix="sandbox-grade-sheets-") as temp:
            return _batch(jobs, Path(temp))
    except WorkbookConversionError:
        if len(jobs) > 1:
            mid = len(jobs) // 2
            return {**_isolated_results(jobs[:mid]), **_isolated_results(jobs[mid:])}
        # A failing solution earns a miss only when the same engine can still
        # score a known-good solution on this specific workbook and hidden variant.
        task_id, label, _ = jobs[0]
        with tempfile.TemporaryDirectory(prefix="sandbox-calc-check-") as temp:
            control = _batch([(task_id, "control", run_reference(task_id))], Path(temp))
        if not control[task_id, "control"]:
            raise RuntimeError(f"Calc could not verify the reference for {task_id}")
        return {(task_id, label): False}


def batch_grade(candidates: dict[str, object]) -> dict[str, bool]:
    """Return a verdict per input ID; unknown tasks and malformed edits are rejected individually."""
    results = dict.fromkeys(candidates, False)
    jobs = []
    for task_id, candidate in candidates.items():
        if task_id in _public() and _candidate_ok(task_id, candidate):
            jobs.append((task_id, "candidate", candidate))
    for start in range(0, len(jobs), 12):
        judged = _isolated_results(jobs[start : start + 12])
        for (task_id, _), verdict in judged.items():
            results[task_id] = verdict
    return results


def grade(task_id, candidate):
    return batch_grade({task_id: candidate})[task_id]


def calibration(task_ids):
    """Batch the same workbook executions used to score a real submission."""
    ids = list(dict.fromkeys(task_ids))
    reports = {}
    with tempfile.TemporaryDirectory(prefix="sandbox-calibrate-sheets-") as temp:
        root = Path(temp)
        for i in range(0, len(ids), 12):
            section = ids[i : i + 12]
            jobs = [
                (task, label, fn(task))
                for task in section
                for label, fn in (("ref", run_reference), ("neg", run_negative))
            ]
            if any(not _candidate_ok(task, candidate) for task, _, candidate in jobs):
                raise ValueError("Invalid stored calibration formula")
            results = _batch(jobs, root)
            for task in section:
                reports[task] = (results[task, "ref"], results[task, "neg"])
    return reports
