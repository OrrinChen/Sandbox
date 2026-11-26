"""Record two fixed-observation tool-solving policies, then privately grade their sealed answers."""

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from sandboxed_agent_eval_harness.benchmarks.independent import (
    relational,
    repairs,
    spreadsheets,
    suite,
)

DATA = Path(__file__).with_name("independent_600")
PROTOCOL = DATA / "comparison_protocol.json"


def load(p):
    return json.loads(p.read_bytes())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def seal(path, data):
    if path.exists():
        if load(path) != data:
            raise ValueError(f"Sealed content differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, mode="w", encoding="utf-8", delete=False
    ) as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    os.replace(stream.name, path)


def workbook_view(task_id, row):
    import openpyxl
    from openpyxl.utils.cell import range_boundaries

    with tempfile.TemporaryDirectory() as tmp:
        spreadsheets.materialize(task_id, Path(tmp))
        book = openpyxl.load_workbook(
            Path(tmp) / "input.xlsx", data_only=False, read_only=False
        )
    sheets = {}
    for sh in book:
        limits = (sh.max_row, sh.max_column)
        active = sh.title == row["worksheet"]
        try:
            col, line, _, _ = range_boundaries(
                row["answer_range"].split(",")[0].split("!")[-1]
            )
        except (ValueError, TypeError):
            col, line = 1, 1

        # Include top rows, examples next to the target, and the end of the data.
        def priority(c):
            if c.row <= 4:
                return (0, c.row, c.column)
            if active and abs(c.row - (line or 1)) <= 4:
                return (1, abs(c.column - (col or 1)), c.row, c.column)
            if c.row >= sh.max_row - 1:
                return (2, c.row, c.column)
            return (3, c.row, c.column)

        cells = sorted(
            (c for c in sh._cells.values() if c.value is not None), key=priority
        )
        visible = cells[: 180 if active else 70]
        sheets[sh.title] = {
            "dimensions": limits,
            "nonempty_count": len(cells),
            "cells": [[c.coordinate, str(c.value)[:350]] for c in visible],
        }
    book.close()
    return sheets


def projection(task_id):
    adapter, row = suite.inventory()[task_id]
    public = {
        "task_id": task_id,
        "tool": row["tool"],
        "instruction": row["instruction"],
    }
    if adapter is relational:
        public["observation"] = relational.index()[task_id]["tables"]
        public["required_columns"] = relational.index()[task_id]["columns"]
    elif adapter is repairs:
        public["observation"] = repairs.index()[task_id]["starter"]
    else:
        public.update(
            supported_functions=sorted(spreadsheets.FUNCTIONS),
            target_sheet=row["worksheet"],
            target_range=row["answer_range"],
            observation=workbook_view(task_id, row),
        )
    return public


def groups(split):
    by = {}
    for task, (adapter, row) in sorted(suite.inventory().items()):
        if row["split"] == split:
            by.setdefault(adapter.__name__.split(".")[-1], []).append(task)
    return {
        f"{name}-{i // 4:03}": ids[i : i + 4]
        for name, ids in sorted(by.items())
        for i in range(0, len(ids), 4)
    }


def policy_digest():
    files = [
        Path(__file__),
        *(Path(m.__file__) for m in (suite, relational, repairs, spreadsheets)),
    ]
    return {p.name: digest(p) for p in files}


