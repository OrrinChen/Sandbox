"""Sandbox backend abstractions for workspace and optional Docker execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Optional, Sequence

from sandboxed_agent_eval_harness.sandbox.filesystem import FileSystemSandbox
from sandboxed_agent_eval_harness.sandbox.subprocess import (
    SandboxCommandResult,
    SandboxTimeoutError,
    run_python_subprocess,
)
from sandboxed_agent_eval_harness.schemas import TaskSpec


SandboxCommandRunner = Callable[[list[str], float], SandboxCommandResult]


class SandboxBackendError(RuntimeError):
    """Raised when a sandbox backend cannot execute a requested operation."""


class DockerUnavailableError(SandboxBackendError):
    """Raised when Docker execution is requested but Docker is unavailable."""


@dataclass(frozen=True)
class SandboxBackendConfig:
    timeout_seconds: float = 5.0
    memory_limit: str = "512m"
    cpus: str = "1.0"
    pids_limit: int = 128
    image: str = "python:3.11-slim"
    network_disabled: bool = True
    tmpfs_size: str = "64m"

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.memory_limit:
            raise ValueError("memory_limit must be non-empty")
        if not self.cpus:
            raise ValueError("cpus must be non-empty")
        if self.pids_limit <= 0:
            raise ValueError("pids_limit must be positive")
        if not self.image:
            raise ValueError("image must be non-empty")
        if not self.network_disabled:
            raise ValueError("network_disabled must remain true for evaluation isolation")

    def to_dict(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "memory_limit": self.memory_limit,
            "cpus": self.cpus,
            "pids_limit": self.pids_limit,
            "image": self.image,
            "network_disabled": self.network_disabled,
            "tmpfs_size": self.tmpfs_size,
        }


class LocalWorkspaceBackend:
    """Current workspace-isolated backend using FileSystemSandbox path checks."""

    name = "workspace"

    def __init__(self, config: Optional[SandboxBackendConfig] = None) -> None:
        self.config = config or SandboxBackendConfig()

    def create_sandbox(
        self,
        task: TaskSpec,
        workspace: Path | str,
        *,
        fixture_root: Path | str,
    ) -> FileSystemSandbox:
        root = Path(fixture_root)
        initial_files = {
            visible_path: (root / visible_path).read_text()
            for visible_path in task.visible_files
        }
        return FileSystemSandbox(Path(workspace), initial_files=initial_files)

    def run_python(
        self,
        code: str,
        *,
        workspace: Path,
        timeout_seconds: float,
    ) -> SandboxCommandResult:
        timeout = min(float(timeout_seconds), self.config.timeout_seconds)
        return run_python_subprocess(code, workspace=workspace, timeout_seconds=timeout)

    def export_artifacts(self, workspace: Path | str, output_dir: Path | str) -> list[str]:
        workspace_path = Path(workspace)
        output_path = Path(output_dir)
        if output_path.exists():
            shutil.rmtree(output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        exported: list[str] = []
        for path in sorted(item for item in workspace_path.rglob("*") if item.is_file()):
            relative = path.relative_to(workspace_path)
            target = output_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            exported.append(relative.as_posix())
        return exported

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "config": self.config.to_dict(),
        }


class DockerSandboxBackend(LocalWorkspaceBackend):
    """Optional Docker command envelope for evaluation isolation.

    Docker is not required for default validation. When a command runner is
    injected, tests can deterministically verify the container command surface
    without starting Docker.
    """

    name = "docker"

    def __init__(
        self,
        config: Optional[SandboxBackendConfig] = None,
        *,
        fixture_root: Optional[Path | str] = None,
        docker_executable: str = "docker",
        command_runner: Optional[SandboxCommandRunner] = None,
    ) -> None:
        super().__init__(config=config)
        self.fixture_root = Path(fixture_root) if fixture_root is not None else Path.cwd()
        self.docker_executable = docker_executable
        self.command_runner = command_runner

    def command_for_workspace(self, workspace: Path | str, command: Sequence[str]) -> list[str]:
        workspace_path = Path(workspace).resolve()
        fixtures_path = (self.fixture_root / "fixtures").resolve()
        return [
            self.docker_executable,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            self.config.memory_limit,
            "--cpus",
            self.config.cpus,
            "--pids-limit",
            str(self.config.pids_limit),
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={self.config.tmpfs_size}",
            "--mount",
            f"type=bind,source={workspace_path},target=/workspace",
            "--mount",
            f"type=bind,source={fixtures_path},target=/fixtures,readonly",
            "--workdir",
            "/workspace",
            self.config.image,
            *command,
        ]

    def run_python(
        self,
        code: str,
        *,
        workspace: Path,
        timeout_seconds: float,
    ) -> SandboxCommandResult:
        timeout = min(float(timeout_seconds), self.config.timeout_seconds)
        command = self.command_for_workspace(workspace, ["python", "-c", code])
        runner = self.command_runner or _run_docker_command
        return runner(command, timeout)


def sandbox_backend_by_name(
    name: str,
    *,
    config: Optional[SandboxBackendConfig] = None,
    fixture_root: Optional[Path | str] = None,
) -> LocalWorkspaceBackend:
    if name == "workspace":
        return LocalWorkspaceBackend(config=config)
    if name == "docker":
        return DockerSandboxBackend(config=config, fixture_root=fixture_root)
    raise SandboxBackendError(f"unknown sandbox backend: {name}")


def _run_docker_command(command: list[str], timeout_seconds: float) -> SandboxCommandResult:
    if shutil.which(command[0]) is None:
        raise DockerUnavailableError(f"Docker executable not found: {command[0]}")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxTimeoutError(f"docker command timed out after {timeout_seconds} seconds") from exc
    return SandboxCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
