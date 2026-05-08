"""LangSmith trace export helpers.

Default behavior is local-only and credential-free. Upload is opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Iterable, Optional

from sandboxed_agent_eval_harness.integrations.common import IntegrationUnavailableError, require_optional_dependency
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tracing import load_trace_events


@dataclass(frozen=True)
class LangSmithExportResult:
    status: str
    output_path: Path
    trace_count: int
    event_count: int
    uploaded: bool
    project_name: Optional[str] = None

    def to_dict(self) -> JsonDict:
        return {
            "status": self.status,
            "output_path": str(self.output_path),
            "trace_count": self.trace_count,
            "event_count": self.event_count,
            "uploaded": self.uploaded,
            "project_name": self.project_name,
        }


class LangSmithTraceExporter:
    """Export harness JSONL traces into a local LangSmith-compatible record stream."""

    def export(
        self,
        trace_paths: Iterable[Path | str],
        *,
        output_path: Path | str = "artifacts/integrations/langsmith/local_trace_export.jsonl",
        upload: bool = False,
        project_name: str = "sandboxed-agent-eval-harness",
        api_key_env: str = "LANGSMITH_API_KEY",
    ) -> LangSmithExportResult:
        paths = [Path(path) for path in trace_paths]
        records = self._records_from_traces(paths, upload_enabled=upload)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

        if not upload:
            return LangSmithExportResult(
                status="local_exported",
                output_path=output,
                trace_count=len(paths),
                event_count=len(records),
                uploaded=False,
            )

        api_key = os.environ.get(api_key_env)
        if not api_key:
            return LangSmithExportResult(
                status="skipped_missing_credentials",
                output_path=output,
                trace_count=len(paths),
                event_count=len(records),
                uploaded=False,
                project_name=project_name,
            )

        self._upload_records(records, project_name=project_name, api_key=api_key)
        return LangSmithExportResult(
            status="uploaded",
            output_path=output,
            trace_count=len(paths),
            event_count=len(records),
            uploaded=True,
            project_name=project_name,
        )

    def _records_from_traces(self, trace_paths: list[Path], *, upload_enabled: bool) -> list[JsonDict]:
        records: list[JsonDict] = []
        for trace_path in trace_paths:
            for event in load_trace_events(trace_path):
                records.append(
                    {
                        "exporter": "langsmith",
                        "upload_enabled": upload_enabled,
                        "trace_path": str(trace_path),
                        "run_id": event.metadata.get("run_id"),
                        "task_id": event.metadata.get("task_id"),
                        "event_type": event.event_type,
                        "sequence": event.sequence,
                        "payload": dict(event.payload),
                        "metadata": dict(event.metadata),
                    }
                )
        return records

    def _upload_records(self, records: list[JsonDict], *, project_name: str, api_key: str) -> None:
        if not records:
            return
        langsmith_module = require_optional_dependency("langsmith")
        client = langsmith_module.Client(api_key=api_key)
        grouped: dict[str, list[JsonDict]] = {}
        for record in records:
            grouped.setdefault(str(record.get("run_id") or "trace"), []).append(record)
        now = datetime.now(timezone.utc)
        for run_id, run_records in grouped.items():
            try:
                client.create_run(
                    name=run_id,
                    run_type="chain",
                    inputs={"trace_path": run_records[0].get("trace_path")},
                    outputs={"event_count": len(run_records)},
                    project_name=project_name,
                    start_time=now,
                    end_time=now,
                    extra={"harness_events": run_records},
                )
            except TypeError as exc:
                raise IntegrationUnavailableError(
                    "installed langsmith client does not support the expected create_run API"
                ) from exc
