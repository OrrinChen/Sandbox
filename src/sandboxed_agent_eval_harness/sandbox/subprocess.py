"""Timeout-constrained subprocess helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys


class SandboxTimeoutError(TimeoutError):
    """Raised when sandboxed subprocess execution exceeds its timeout."""


@dataclass(frozen=True)
class SandboxCommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_python_subprocess(
    code: str,
    *,
    workspace: Path,
    timeout_seconds: float,
) -> SandboxCommandResult:
    Path(workspace).mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxTimeoutError(f"python subprocess timed out after {timeout_seconds} seconds") from exc
    return SandboxCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
