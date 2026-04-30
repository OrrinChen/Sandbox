"""Filesystem sandbox and state tracking utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import shutil
from typing import Dict, Mapping, Optional, Sequence


class SandboxError(RuntimeError):
    """Base error for sandbox failures."""


class SandboxPathError(SandboxError):
    """Raised when a path attempts to escape the sandbox workspace."""


@dataclass(frozen=True)
class StateDiff:
    added: list[str]
    modified: list[str]
    deleted: list[str]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "added": list(self.added),
            "modified": list(self.modified),
            "deleted": list(self.deleted),
        }


@dataclass(frozen=True)
class StateSnapshot:
    files: Dict[str, str]

    @classmethod
    def from_directory(cls, root: Path) -> "StateSnapshot":
        root = root.resolve()
        files: Dict[str, str] = {}
        if not root.exists():
            return cls(files={})
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return cls(files=files)

    def diff(self, other: "StateSnapshot") -> StateDiff:
        before = self.files
        after = other.files
        added = sorted(path for path in after if path not in before)
        deleted = sorted(path for path in before if path not in after)
        modified = sorted(path for path in before if path in after and before[path] != after[path])
        return StateDiff(added=added, modified=modified, deleted=deleted)


class FileSystemSandbox:
    """Workspace-only filesystem helper for deterministic local tool tests."""

    def __init__(
        self,
        workspace: Path,
        initial_files: Optional[Mapping[str, str]] = None,
        readable_paths: Optional[Sequence[str]] = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self._initial_files = dict(initial_files or {})
        self._readable_paths = tuple(readable_paths) if readable_paths is not None else None
        self.reset()

    def reset(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        for relative_path, contents in self._initial_files.items():
            self.write_text(relative_path, contents)

    def resolve_path(self, relative_path: str | Path) -> Path:
        requested = Path(relative_path)
        if requested.is_absolute():
            raise SandboxPathError(f"absolute path is not allowed: {relative_path}")
        resolved = (self.workspace / requested).resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise SandboxPathError(f"path is outside workspace: {relative_path}") from exc
        return resolved

    def write_text(self, relative_path: str | Path, contents: str) -> Path:
        path = self.resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def read_text(self, relative_path: str | Path) -> str:
        self._check_read_allowed(relative_path)
        return self.resolve_path(relative_path).read_text()

    def delete(self, relative_path: str | Path) -> None:
        path = self.resolve_path(relative_path)
        if path.exists():
            path.unlink()

    def snapshot(self) -> StateSnapshot:
        return StateSnapshot.from_directory(self.workspace)

    def _check_read_allowed(self, relative_path: str | Path) -> None:
        if self._readable_paths is None:
            return
        requested = Path(relative_path)
        requested_parts = requested.parts
        for allowed in self._readable_paths:
            allowed_parts = Path(allowed).parts
            if requested_parts[: len(allowed_parts)] == allowed_parts:
                return
        raise SandboxPathError(f"path is not in read allowlist: {relative_path}")
