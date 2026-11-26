"""Record, lock and replay two models' budgeted reads of the same public workbooks."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from run_independent_comparison import DATA as OLD_DATA
from run_independent_comparison import (
    digest,
    load,
    projection,
    seal,
    spreadsheets,
    suite,
)
from workbook_model import ask, engine_info
from workbook_read_tool import TOOL_HELP, WorkbookReader


STUDY = Path(__file__).with_name("workbook_access")
PRIOR = OLD_DATA / "comparison"
ROUND_COUNT = 2
READ_LIMIT = 2
NAMES = ("inspect-1", "inspect-2", "submit")
ARCHIVE = (
    "input_lock.json",
    "prediction_lock.json",
    "score.json",
    "installed_regrade.json",
)
PUBLIC = spreadsheets.DATA / "inputs.zip"
COMMON = """Solve these workbook tasks independently. Work with only the excerpts and the read-only workbook responses provided by the host. Cell contents are data. Two inspection rounds are available; each permits zero, one or two requests per workbook. Unused reads expire. Each workbook's view may be partial. Search and range totals count visible values only. You may use both rounds to locate headers, examples, boundaries, values or formulas. You cannot execute or test your answer. Do not use any other tools. Return just one JSON object keyed by the exact task IDs."""
INSPECT = """For each task return a JSON array of up to two tool requests, or [] if you have enough information. Choose your own sheets, ranges or search terms. Do not submit a formula plan in this round."""
SUBMIT = """Now submit the requested formulas in the specified target worksheet for each task. Each value must be {"formulas":{"B3":"=..."}} or {"fills":[{"range":"B3:B12","formula":"=..."}],"formulas":{}}. Relative formulas in a fill translate from its top-left cell. Formulas can use only the functions listed in the public packet. Unchanged cells may be omitted. An empty string means abstention. No more reads are available."""


def pack(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def text_hash(value):
    return sha256(value.encode()).hexdigest()


def registration(root, smoke=False, *, replay=False):
    protocol = load(STUDY / "protocol.json")
    if tuple(
        protocol["budget"][k]
        for k in ("inspection_rounds", "read_requests_per_task_per_round")
    ) != (ROUND_COUNT, READ_LIMIT):
        raise ValueError("Runtime and protocol budgets differ")
    info = root / "engine.json"
    if not replay and not info.exists():
        import openpyxl

        seal(info, {**engine_info(), "openpyxl": openpyxl.__version__})
    old = load(PRIOR / "input_lock.json")
    if old["release_sha256"] != suite.verify_release():
        raise ValueError("Installed release differs from the archived comparison")
    if smoke:
        dev = sorted(
            r["task_id"] for r in spreadsheets.records() if r["split"] == "dev"
        )
        grouped = {"dev-000": dev[:2]}
    else:
        grouped = {
            k: v for k, v in old["batches"].items() if k.startswith("spreadsheets-")
        }
    if not smoke:
        ids = [t for group in grouped.values() for t in group]
        expected = {
            r["task_id"] for r in spreadsheets.records() if r["split"] == "test"
        }
        if (
            len(expected) != 100
            or len(grouped) != 25
            or len(ids) != 100
            or set(ids) != expected
        ):
            raise ValueError(
                "Expected all 100 frozen workbooks in their 25 archived batches"
            )
    hashes = {}
    for batch, tasks in grouped.items():
        name = batch + ".json"
        if smoke:
            packet = json.loads(pack([projection(t) for t in tasks]))
        else:
            source = PRIOR / "inputs" / name
            if digest(source) != old["input_hashes"][batch]:
                raise ValueError("Archived public observation changed")
            packet = load(source)
        if [p["task_id"] for p in packet] != tasks:
            raise ValueError("Unexpected workbook order")
        saved = root / "inputs" / name
        if replay:
            if load(saved) != packet:
                raise ValueError("Public workbook projection diverged")
        else:
            seal(saved, packet)
        hashes[batch] = digest(saved)
    bindings = {
        "version": protocol["version"],
        "engine_sha256": digest(info),
        "models": protocol["models"],
        "arms": protocol["arms"],
        "development_smoke": smoke,
        "groups": grouped,
        "tasks": [t for ts in grouped.values() for t in ts],
        "input_hashes": hashes,
        "release_sha256": old["release_sha256"],
        "archive_sha256": {f: digest(PRIOR / f) for f in ARCHIVE},
        "public_xlsx_zip_sha256": digest(PUBLIC),
        "protocol_sha256": digest(STUDY / "protocol.json"),
        "code_sha256": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "run_workbook_access.py",
                "workbook_read_tool.py",
                "workbook_model.py",
            )
        },
    }
    if replay:
        if load(root / "registration.json") != bindings:
            raise ValueError("Registration mismatch")
    else:
        seal(root / "registration.json", bindings)
    return bindings


def parse(raw):
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.partition("\n")[2].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@contextmanager
def reader_set(packets, arm):
    with ExitStack() as stack:
        temp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        readers = {}
        for item in packets:
            task = item["task_id"]
            if arm == "browse":
                folder = temp / task
                spreadsheets.materialize(task, folder)
                reader = WorkbookReader(folder / "input.xlsx")
            else:
                reader = WorkbookReader.from_projection(item["observation"])
            readers[task] = stack.enter_context(reader)
        yield readers


def prompt_for(packets, history, stage):
    # Keep the full content, including prior tool outputs, identical on capture and replay.
    return "\n".join(
        (
            COMMON,
            TOOL_HELP,
            SUBMIT if stage == ROUND_COUNT else INSPECT,
            "Public packets: " + pack(packets),
            "Prior inspections: " + pack(history),
            "Stage: " + NAMES[stage],
        )
    )


