"""Adapt verified spreadsheet formula tasks from locally supplied pinned upstream archives.

Run with the two original .tar.gz files. The optional curation dependencies are
openpyxl and LibreOffice Calc; scoring in the installed wheel needs Calc only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import gzip
import io
import json
from pathlib import Path
import re
import sys
import subprocess
import tarfile
import warnings
import zipfile

from openpyxl import load_workbook, Workbook
from openpyxl.utils import range_boundaries, get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sandboxed_agent_eval_harness.benchmarks.independent import spreadsheets as ss

BASE_URL = "https://huggingface.co/datasets/KAKA22/SpreadsheetBench"
REV = "ab0b742b0fc95b946f212d80ac7771b5531272e4"
ARCHIVES = {
    "verified": (
        "spreadsheetbench_verified_400",
        "spreadsheetbench_verified_400.tar.gz",
        "10ef893dd29cb13ab97143ea787e68cdc9574a13873ab9a54e50b31dc03fc949",
    ),
    "original": (
        "all_data_912_v0.1",
        "spreadsheetbench_912_v0.1.tar.gz",
        "9cf7228b54f1edcdd4b372eb736774adf29cb4f804c9920229bac6c154833399",
    ),
}
# Restrict this adapter to cell calculations, not formatting, macros or styling.
NOT_FORMULA = re.compile(
    r"\b(?:vba|macro|bold|font|unmerge|highlight|formatted in (?:red|green)|by (?:cell )?colou?r|"
    r"today|yesterday|current (?:day|date|time)|workbook password|external workbook|pivot table|"
    r"press (?:a |the )?button|conditional formatting|text box|drop.down|hyperlink|twitter|email|e-mail|"
    r"stock ticker|patient|disease|medication|medical|military|weapon|warhead|pathogen|virus|battery of weapons|"
    r"exploit|hacking|password|breach|credit card|social security|home address|first name|last name|middle initial)\b",
    re.I,
)
SENSITIVE = re.compile(
    r"(?:https?://|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{3}-\d{2}-\d{4}\b|"
    r"\b\(?\d{3}\)?[- .]\d{3}[- .]\d{4}\b|(?:[A-Z]:\\|/Users/|/home/)|"
    r"\b(?:password|social security|phone number|telephone|passport|birth date|e-mail|email address)\b)",
    re.I,
)
NAME_FIELD = re.compile(
    r"^(?:(?:employee|salesperson|customer|agent|client|staff|first|last|contact|driver|applicant)\s*(?:name|names)?|full name|person|name|names)$",
    re.I,
)
# Single forum problems can share a numerical source stem. Keep at most one.
CELL_REF = re.compile(r"(?<![A-Z0-9_])(?:\$?[A-Z]{1,3}\$?[1-9][0-9]*)(?![A-Z0-9_(])")
SIMPLE_RANGE = re.compile(r"[A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?\Z", re.I)
SEED = "sandbox-independent-sheet-v1"
# Semantic review found that the original test lookup duplicated a development
# problem on its actual unique keys, despite using a different Excel formula.
REPLACEMENT = {
    "removed": "sheet-5835",
    "overlaps_with": "sheet-39931",
    "replacement": "sheet-43775",
    "reason": "Both original tasks retrieve a single value by two keys; the new task distributes a list across repeated four-column blocks.",
}
# A values-only input cannot represent visibility, borders, colour or drawing
# operations. Avoid personnel records and any workbook mirroring expected data.
EXCLUDE_TEXT = re.compile(
    r"\b(?:formatting|recreate|bolded|bordered|bordering|highlighted|shaded|colored|coloured|"
    r"vba|macros?|drop[- ]?down|hidden rows|wrap text|data validation list|person(?:s|nel)?|people|"
    r"named|surnames?|employees?|staff|students?|salaries|payroll|contacts?|workers?|clients?|"
    r"customers?|patients?|drivers?|doctors?|birthdays?|vetters?|member names?|first names?|last names?|"
    r"first and last|family names?|employee numbers?|home addresses?|login|offender|referral|transfers? a phone call)\b",
    re.I,
)
EXCLUDE_ID = {
    "41691": "instruction requests removal of #REF without specifying what value to compute",
    "54675": "multiple identifiable personal names in both input and search prompt",
    "52964": "clinical operative records and dates of birth",
    "55421": "appointment records",
    "55817": "input includes the correct answer in an adjacent column",
    "3002": "original workbook requests ungraded formatting changes",
    "59433": "location identifiers in field records",
}
ANSWER_HEADER = re.compile(
    r"^\s*(?:desired results?|expected (?:results?|answers?|output)|known solution|correct answers?)\s*[:.]?\s*$",
    re.I,
)


def digest(data):
    return sha256(data).hexdigest()


def zip_data(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, b in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, b)
    return data.getvalue()


def canonical(data):
    return (
        json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def boxes(pos, sheet, default):
    parts = re.split(r"[,;]", pos.replace("$", "").strip())
    all_cells = set()
    for item in parts:
        if "!" in item:
            tab, item = item.rsplit("!", 1)
            tab = tab.strip().strip("'")
            if sheet and tab != sheet and len(parts) > 1:
                raise ValueError("multiple target sheets")
            sheet = tab
        item = item.strip().strip("'").upper()
        if not SIMPLE_RANGE.fullmatch(item):
            raise ValueError("non finite target")
        a, b, c, d = range_boundaries(item)
        if (c - a + 1) * (d - b + 1) > 400 or d > 2000 or c > 130:
            raise ValueError("large answer range")
        all_cells.update(
            get_column_letter(col) + str(row)
            for col in range(a, c + 1)
            for row in range(b, d + 1)
        )
    sheet = sheet or default
    if len(all_cells) > 400:
        raise ValueError("large answer range")
    return sheet, all_cells


def snapshots(zip_path):
    """Project raw cells to a clean workbook, retaining values and date formats only."""
    orig = load_workbook(io.BytesIO(zip_path), data_only=True, keep_links=False)
    dest = Workbook()
    dest.remove(dest.active)
    rows = 0
    for old in orig:
        if old.sheet_state != "visible":
            raise ValueError("hidden sheet")
        if len(old._cells) > 12000 or len(orig.worksheets) > 9:
            raise ValueError("large input")
        new = dest.create_sheet(old.title)
        if SENSITIVE.search(old.title):
            raise ValueError("contact metadata")
        name_headers = []
        for c in old._cells.values():
            v = c.value
            if v is None:
                continue
            rows += 1
            if rows > 12000:
                raise ValueError("large input")
            if isinstance(v, str):
                if ANSWER_HEADER.fullmatch(v) or EXCLUDE_TEXT.search(v):
                    raise ValueError("unscored formatting, personnel or answer hints")
                if len(v) > 1600 or SENSITIVE.search(v):
                    raise ValueError("contact or remote content")
                if NAME_FIELD.fullmatch(v.strip()):
                    name_headers.append((c.row, c.column))
                if v.startswith("="):
                    raise ValueError("untrusted cached formula string")
            copied = new[c.coordinate]
            copied.value = v
            if c.data_type == "e":
                copied.data_type = "e"
            if isinstance(v, (date, time, timedelta)):
                copied.number_format = c.number_format
            elif isinstance(v, (int, float)) and c.number_format in (
                "0%",
                "0.00%",
                "0.0%",
            ):
                copied.number_format = c.number_format
        for row, col in name_headers:
            for cell in old._cells.values():
                if (
                    cell.column == col
                    and row < cell.row
                    and isinstance(cell.value, str)
                ):
                    value = cell.value.strip()
                    if re.fullmatch(r"[A-Z][a-z]+(?:[- ][A-Z][a-z]+)+", value):
                        raise ValueError("person-name column")
    dest.epoch = orig.epoch
    dest.properties.creator = "Sandbox spreadsheet fixtures"
    dest.properties.lastModifiedBy = None
    dest.properties.created = dest.properties.modified = datetime(2000, 1, 1)
    out = io.BytesIO()
    dest.save(out)
    with zipfile.ZipFile(io.BytesIO(out.getvalue())) as archive:
        parts = {k: archive.read(k) for k in archive.namelist()}
    # openpyxl stamps modified with wall-clock time when saving.
    parts["docProps/core.xml"] = re.sub(
        rb"(<dcterms:modified[^>]*>).*?(</dcterms:modified>)",
        rb"\g<1>2000-01-01T00:00:00Z\g<2>",
        parts["docProps/core.xml"],
    )
    return zip_data(parts), list(orig.sheetnames)


def formula_value(cell):
    val = cell.value
    if isinstance(val, ArrayFormula):
        return val.text
    return val if cell.data_type == "f" and isinstance(val, str) else None


def prepare(d, version, initial, golden):
    if (
        str(d["id"]) in EXCLUDE_ID
        or EXCLUDE_TEXT.search(d["instruction"])
        or d["instruction_type"] != "Cell-Level Manipulation"
        or NOT_FORMULA.search(d["instruction"])
        or SENSITIVE.search(d["instruction"])
    ):
        raise ValueError("out of scope")
    if len(initial) > 95000 or len(golden) > 155000:
        raise ValueError("large input")
    a = load_workbook(io.BytesIO(golden), keep_links=False)
    target, addresses = boxes(
        d["answer_position"], d.get("answer_sheet"), a.active.title
    )
    formulas = {}
    snapshot, sheets = snapshots(initial)
    if target not in sheets:
        raise ValueError("missing input sheet")
    before = ss.sheet_values(snapshot, target, addresses)
    expected = ss.sheet_values(golden, target, addresses)
    if any(t == "e" for t, v in expected.values()):
        raise ValueError("error in gold target")
    for addr in sorted(addresses):
        cell = a[target][addr]
        f = formula_value(cell)
        if f:
            if not ss.safe_formula(f):
                raise ValueError("unsupported formula")
            formulas[addr] = f
        elif before.get(addr) != expected.get(addr):
            raise ValueError("gold is not executable")
    if not formulas or not any(CELL_REF.search(v) for v in formulas.values()):
        raise ValueError("no working formula")
    if ss.equivalent(before, expected):
        raise ValueError("input already passes")
    # Replace one formula with a stale source reference. Prefer a preceding
    # target when available, otherwise use one of the original formula inputs.
    options = []
    for address, expr in formulas.items():
        for m in CELL_REF.finditer(expr.upper()):
            shift = expr[m.start() : m.end()]
            if shift.replace("$", "") == address:
                continue
            options.append({address: "=" + shift})
            break
        if len(options) >= 8:
            break
    if not options:
        raise ValueError("no executable wrong edit")
    ident = str(d["id"])
    group = "sheet-" + ident
    return {
        "public": {
            "task_id": group,
            "source_group": group,
            "domain": "file_workflow",
            "instruction": d["instruction"]
            + " Submit the local workbook formula edits as JSON with a formulas object keyed by cell address. Use the supplied input.xlsx. The scorer applies the same formulas to this workbook and a second input with different values, checking the specified target cells in both.",
            "tool": "spreadsheet.edit_formulas",
            "worksheet": target,
            "answer_range": d["answer_position"],
            "upstream_archive": version,
            "provenance": BASE_URL + "/tree/" + REV,
            "upstream_task_id": ident,
            "upstream_input_sha256": digest(initial),
            "upstream_gold_sha256": digest(golden),
        },
        "private": {
            "addresses": sorted(addresses),
            "gold": expected,
            "reference": formulas,
        },
        "input": snapshot,
        "options": options,
    }


def read_archive(path, version, number=1):
    label = ARCHIVES[version][0]
    files = {}
    with tarfile.open(path, "r|gz") as tar:
        for entry in tar:
            if entry.isfile() and (
                entry.name == label + "/dataset.json"
                or (f"/{number}_" in entry.name and entry.name.endswith(".xlsx"))
            ):
                files[entry.name] = tar.extractfile(entry).read()
    for d in json.loads(files.pop(label + "/dataset.json")):
        i = str(d["id"])
        stem = f"{label}/spreadsheet/{i}/{number}_{i}_"
        suffix = ("init", "golden") if version == "verified" else ("input", "answer")
        if all(stem + n + ".xlsx" in files for n in suffix):
            yield d, *(files[stem + n + ".xlsx"] for n in suffix)


def same_parts(cached, rendered):
    """Compare the complete OpenXML package while ignoring external ZIP timestamps."""
    if not cached or not cached.is_file():
        return False
    with zipfile.ZipFile(cached) as a, zipfile.ZipFile(io.BytesIO(rendered)) as b:
        return set(a.namelist()) == set(b.namelist()) and all(
            a.read(k) == b.read(k) for k in b.namelist()
        )


def validate_batch(batch, folder, tries, prior=None):
    folder.mkdir(parents=True, exist_ok=False)
    files = []
    (folder / "out").mkdir()
    for case in batch:
        pub = case["public"]
        private = case["private"]
        group = pub["source_group"]
        alternatives = [private["reference"]] + [
            dict(private["reference"], **m) for m in case["options"][:tries]
        ]
        for i, plan in enumerate(alternatives):
            f = folder / f"{group}-{i}.xlsx"
            data = ss.render(case["input"], pub["worksheet"], plan)
            f.write_bytes(data)
            cached = prior.get(f.name) if prior else None
            if (
                cached
                and same_parts(cached, data)
                and (cached.parent / "out" / f.name).is_file()
            ):
                (folder / "out" / f.name).write_bytes(
                    (cached.parent / "out" / f.name).read_bytes()
                )
            else:
                files.append(f)
    try:
        if files:
            ss.recalculate(files, folder / "out", 180)
    except (OSError, subprocess.SubprocessError):
        pass
    accepted = []
    for case in batch:
        p = case["public"]
        s = case["private"]
        group = p["source_group"]

        def get_values(index):
            f = folder / "out" / f"{group}-{index}.xlsx"
            return (
                ss.sheet_values(f.read_bytes(), p["worksheet"], set(s["addresses"]))
                if f.exists()
                else None
            )

        actual = get_values(0)
        if actual is None or not ss.equivalent(actual, s["gold"]):
            continue
        for index, wrong in enumerate(case["options"][:tries], 1):
            bad = get_values(index)
            if (
                bad
                and all(tag != "e" for tag, v in bad.values())
                and not ss.equivalent(bad, s["gold"])
            ):
                s["wrong_edit"] = wrong
                accepted.append(case)
                break
    return accepted


def second_inputs(selected, archive, folder, workers, prior=None):
    """Admit only formulas that also compute a distinct official held-out result."""
    pool = {c["public"]["upstream_task_id"]: c for c in selected}
    items = []
    folder.mkdir(parents=True, exist_ok=False)
    for source, raw, gold in read_archive(archive, "original", 2):
        case = pool.get(str(source["id"]))
        if case is None:
            continue
        public, private = case["public"], case["private"]
        coords, tab = set(private["addresses"]), public["worksheet"]
        try:
            if len(raw) > 95000 or len(gold) > 155000:
                continue
            data, tabs = snapshots(raw)
            if tab not in tabs:
                continue
            expected = ss.sheet_values(gold, tab, coords)
            if (
                not expected
                or any(k == "e" for k, _ in expected.values())
                or ss.equivalent(expected, private["gold"])
                or ss.equivalent(ss.sheet_values(data, tab, coords), expected)
            ):
                continue
            file = folder / (public["task_id"] + ".xlsx")
            file.write_bytes(ss.render(data, tab, private["reference"]))
        except (
            ValueError,
            TypeError,
            AttributeError,
            StopIteration,
            IndexError,
            KeyError,
            zipfile.BadZipFile,
        ):
            continue
        case["variant_input"] = data
        private["variant_gold"] = expected
        private["upstream_variant_input_sha256"] = digest(raw)
        private["upstream_variant_gold_sha256"] = digest(gold)
        items.append((file, case))

    def compute(start):
        batch = items[start : start + 20]
        output = folder / f"out-{start}"
        output.mkdir()
        todo = []
        for f, _ in batch:
            cached = prior / "second" / f.name if prior else None
            earlier = (
                next((prior / "second").glob("out-*/" + f.name), None)
                if prior
                else None
            )
            if earlier and same_parts(cached, f.read_bytes()):
                (output / f.name).write_bytes(earlier.read_bytes())
            else:
                todo.append(f)
        if todo:
            ss.recalculate(todo, output, 180)
        valid = set()
        for file, case in batch:
            outcome = output / file.name
            if not outcome.is_file():
                continue
            p, v = case["public"], case["private"]
            actual = ss.sheet_values(
                outcome.read_bytes(), p["worksheet"], set(v["addresses"])
            )
            if ss.equivalent(actual, v["variant_gold"]):
                valid.add(p["task_id"])
        return valid

    with ThreadPoolExecutor(max_workers=workers) as executor:
        ids = set().union(*executor.map(compute, range(0, len(items), 20)))
    return [c for c in selected if c["public"]["task_id"] in ids]


def structure(formulas):
    """Replace input addresses, text and numeric literals when detecting template twins."""

    def shape(formula):
        text = re.sub(r'"(?:[^"]|"")*"', '"text"', formula.upper())
        text = re.sub(r"(?:'[^']+'|[A-Z][A-Z0-9_ ]*)!", "SHEET!", text)
        text = CELL_REF.sub("CELL", text)
        return re.sub(r"(?<![A-Z0-9])[0-9]+(?:\.[0-9]+)?", "N", text).replace(" ", "")

    return tuple(sorted({shape(f) for f in formulas.values()}))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--verified", required=True, type=Path)
    cli.add_argument("--original", required=True, type=Path)
    cli.add_argument("--output", type=Path, default=ss.DATA)
    cli.add_argument("--work", required=True, type=Path)
    cli.add_argument("--workers", type=int, default=3)
    cli.add_argument(
        "--prior",
        type=Path,
        help="Reuse a locally calculated workbook only after matching its exact rendered input bytes",
    )
    args = cli.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    cases = {}
    seen_ids = set()
    reject = Counter()
    hashes = {}
    for version, path in [("verified", args.verified), ("original", args.original)]:
        hashes[version] = digest(path.read_bytes())
        if hashes[version] != ARCHIVES[version][2]:
            raise ValueError(
                "Unexpected source archive " + version + " " + hashes[version]
            )
        for d, inp, gold in read_archive(path, version):
            i = str(d["id"])
            if i in seen_ids:
                continue
            seen_ids.add(i)
            try:
                cases[i] = prepare(d, version, inp, gold)
            except (
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
                IndexError,
                zipfile.BadZipFile,
            ) as exc:
                reject[str(exc)[:60]] += 1
        print(
            version,
            "candidate tasks",
            len(cases),
            "exclusions",
            dict(reject),
            flush=True,
        )

    def priority(c):
        p = c["public"]
        return (
            p["upstream_archive"] != "verified",
            digest((SEED + ":sample:" + p["source_group"]).encode()),
        )

    candidates = sorted(cases.values(), key=priority)
    # A source-stem and normalized source problem are each represented once.
    batches = [candidates[i : i + 12] for i in range(0, len(candidates), 12)]
    prior = {f.name: f for f in args.prior.glob("batch-*/*.xlsx")} if args.prior else {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(validate_batch, b, args.work / f"batch-{i:03}", 2, prior)
            for i, b in enumerate(batches)
        ]
        accepted = []
        for i, f in enumerate(futures):
            accepted.extend(f.result())
            print(
                "calculated",
                i + 1,
                "of",
                len(batches),
                "accepted",
                len(accepted),
                flush=True,
            )
    groups = set()
    problems = set()
    inputs = set()
    shapes = set()
    filtered = []
    for c in sorted(accepted, key=priority):
        p = c["public"]
        source = p["upstream_task_id"].split("-")[0]
        instruction = re.sub(r"[^a-z0-9 ]", " ", p["instruction"].lower())
        sig = " ".join(instruction.split())
        signature = digest(c["input"])
        method = structure(c["private"]["reference"])
        if (
            source in groups
            or sig in problems
            or signature in inputs
            or method in shapes
        ):
            continue
        groups.add(source)
        problems.add(sig)
        inputs.add(signature)
        shapes.add(method)
        filtered.append(c)
    double_verified = second_inputs(
        filtered, args.original, args.work / "second", args.workers, args.prior
    )
    selected = double_verified[:120]
    ordered = sorted(
        selected,
        key=lambda c: digest((SEED + ":split:" + c["public"]["source_group"]).encode()),
    )
    public = []
    private = {}
    books = {}
    variants = {}
    surplus = {c["public"]["task_id"]: c for c in double_verified[120:]}
    if REPLACEMENT["removed"] not in {c["public"]["task_id"] for c in selected}:
        raise ValueError("Expected reviewed worksheet in the initial selection")
    for i, c in enumerate(ordered):
        if c["public"]["task_id"] == REPLACEMENT["removed"]:
            c = surplus[REPLACEMENT["replacement"]]
        p = c["public"]
        p["split"] = "dev" if i < round(len(ordered) / 6) else "test"
        key = p["task_id"]
        public.append(p)
        private[key] = c["private"]
        books[key + ".xlsx"] = c["input"]
        variants[key + ".xlsx"] = c["variant_input"]
    # Keep the original three calculated cases from SpreadsheetBench grouped by
    # source: only the first workbook of each selected question is packaged.
    (args.output / "public.json").write_bytes(
        canonical(sorted(public, key=lambda p: p["task_id"]))
    )
    (args.output / "scorer.json.gz").write_bytes(
        gzip.compress(canonical(private), mtime=0)
    )
    (args.output / "inputs.zip").write_bytes(zip_data(books))
    (args.output / "scorer_variants.zip").write_bytes(zip_data(variants))
    report = {
        "two_distinct_inputs_verified": len(double_verified),
        "archives_sha256": hashes,
        "candidates": len(candidates),
        "reference_and_negative_verified": len(accepted),
        "unique_qualified": len(filtered),
        "selected": len(selected),
        "pre_freeze_replacement": REPLACEMENT,
        "split": dict(Counter(p["split"] for p in public)),
        "selected_sources": dict(Counter(p["upstream_archive"] for p in public)),
        "engine": "LibreOffice Calc opens a newly rendered workbook; expected values come from upstream golden workbook caches. Negative uses a stale source-cell reference and must produce a different non-error result.",
        "revision": REV,
        "licence": "CC BY-SA 4.0",
        "selected_sha256": {
            f: digest((args.output / f).read_bytes())
            for f in [
                "public.json",
                "scorer.json.gz",
                "inputs.zip",
                "scorer_variants.zip",
            ]
        },
    }
    (args.output / "curation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
