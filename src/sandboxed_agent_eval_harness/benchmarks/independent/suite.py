"""Public export, deterministic grading, paired calibration and receipt replay."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256
import json
import tempfile
from pathlib import Path

from . import relational, repairs, spreadsheets

ROOT = Path(__file__).parent
LOCK = ROOT / "data" / "release.json"
ADAPTERS = (relational, repairs, spreadsheets)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def fingerprint(value):
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


@lru_cache(maxsize=1)
def inventory():
    result = {}
    groups = {}
    for adapter in ADAPTERS:
        for row in adapter.records():
            task = row["task_id"]
            group, split = row["source_group"], row["split"]
            if (
                task in result
                or split not in {"dev", "test"}
                or groups.setdefault(group, split) != split
            ):
                raise ValueError(
                    f"Duplicate task or overlapping source group at {task}"
                )
            result[task] = (adapter, row)
    return result


def assets():
    return {
        str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
        for folder in (ROOT / "data", ROOT / "sheet_data")
        for p in sorted(folder.iterdir())
        if p.is_file() and p != LOCK
    }


def release_record():
    tasks = inventory()
    split = Counter(row["split"] for _, row in tasks.values())
    if split != {"dev": 100, "test": 500}:
        raise ValueError(f"Incomplete benchmark counts: {dict(split)}")
    return {
        "version": "independent-tools-1",
        "counts": dict(sorted(split.items())),
        "domains": {
            s: dict(
                sorted(
                    Counter(
                        row["domain"] for _, row in tasks.values() if row["split"] == s
                    ).items()
                )
            )
            for s in ("dev", "test")
        },
        "groups": len({row["source_group"] for _, row in tasks.values()}),
        "assets": assets(),
    }


def verify_release():
    expected = json.loads(LOCK.read_bytes())
    if release_record() != expected:
        raise ValueError("Installed task assets differ from the frozen release")
    return sha256(LOCK.read_bytes()).hexdigest()


def export(task_id, directory):
    adapter, row = inventory()[task_id]
    directory = Path(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as intermediate:
        packet = Path(intermediate) / "packet"
        packet.mkdir()
        adapter.materialize(task_id, packet)
        if not (packet / "task.json").exists():
            write_json(packet / "task.json", row)
        if directory.is_dir() and any(directory.iterdir()):
            existing = {p.name for p in directory.iterdir()}
            if existing == {p.name for p in packet.iterdir()} and all(
                (directory / p.name).is_file()
                and (directory / p.name).read_bytes() == p.read_bytes()
                for p in packet.iterdir()
            ):
                return
            raise ValueError(
                "Export directory contains a different packet or user files"
            )
        packet.replace(directory)


def receipt(task_id, candidate):
    adapter, row = inventory()[task_id]
    return {
        "version": 1,
        "release_sha256": sha256(LOCK.read_bytes()).hexdigest(),
        "task_id": task_id,
        "split": row["split"],
        "tool": row["tool"],
        "candidate": candidate,
        "candidate_sha256": fingerprint(candidate),
        "passed": adapter.grade(task_id, candidate),
    }


def calibrate(split, workers=4):
    digest = verify_release()
    tasks = {
        t: entry
        for t, entry in inventory().items()
        if split == "all" or entry[1]["split"] == split
    }
    books = [t for t, (a, _) in tasks.items() if a is spreadsheets]
    book_results = spreadsheets.calibration(books) if books else {}

    def check(task):
        adapter, row = tasks[task]
        if task in book_results:
            good, bad = book_results[task]
        elif adapter is repairs:
            good, bad = repairs.calibration(task)
        else:
            good = adapter.grade(task, adapter.run_reference(task))
            bad = adapter.grade(task, adapter.run_negative(task))
        return {
            "task_id": task,
            "split": row["split"],
            "domain": row["domain"],
            "reference_accepted": bool(good),
            "incorrect_rejected": not bad,
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(check, sorted(tasks)))
    return {
        "kind": "reference and controlled-error calibration",
        "release_sha256": digest,
        "cases": len(results),
        "references_accepted": sum(x["reference_accepted"] for x in results),
        "incorrect_rejected": sum(x["incorrect_rejected"] for x in results),
        "results": results,
    }


def add_commands(parser):
    commands = parser.add_subparsers(dest="independent_action", required=True)
    commands.add_parser(
        "verify", help="Check all installed assets against the benchmark lock."
    )
    ls = commands.add_parser("list", help="List public task metadata.")
    ls.add_argument("--split", choices=("dev", "test"), default="dev")
    packet = commands.add_parser(
        "export", help="Materialize one public task for a solver."
    )
    packet.add_argument("task_id")
    packet.add_argument("directory", type=Path)
    stats = commands.add_parser(
        "calibrate", help="Execute reference and plausible wrong submissions."
    )
    stats.add_argument("--split", choices=("dev", "test", "all"), default="all")
    stats.add_argument("--out", type=Path, required=True)
    score = commands.add_parser(
        "grade", help="Grade a candidate saved before opening the scorer."
    )
    score.add_argument("task_id")
    score.add_argument("submission", type=Path)
    score.add_argument("--out", type=Path, required=True)
    replay = commands.add_parser(
        "replay", help="Re-evaluate a recorded submission and compare the verdict."
    )
    replay.add_argument("receipt", type=Path)
    run = commands.add_parser(
        "query", help="Run a relational task on its public tables and write its CSV."
    )
    run.add_argument("task_id")
    run.add_argument("submission", type=Path)
    run.add_argument("--out", type=Path, required=True)


def run(args):
    cmd = args.independent_action
    if cmd == "verify":
        print(verify_release())
    elif cmd == "list":
        for t, (_, r) in sorted(inventory().items()):
            if r["split"] == args.split:
                print(
                    json.dumps({"task_id": t, "domain": r["domain"], "tool": r["tool"]})
                )
    elif cmd == "export":
        export(args.task_id, args.directory)
    elif cmd == "calibrate":
        result = calibrate(args.split)
        write_json(args.out, result)
        print(
            f"{result['cases']} cases, {result['references_accepted']} accepted references, "
            f"{result['incorrect_rejected']} rejected controls"
        )
        return int(
            not result["cases"]
            == result["references_accepted"]
            == result["incorrect_rejected"]
        )
    elif cmd == "grade":
        verify_release()
        adapter, _ = inventory()[args.task_id]
        result = receipt(args.task_id, adapter.candidate_from_file(args.submission))
        write_json(args.out, result)
        print("pass" if result["passed"] else "fail")
        return int(not result["passed"])
    elif cmd == "replay":
        verify_release()
        former = json.loads(args.receipt.read_bytes())
        if receipt(former["task_id"], former["candidate"]) != former:
            raise ValueError("Replay diverged from the original receipt")
        print("reproduced pass" if former["passed"] else "reproduced failure")
    elif cmd == "query":
        adapter, _ = inventory()[args.task_id]
        if adapter is not relational:
            raise ValueError("Only relational tasks accept SQLite queries")
        cols, rows = relational.execute(
            args.submission.read_text(), relational.index()[args.task_id]["tables"]
        )
        args.out.write_bytes(
            relational.artifact(relational.index()[args.task_id], cols, rows)
        )
    return 0
