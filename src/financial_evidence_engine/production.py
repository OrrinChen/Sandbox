"""Local production workflow helpers for CLI and artifact hygiene."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Tuple


ERROR_TAXONOMY: Mapping[str, str] = {
    "bad_input": "The command input is invalid or incomplete.",
    "missing_pdf": "The requested investor-deck PDF does not exist.",
    "missing_corpus": "The requested corpus artifact is unavailable.",
    "missing_model": "An optional model backend is unavailable.",
    "missing_artifact": "A requested local artifact does not exist.",
}


@dataclass(frozen=True)
class ProductionConfigProfile:
    """Named runtime profile for local commands."""

    name: str
    artifact_root: Path
    cache_root: Path
    network_enabled: bool
    log_format: str = "json"

    def to_dict(self) -> Mapping[str, object]:
        return {
            "name": self.name,
            "artifact_root": str(self.artifact_root),
            "cache_root": str(self.cache_root),
            "network_enabled": self.network_enabled,
            "log_format": self.log_format,
        }


@dataclass(frozen=True)
class ProductionError(Exception):
    """Clear production workflow error with a stable code."""

    error_code: str
    message: str

    def to_dict(self) -> Mapping[str, str]:
        return {"error_code": self.error_code, "message": self.message}


@dataclass(frozen=True)
class ArtifactVersion:
    """Version metadata for a generated local artifact."""

    path: Path
    content_hash: str
    size_bytes: int

    def to_dict(self) -> Mapping[str, object]:
        return {
            "path": str(self.path),
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class CacheInvalidationPlan:
    """Non-destructive cache invalidation plan."""

    path: Path
    reason: str
    would_delete: bool

    def to_dict(self) -> Mapping[str, object]:
        return {
            "path": str(self.path),
            "reason": self.reason,
            "would_delete": self.would_delete,
        }


@dataclass(frozen=True)
class ProvenanceCheck:
    """Local artifact provenance check."""

    path: Path
    status: str
    detail: str

    def to_dict(self) -> Mapping[str, str]:
        return {
            "path": str(self.path),
            "status": self.status,
            "detail": self.detail,
        }


CONFIG_PROFILES: Mapping[str, ProductionConfigProfile] = {
    "local": ProductionConfigProfile(
        name="local",
        artifact_root=Path("reports"),
        cache_root=Path("data/cache"),
        network_enabled=False,
    ),
    "ci": ProductionConfigProfile(
        name="ci",
        artifact_root=Path("reports"),
        cache_root=Path(".cache/financial_evidence"),
        network_enabled=False,
    ),
}


def version_artifact(path: Path) -> ArtifactVersion:
    """Return stable version metadata for an existing artifact."""

    if not path.exists():
        raise ProductionError("missing_artifact", f"Artifact does not exist: {path}")
    data = path.read_bytes()
    return ArtifactVersion(
        path=path,
        content_hash=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )


def plan_cache_invalidation(
    paths: Iterable[Path],
    reason: str,
    execute: bool = False,
) -> Tuple[CacheInvalidationPlan, ...]:
    """Plan cache invalidation without deleting by default."""

    return tuple(
        CacheInvalidationPlan(path=path, reason=reason, would_delete=bool(execute and path.exists()))
        for path in paths
    )


def check_data_provenance(paths: Iterable[Path]) -> Tuple[ProvenanceCheck, ...]:
    """Check whether required local artifact paths exist and are readable."""

    checks = []
    for path in paths:
        if path.exists() and path.is_file():
            checks.append(ProvenanceCheck(path=path, status="pass", detail="artifact exists"))
        else:
            checks.append(ProvenanceCheck(path=path, status="fail", detail="artifact missing"))
    return tuple(checks)


def structured_log(event: str, payload: Mapping[str, object]) -> str:
    """Render one structured log line."""

    return json.dumps({"event": event, **payload}, sort_keys=True)
