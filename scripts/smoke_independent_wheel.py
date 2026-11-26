"""Build a wheel, install into an empty venv, calibrate every independent task and replay failures."""

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OFFLINE_PIP = ["--no-index", "--no-deps", "--no-cache-dir"]
PROBE = """
import socket,sys
from pathlib import Path
from sandboxed_agent_eval_harness.benchmarks.independent import suite
assert Path(suite.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
try:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.connect(('192.0.2.1', 9))
except (PermissionError, OSError) as exc:
    import errno
    assert exc.errno in {errno.EPERM, errno.EACCES, errno.ENETUNREACH, errno.EADDRNOTAVAIL}, exc
else:
    raise AssertionError('Expected a kernel network barrier')
print(suite.verify_release())
"""
PREPARE_CONTROLS = """
import json
from pathlib import Path
from sandboxed_agent_eval_harness.benchmarks.independent import suite
units = {}
for adapter in suite.ADAPTERS:
    key = adapter.__name__.rsplit('.',1)[1]
    task_id = next(row['task_id'] for row in adapter.records() if row['split'] == 'test')
    adapter.save_candidate(task_id, adapter.run_negative(task_id), Path(key))
    units[key] = task_id
print(json.dumps(units))
"""


def network_barrier():
    if platform.system() == "Darwin":
        return [
            "/usr/bin/sandbox-exec",
            "-p",
            "(version 1)(allow default)(deny network*)",
        ]
    if platform.system() == "Linux" and shutil.which("unshare"):
        return ["unshare", "--user", "--map-root-user", "--net", "--"]
    raise RuntimeError(
        "This smoke test needs macOS sandbox-exec or Linux network namespace support."
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir", type=Path, required=True)
    p.add_argument("--wheel-dir", type=Path)
    args = p.parse_args()
    dest = args.results_dir.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    if shutil.which("soffice") is None and shutil.which("libreoffice") is None:
        raise SystemExit(
            "Install LibreOffice Calc before running workbook calibration."
        )
    with tempfile.TemporaryDirectory(prefix="independent-wheel-") as temp:
        stage = Path(temp)
        source, work, dist = stage / "source", stage / "run", stage / "wheelhouse"
        work.mkdir()
        source.mkdir()
        for name in ("pyproject.toml", "README.md"):
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(
            ROOT / "src",
            source / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
        )
        barrier = network_barrier()
        env = {
            k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")
        }
        env.update(
            PIP_CONFIG_FILE=os.devnull,
            PIP_DISABLE_PIP_VERSION_CHECK="1",
            PYTHONNOUSERSITE="1",
            SOURCE_DATE_EPOCH="946684800",
            TZ="UTC",
        )

        def run(argv, *, wrapper=True, code=0):
            proc = subprocess.run(
                (barrier if wrapper else []) + list(argv),
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
            )
            if proc.returncode != code:
                raise RuntimeError(
                    f"{argv[0]} exited {proc.returncode} (expected {code}): {proc.stdout} {proc.stderr}"
                )
            return proc.stdout.strip()

        run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                *OFFLINE_PIP,
                "--no-build-isolation",
                "--wheel-dir",
                dist,
                source,
            ]
        )
        (wheel,) = dist.glob("*.whl")
        venv = stage / "venv"
        run([sys.executable, "-m", "venv", venv])
        py = venv / "bin/python"
        cli = [venv / "bin/sandboxed-agent-eval", "independent-benchmark"]
        run([py, "-m", "pip", "install", *OFFLINE_PIP, wheel])
        release = run([py, "-I", "-c", PROBE])
        if run([*cli, "verify"]) != release:
            raise RuntimeError(
                "Installed CLI and Python disagree about the frozen release"
            )
        print(f"Calibrating frozen release {release}", flush=True)
        calibration = work / "calibration.json"
        print(
            run([*cli, "calibrate", "--split", "all", "--out", calibration]), flush=True
        )
        values = json.loads(calibration.read_bytes())
        splits = collections.Counter(row["split"] for row in values["results"])
        if splits != {"dev": 100, "test": 500} or values["release_sha256"] != release:
            raise RuntimeError("Calibration did not cover the complete frozen split")
        # The candidate itself always runs inside its restrictive OS profile. On macOS
        # Seatbelt does not accept a second sandbox once the grader driver is sandboxed.
        units = json.loads(run([py, "-I", "-c", PREPARE_CONTROLS]))
        receipts = {}
        for name, task in units.items():
            out = work / (name + ".json")
            wrap = name != "repairs" or platform.system() != "Darwin"
            if (
                run([*cli, "grade", task, name, "--out", out], wrapper=wrap, code=1)
                != "fail"
            ):
                raise RuntimeError(f"Expected controlled failure for {task}")
            if run([*cli, "replay", out], wrapper=wrap) != "reproduced failure":
                raise RuntimeError(f"Replay diverged for {task}")
            receipts[name] = {"task": task, "sha256": digest(out)}
        shutil.copyfile(calibration, dest / calibration.name)
        replay_dir = dest / "controlled_failure_receipts"
        replay_dir.mkdir(exist_ok=True)
        for name in units:
            shutil.copyfile(work / (name + ".json"), replay_dir / (name + ".json"))
        if args.wheel_dir:
            args.wheel_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wheel, args.wheel_dir / wheel.name)
        summary = {
            "wheel": wheel.name,
            "wheel_sha256": digest(wheel),
            "release_sha256": release,
            "calibration_sha256": digest(calibration),
            "python": platform.python_version(),
            "platform": platform.system(),
            "calc": run(
                [shutil.which("soffice") or shutil.which("libreoffice"), "--version"]
            ),
            "network_barrier": barrier,
            "installed_outside_checkout": True,
            "repair_failure_replay": "submission in restrictive network-denied OS sandbox",
            "split": dict(splits),
            "accepted_references": values["references_accepted"],
            "rejected_controls": values["incorrect_rejected"],
            "replayed_failures": receipts,
        }
        (dest / "wheel_verification.json").write_text(
            json.dumps(summary, indent=2) + "\n"
        )
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