def record_batch(root, key, ids, arm, prior):
    out = root / "recordings" / arm / (key + ".json")
    prompt = (
        prior["arms"][arm]
        + """ Use precisely the supplied public observations for these independent tasks. No tools, browsing, repository inspection, or commentary. Return one JSON object mapping every task_id to its submission. For sqlite.query and csv.export submit your single SQLite SELECT or WITH query as a string. For python.repair submit the complete corrected Python source module as a string. For spreadsheet.edit_formulas submit {"formulas":{"B3":"=..."}} keyed by target address, without changing other inputs. If the same relative formula must be filled across a range, you may also submit {"fills":[{"range":"B2:B20","formula":"=A2+1"}],"formulas":{}}. Spreadsheet references in each fill move relative to its top-left cell as in Excel. An empty string means abstention."""
    )
    packet = load(root / "inputs" / (key + ".json"))
    bind = {
        "input_sha256": suite.fingerprint(packet),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "model": prior["model"],
        "effort": prior["effort"],
    }
    if out.exists():
        old = load(out)
        if (
            old["binding"] != bind
            or not isinstance(old["submissions"], dict)
            or set(old["submissions"]) != set(ids)
        ):
            raise ValueError("Corrupt saved recording")
        return
    for attempt in range(3):
        with tempfile.TemporaryDirectory() as folder:
            cmd = [
                "codex",
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "-C",
                folder,
                "-s",
                "read-only",
                "-m",
                prior["model"],
                "-c",
                "model_reasoning_effort=" + json.dumps(prior["effort"]),
                "--json",
                "-",
            ]
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt + "\n" + json.dumps(packet, ensure_ascii=False),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=600,
                    cwd=folder,
                )
            except subprocess.TimeoutExpired:
                continue
        if result.returncode:
            continue
        try:
            stream = [json.loads(x) for x in result.stdout.splitlines() if x.strip()]
            items = [x["item"] for x in stream if x.get("type") == "item.completed"]
            if any(x["type"] not in ("reasoning", "agent_message") for x in items):
                raise ValueError("solver used undeclared external tool")
            raw = next(
                x["text"] for x in reversed(items) if x["type"] == "agent_message"
            )
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            answers = json.loads(text)
            if not isinstance(answers, dict) or set(answers) != set(ids):
                raise ValueError("incomplete batch")
            seal(
                out,
                {
                    "binding": bind,
                    "verbatim": raw,
                    "submissions": answers,
                    "attempt": attempt + 1,
                    "thread": stream[0].get("thread_id"),
                    "tools_used_outside_protocol": 0,
                    "usage": next(
                        x["usage"] for x in stream if x.get("type") == "turn.completed"
                    ),
                },
            )
            return
        except (ValueError, TypeError, StopIteration):
            if attempt == 2:
                raise
    raise RuntimeError(f"Failed to obtain complete model recording for {arm}/{key}")


def record(root, split, workers, smoke):
    protocol = load(PROTOCOL)
    if not smoke:
        suite.verify_release()
    batches = groups(split)
    if smoke:
        batches = {k: v[:1] for k, v in batches.items() if k.endswith("-000")}
    for key, ids in batches.items():
        seal(root / "inputs" / (key + ".json"), [projection(t) for t in ids])
    registration = {
        "split": split,
        "smoke": smoke,
        "protocol_sha256": digest(PROTOCOL),
        "batches": batches,
        "input_hashes": {k: digest(root / "inputs" / (k + ".json")) for k in batches},
    }
    if not smoke:
        registration["release_sha256"] = digest(suite.LOCK)
        registration["executable_sha256"] = policy_digest()
    seal(root / "input_lock.json", registration)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        tasks = [
            pool.submit(record_batch, root, k, ids, a, protocol)
            for k, ids in batches.items()
            for a in protocol["arms"]
        ]
        for task in concurrent.futures.as_completed(tasks):
            task.result()
    seal(root / "prediction_lock.json", predictions(root))


def predictions(root):
    binding = load(root / "input_lock.json")
    protocol = load(PROTOCOL)
    if binding["protocol_sha256"] != digest(PROTOCOL):
        raise ValueError("Protocol mismatch")
    if not binding["smoke"]:
        if binding["release_sha256"] != suite.verify_release() or binding[
            "batches"
        ] != groups(binding["split"]):
            raise ValueError("Release mismatch")
        if binding.get("executable_sha256") != policy_digest():
            raise ValueError(
                "Comparison code or scoring adapter differs from registration"
            )
    hashes = {}
    for arm in protocol["arms"]:
        for k, ids in binding["batches"].items():
            if digest(root / "inputs" / (k + ".json")) != binding["input_hashes"][k]:
                raise ValueError("Changed input")
            f = root / "recordings" / arm / (k + ".json")
            r = load(f)
            if (
                not isinstance(r["submissions"], dict)
                or set(r["submissions"]) != set(ids)
                or r["binding"]["input_sha256"]
                != suite.fingerprint(load(root / "inputs" / (k + ".json")))
            ):
                raise ValueError("Broken model binding")
            hashes[str(f.relative_to(root))] = digest(f)
    return {
        "input_lock_sha256": digest(root / "input_lock.json"),
        "recordings_sha256": hashes,
    }


