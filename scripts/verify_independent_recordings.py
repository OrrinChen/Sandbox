"""Regrade sealed model submissions with an installed wheel and network-blocked tools."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile


def run_partition(part):
    from sandboxed_agent_eval_harness.benchmarks.independent import (
        repairs,
        spreadsheets,
        suite,
    )

    if Path(sys.prefix).resolve() not in Path(suite.__file__).resolve().parents:
        raise RuntimeError("Expected the package installed in the verification venv")
    if part == "calc-sql" and platform.system() == "Linux":
        routes = Path("/proc/net/route").read_text().splitlines()[1:]
        if any(line.split()[1] == "00000000" for line in routes):
            raise RuntimeError(
                "The isolated network namespace has a default IPv4 route"
            )
    elif part == "calc-sql":
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
        except OSError:
            pass
        else:
            raise RuntimeError("Missing OS network denial")
    checked = {}
    for arm, batch in json.load(sys.stdin).items():
        books, ordinary = {}, []
        for task, candidate in batch.items():
            adapter, _ = suite.inventory()[task]
            if (adapter is repairs) != (part == "repair"):
                continue
            if adapter is spreadsheets:
                books[task] = candidate
            else:
                ordinary.append((task, adapter, candidate))

        def score(entry):
            task, adapter, candidate = entry
            return task, bool(candidate) and adapter.grade(task, candidate)

        with ThreadPoolExecutor(max_workers=4) as pool:
            checked[arm] = dict(pool.map(score, ordinary))
        if books:
            checked[arm].update(spreadsheets.batch_grade(books))
    print(json.dumps({"release": suite.verify_release(), "rows": checked}))


def verify(root, python):
    from run_independent_comparison import expand, load, predictions, seal
    from sandboxed_agent_eval_harness.benchmarks.independent import spreadsheets, suite

    if load(root / "prediction_lock.json") != predictions(root):
        raise ValueError("Recording lock differs")
    raw = {}
    for arm in ("direct", "self_check"):
        raw[arm] = {}
        for path in sorted((root / "recordings" / arm).glob("*.json")):
            for task, candidate in load(path)["submissions"].items():
                if suite.inventory()[task][0] is spreadsheets:
                    try:
                        candidate = expand(candidate)
                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        IndexError,
                        AttributeError,
                    ):
                        candidate = {}
                raw[arm][task] = candidate
    if platform.system() == "Darwin":
        denied = [
            "/usr/bin/sandbox-exec",
            "-p",
            "(version 1)(allow default)(deny network*)",
        ]
    elif shutil.which("unshare"):
        denied = ["unshare", "--user", "--map-root-user", "--net", "--"]
    else:
        raise RuntimeError("Need macOS sandbox-exec or Linux network namespaces")
    command = [
        str(python.absolute()),
        "-I",
        str(Path(__file__).resolve()),
        "--partition",
    ]
    scored_file = root / "score.json"
    expected = {(r["task"], r["arm"]): r["passed"] for r in load(scored_file)["rows"]}
    verified = {}
    with tempfile.TemporaryDirectory() as temp:
        for part in ("calc-sql", "repair"):
            # Each Python submission starts its own deny-default OS sandbox.
            prefix = denied if part == "calc-sql" else []
            result = subprocess.run(
                prefix + command + [part],
                input=json.dumps(raw),
                stdout=subprocess.PIPE,
                text=True,
                cwd=temp,
                check=True,
            )
            response = json.loads(result.stdout)
            if response["release"] != suite.verify_release():
                raise ValueError("Installed wheel has a different release")
            for arm, values in response["rows"].items():
                for task, passed in values.items():
                    if (task, arm) in verified:
                        raise ValueError("Duplicate observation")
                    verified[task, arm] = passed
    if verified != expected:
        differences = [key for key in expected if verified.get(key) != expected[key]]
        raise ValueError(f"Regrade diverged on {differences}")
    seal(
        root / "installed_regrade.json",
        {
            "release_sha256": suite.verify_release(),
            "score_sha256": sha256(scored_file.read_bytes()).hexdigest(),
            "reproduced_submissions": len(verified),
            "network_isolation": "Calc and SQLite ran under OS network denial. Each Python submission ran in its own network-blocked OS sandbox. The driver compared sealed local files.",
        },
    )
    print(f"Reproduced {len(verified)} verdicts from the installed wheel")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partition", choices=("repair", "calc-sql"), help=argparse.SUPPRESS
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--installed-python", type=Path)
    args = parser.parse_args()
    if args.partition:
        run_partition(args.partition)
    elif args.out and args.installed_python:
        verify(args.out, args.installed_python)
    else:
        parser.error("Provide --out and --installed-python")