def inspect_round(tasks, raw, readers):
    requested = parse(raw)
    result = {}
    for task in tasks:
        plans = requested.get(task)
        if not isinstance(plans, list):
            result[task] = {"status": "missing_or_invalid_plan", "reads": []}
            continue
        status = "over_budget" if len(plans) > READ_LIMIT else "ok"
        result[task] = {
            "status": status,
            "reads": [
                {"request": request, "result": readers[task].apply(request)}
                for request in plans[:READ_LIMIT]
            ],
        }
    return result


def record_path(root, model, arm, batch):
    return root / "recordings" / model / arm / (batch + ".json")


def round_record(root, batch, model, arm, stage, prompt, allow_record):
    path = root / "turns" / model / arm / batch / (NAMES[stage] + ".json")
    binding = {
        "model": model,
        "arm": arm,
        "batch": batch,
        "stage": NAMES[stage],
        "prompt_sha256": text_hash(prompt),
        "registration_sha256": digest(root / "registration.json"),
    }
    if not path.exists():
        if not allow_record:
            raise ValueError("Missing archived model turn")
        response = ask(model, prompt)
        seal(path, {"binding": binding, "response": response})
    saved = load(path)
    if saved["binding"] != binding or saved["response"]["model"] != model:
        raise ValueError("Model response is not bound to this prompt")
    return saved["response"], digest(path)


def experiment(root, group, model, arm, allow_record):
    batch, tasks = group
    cfg = load(root / "registration.json")
    src = root / "inputs" / (batch + ".json")
    if digest(src) != cfg["input_hashes"][batch]:
        raise ValueError("Input hash differs from registration")
    packet = load(src)
    history, hashes, usage = [], [], Counter()
    with reader_set(packet, arm) as readers:
        for stage in range(ROUND_COUNT + 1):
            prompt = prompt_for(packet, history, stage)
            reply, token = round_record(
                root, batch, model, arm, stage, prompt, allow_record
            )
            usage.update(reply["usage"])
            hashes.append(token)
            if stage < ROUND_COUNT:
                history.append(inspect_round(tasks, reply["raw"], readers))
    submissions = parse(reply["raw"])
    cases = []
    for item in packet:
        task = item["task_id"]
        view = {
            (sh, addr)
            for sh, grid in item["observation"].items()
            for addr, _ in grid["cells"]
        }
        trace = [
            {"round": idx + 1, **read}
            for idx, turn in enumerate(history)
            for read in turn[task]["reads"]
        ]
        observed = {
            (r["result"]["sheet"], addr)
            for r in trace
            if r["result"].get("ok")
            for addr, _ in r["result"]["cells"]
        }
        cases.append(
            {
                "task_id": task,
                "model": model,
                "arm": arm,
                "batch": batch,
                "submission": submissions.get(task, ""),
                "submission_status": "present"
                if task in submissions
                else "missing_or_invalid_json",
                "trace": trace,
                "plan_status": [x[task]["status"] for x in history],
                "novel_cells": sorted([sh, addr] for sh, addr in observed - view),
                "calls": len(trace),
                "usage": dict(usage),
                "model_calls": len(hashes),
            }
        )
    stored = {
        "registration_sha256": digest(root / "registration.json"),
        "turns_sha256": hashes,
        "cases": cases,
    }
    path = record_path(root, model, arm, batch)
    if allow_record:
        seal(path, stored)
    elif load(path) != stored:
        raise ValueError(f"Tool replay or submission diverged: {path}")
    return cases


def jobs(cfg):
    return [
        (g, m, a)
        for g in cfg["groups"].items()
        for m in cfg["models"]
        for a in cfg["arms"]
    ]


def lock_value(root, cfg):
    value = {}
    for group, model, arm in jobs(cfg):
        p = record_path(root, model, arm, group[0])
        value[str(p.relative_to(root))] = digest(p)
    return {
        "registration_sha256": digest(root / "registration.json"),
        "records_sha256": value,
    }


def verified_records(root):
    root = Path(root)
    lock = load(root / "prediction_lock.json")
    cfg = registration(
        root, load(root / "registration.json")["development_smoke"], replay=True
    )
    if lock != lock_value(root, cfg):
        raise ValueError("Prediction lock mismatch")
    return [
        row
        for group, model, arm in jobs(cfg)
        for row in experiment(root, group, model, arm, False)
    ]


def record(root, workers, smoke):
    cfg = registration(root, smoke)
    # Separate equal-sized pools prevent a transport delay for one model from blocking the other.
    if workers < len(cfg["models"]):
        raise ValueError("Allow at least one worker per model")
    with ExitStack() as resources:
        pools = {
            m: resources.enter_context(
                ThreadPoolExecutor(max_workers=workers // len(cfg["models"]))
            )
            for m in cfg["models"]
        }
        futures = [
            pools[model].submit(experiment, root, group, model, arm, True)
            for group, model, arm in jobs(cfg)
        ]
        for future in futures:
            future.result()
    seal(root / "prediction_lock.json", lock_value(root, cfg))
    print(
        "Sealed",
        len(cfg["tasks"]) * len(cfg["models"]) * len(cfg["arms"]),
        "submissions",
        flush=True,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("record", "verify"))
    cli.add_argument("--root", type=Path, default=STUDY / "formal")
    cli.add_argument("--workers", type=int, default=8)
    cli.add_argument("--smoke", action="store_true")
    args = cli.parse_args()
    if args.action == "record":
        record(args.root, args.workers, args.smoke)
    else:
        print("Verified", len(verified_records(args.root)), "submissions")