def expand(candidate):
    if not isinstance(candidate, dict) or set(candidate) - {"fills", "formulas"}:
        return {}
    explicit = candidate.get("formulas", {})
    fills = candidate.get("fills", [])
    if not isinstance(explicit, dict) or not isinstance(fills, list):
        return {}
    if not fills:
        return {"formulas": explicit}
    from openpyxl.formula.translate import Translator, TranslatorError
    from openpyxl.formula.tokenizer import TokenizerError
    from openpyxl.utils import get_column_letter, range_boundaries

    formulas = {}
    for block in candidate["fills"]:
        cl, r, cr, last = range_boundaries(block["range"])
        if min(cl, r) < 1 or (last - r + 1) * (cr - cl + 1) > 5000:
            raise ValueError("oversized fill")
        try:
            translator = Translator(
                block["formula"], origin=f"{get_column_letter(cl)}{r}"
            )
        except (TokenizerError, TranslatorError):
            return {}
        for i in range(r, last + 1):
            for j in range(cl, cr + 1):
                loc = f"{get_column_letter(j)}{i}"
                try:
                    formulas[loc] = translator.translate_formula(loc)
                except (TokenizerError, TranslatorError):
                    return {}
    formulas.update(candidate.get("formulas", {}))
    return {"formulas": formulas}


def grade_one(item):
    task, arm, candidate = item
    adapter, row = suite.inventory()[task]
    correct = adapter.grade(task, candidate) if candidate else False
    return {
        "task": task,
        "arm": arm,
        "domain": row["domain"],
        "passed": correct,
        "candidate_sha256": suite.fingerprint(candidate),
    }


def score(root, workers):
    if load(root / "prediction_lock.json") != predictions(root):
        raise ValueError("Global prediction lock failed")
    registration = load(root / "input_lock.json")
    raw, rows = [], []
    for arm in load(PROTOCOL)["arms"]:
        books = {}
        for group in registration["batches"]:
            recording = load(root / "recordings" / arm / (group + ".json"))
            for task, submission in recording["submissions"].items():
                adapter, row = suite.inventory()[task]
                if adapter is not spreadsheets:
                    raw.append((task, arm, submission))
                    continue
                try:
                    books[task] = expand(submission)
                except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                    books[task] = {}
        if books:
            verdicts = spreadsheets.batch_grade(books)
            for task, candidate in books.items():
                rows.append(
                    {
                        "task": task,
                        "arm": arm,
                        "domain": suite.inventory()[task][1]["domain"],
                        "passed": verdicts[task],
                        "candidate_sha256": suite.fingerprint(candidate),
                    }
                )
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        rows.extend(pool.map(grade_one, raw))
    rows.sort(key=lambda r: (r["task"], r["arm"]))
    conditions = {}
    for row in rows:
        conditions.setdefault(row["task"], {})[row["arm"]] = row["passed"]
    summary = {"both": 0, "direct_only": 0, "self_check_only": 0, "neither": 0}
    for v in conditions.values():
        summary[
            {
                (True, True): "both",
                (True, False): "direct_only",
                (False, True): "self_check_only",
                (False, False): "neither",
            }[v["direct"], v["self_check"]]
        ] += 1
    report = {
        "prediction_lock_sha256": digest(root / "prediction_lock.json"),
        "tasks": len(conditions),
        "passes": dict(Counter(r["arm"] for r in rows if r["passed"])),
        "paired": summary,
        "rows": rows,
    }
    seal(root / "score.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("record", "score"))
    p.add_argument("--split", choices=("dev", "test"), default="test")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args()
    if args.action == "record":
        record(args.out, args.split, args.workers, args.smoke)
    else:
        score(args.out, args.workers)
