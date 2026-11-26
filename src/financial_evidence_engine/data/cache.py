"""Local source payload cache with stable version hashes."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Union

from financial_evidence_engine.data.models import CachedPayload


class SourceCache:
    """Write source payloads and sidecar metadata under a cache root."""

    def __init__(self, root: Union[Path, str]):
        self.root = Path(root)

    def write_json(self, relative_path: Union[Path, str], payload: Any, retrieved_at: datetime) -> CachedPayload:
        payload_path = self.root / relative_path
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(_canonical_json(payload), encoding="utf-8")

        version_hash = stable_json_hash(payload)
        metadata_path = payload_path.with_name(f"{payload_path.name}.metadata.json")
        metadata = {
            "payload_path": str(payload_path),
            "retrieved_at": retrieved_at.isoformat(),
            "version_hash": version_hash,
        }
        metadata_path.write_text(_canonical_json(metadata), encoding="utf-8")

        return CachedPayload(
            payload_path=payload_path,
            metadata_path=metadata_path,
            retrieved_at=retrieved_at,
            version_hash=version_hash,
        )

    def read_json(self, relative_path: Union[Path, str]) -> Any:
        payload_path = self.root / relative_path
        with payload_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def stable_json_hash(payload: Any) -> str:
    """Return a stable SHA-256 hash for JSON-like payloads."""

    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
