"""Smoke check for Phase 19 local CLI production workflow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH = str(PROJECT_ROOT / "src")


def main() -> None:
    verify = _run("verify-claim", "--claim", "Apple FY2024 revenue was $391.035 billion.")
    corpus = _run("build-corpus", "--corpus", "raw")
    evaluation = _run("run-eval", "--corpus", "benchmark")
    cases = _run("build-case-studies")
    report = _run("build-report")
    serve = _run("serve-demo", "--dry-run")
    print(
        "commands=6 "
        f"verify_verdict={verify['verdict']} "
        f"raw_chunks={corpus['chunks']} "
        f"eval_tasks={evaluation['tasks']} "
        f"case_studies={cases['case_studies']} "
        f"report_pages={report['pages']} "
        f"serve_demo={serve['dry_run']} "
        f"network_enabled={verify['network_enabled']}"
    )


def _run(*args: str):
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    result = subprocess.run(
        [sys.executable, "-m", "financial_evidence_engine.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    return json.loads(result.stdout)


if __name__ == "__main__":
    main()
