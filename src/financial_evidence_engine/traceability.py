"""Reproducible evidence trace manifests and local trace storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Tuple

from financial_evidence_engine.case_studies import (
    EvidenceReference,
    PortfolioCaseStudy,
    build_portfolio_case_studies,
)


PHASE16_TRACE_TIMESTAMP = "2026-05-02T00:00:00Z"
DEFAULT_CORPUS_VERSION = "benchmark:60-tasks:320-documents"


@dataclass(frozen=True)
class RunManifest:
    """Top-level manifest for one reproducible verification run."""

    run_id: str
    config_hash: str
    corpus_version: str
    method: str
    task_id: str
    started_at: str
    runtime_ms: int
    artifact_paths: Tuple[str, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "config_hash": self.config_hash,
            "corpus_version": self.corpus_version,
            "method": self.method,
            "task_id": self.task_id,
            "started_at": self.started_at,
            "runtime_ms": self.runtime_ms,
            "artifact_paths": list(self.artifact_paths),
        }


@dataclass(frozen=True)
class RetrievalTrace:
    """Retrieved evidence chunks for one method and task."""

    run_id: str
    method: str
    task_id: str
    retrieved_chunks: Tuple[str, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "method": self.method,
            "task_id": self.task_id,
            "retrieved_chunks": list(self.retrieved_chunks),
        }


@dataclass(frozen=True)
class VerificationTrace:
    """Validator outputs and final verdict for one run."""

    run_id: str
    task_id: str
    validator_results: Mapping[str, str]
    final_verdict: str
    expected_verdict: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "validator_results": dict(self.validator_results),
            "final_verdict": self.final_verdict,
            "expected_verdict": self.expected_verdict,
        }


@dataclass(frozen=True)
class EvidenceTrace:
    """Evidence identifiers and provenance documents attached to a run."""

    run_id: str
    task_id: str
    evidence_ids: Tuple[str, ...]
    source_documents: Tuple[str, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "evidence_ids": list(self.evidence_ids),
            "source_documents": list(self.source_documents),
        }


@dataclass(frozen=True)
class MemoTrace:
    """Memo-level trace metadata derived from a verification run."""

    run_id: str
    memo_id: str
    conclusion_count: int
    artifact_path: str
    memo_snippet: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "memo_id": self.memo_id,
            "conclusion_count": self.conclusion_count,
            "artifact_path": self.artifact_path,
            "memo_snippet": self.memo_snippet,
        }


@dataclass(frozen=True)
class ArtifactManifest:
    """Artifact paths and trace-store identity for one run."""

    run_id: str
    artifact_paths: Tuple[str, ...]
    trace_database_path: str
    config_hash: str
    corpus_version: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_id": self.run_id,
            "artifact_paths": list(self.artifact_paths),
            "trace_database_path": self.trace_database_path,
            "config_hash": self.config_hash,
            "corpus_version": self.corpus_version,
        }


@dataclass(frozen=True)
class EvidenceTraceBundle:
    """All Phase 16 trace records needed to reproduce case-study evidence."""

    run_manifests: Tuple[RunManifest, ...]
    retrieval_traces: Tuple[RetrievalTrace, ...]
    verification_traces: Tuple[VerificationTrace, ...]
    evidence_traces: Tuple[EvidenceTrace, ...]
    memo_traces: Tuple[MemoTrace, ...]
    artifact_manifests: Tuple[ArtifactManifest, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "run_manifests": [record.to_dict() for record in self.run_manifests],
            "retrieval_traces": [record.to_dict() for record in self.retrieval_traces],
            "verification_traces": [record.to_dict() for record in self.verification_traces],
            "evidence_traces": [record.to_dict() for record in self.evidence_traces],
            "memo_traces": [record.to_dict() for record in self.memo_traces],
            "artifact_manifests": [record.to_dict() for record in self.artifact_manifests],
        }


@dataclass(frozen=True)
class TraceArtifactWriteResult:
    """Files written for Phase 16 trace reproducibility artifacts."""

    trace_db_path: Path
    artifact_manifest_path: Path
    integrity_summary: Mapping[str, object]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "trace_db_path": str(self.trace_db_path),
            "artifact_manifest_path": str(self.artifact_manifest_path),
            "integrity_summary": dict(self.integrity_summary),
        }


class TraceStore:
    """SQLite-backed local trace store for reproducible benchmark runs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def write_bundle(self, bundle: EvidenceTraceBundle) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            self._ensure_schema(connection)
            self._write_run_manifests(connection, bundle.run_manifests)
            self._write_retrieval_traces(connection, bundle.retrieval_traces)
            self._write_verification_traces(connection, bundle.verification_traces)
            self._write_evidence_traces(connection, bundle.evidence_traces)
            self._write_memo_traces(connection, bundle.memo_traces)
            self._write_artifact_manifests(connection, bundle.artifact_manifests)

    def integrity_summary(self) -> Mapping[str, object]:
        with sqlite3.connect(self.database_path) as connection:
            self._ensure_schema(connection)
            counts = {
                table: _table_count(connection, table)
                for table in (
                    "run_manifests",
                    "retrieval_traces",
                    "verification_traces",
                    "evidence_traces",
                    "memo_traces",
                    "artifact_manifests",
                )
            }
            run_count = counts["run_manifests"]
            retrieved_chunks = _json_array_total(connection, "retrieval_traces", "retrieved_chunks_json")
            validator_results = _json_object_total(
                connection,
                "verification_traces",
                "validator_results_json",
            )
            artifact_path_count = _json_array_total(
                connection,
                "artifact_manifests",
                "artifact_paths_json",
            )
        trace_integrity = run_count > 0 and all(count == run_count for count in counts.values())
        trace_integrity = trace_integrity and retrieved_chunks >= run_count and artifact_path_count >= run_count
        return {
            **counts,
            "retrieved_chunks": retrieved_chunks,
            "validator_results": validator_results,
            "artifact_paths": artifact_path_count,
            "trace_integrity": trace_integrity,
        }

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS run_manifests (
                run_id TEXT PRIMARY KEY,
                config_hash TEXT NOT NULL,
                corpus_version TEXT NOT NULL,
                method TEXT NOT NULL,
                task_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                runtime_ms INTEGER NOT NULL,
                artifact_paths_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS retrieval_traces (
                run_id TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                task_id TEXT NOT NULL,
                retrieved_chunks_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verification_traces (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                validator_results_json TEXT NOT NULL,
                final_verdict TEXT NOT NULL,
                expected_verdict TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence_traces (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                source_documents_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memo_traces (
                run_id TEXT PRIMARY KEY,
                memo_id TEXT NOT NULL,
                conclusion_count INTEGER NOT NULL,
                artifact_path TEXT NOT NULL,
                memo_snippet TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifact_manifests (
                run_id TEXT PRIMARY KEY,
                artifact_paths_json TEXT NOT NULL,
                trace_database_path TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                corpus_version TEXT NOT NULL
            );
            """
        )

    def _write_run_manifests(
        self,
        connection: sqlite3.Connection,
        records: Iterable[RunManifest],
    ) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO run_manifests
            (run_id, config_hash, corpus_version, method, task_id, started_at, runtime_ms, artifact_paths_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    record.run_id,
                    record.config_hash,
                    record.corpus_version,
                    record.method,
                    record.task_id,
                    record.started_at,
                    record.runtime_ms,
                    _json(record.artifact_paths),
                )
                for record in records
            ),
        )

    def _write_retrieval_traces(
        self,
        connection: sqlite3.Connection,
        records: Iterable[RetrievalTrace],
    ) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO retrieval_traces
            (run_id, method, task_id, retrieved_chunks_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                (record.run_id, record.method, record.task_id, _json(record.retrieved_chunks))
                for record in records
            ),
        )

    def _write_verification_traces(
        self,
        connection: sqlite3.Connection,
        records: Iterable[VerificationTrace],
    ) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO verification_traces
            (run_id, task_id, validator_results_json, final_verdict, expected_verdict)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    record.run_id,
                    record.task_id,
                    _json(record.validator_results),
                    record.final_verdict,
                    record.expected_verdict,
                )
                for record in records
            ),
        )

    def _write_evidence_traces(
        self,
        connection: sqlite3.Connection,
        records: Iterable[EvidenceTrace],
    ) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO evidence_traces
            (run_id, task_id, evidence_ids_json, source_documents_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                (
                    record.run_id,
                    record.task_id,
                    _json(record.evidence_ids),
                    _json(record.source_documents),
                )
                for record in records
            ),
        )

    def _write_memo_traces(
        self,
        connection: sqlite3.Connection,
        records: Iterable[MemoTrace],
    ) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO memo_traces
            (run_id, memo_id, conclusion_count, artifact_path, memo_snippet)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    record.run_id,
                    record.memo_id,
                    record.conclusion_count,
                    record.artifact_path,
                    record.memo_snippet,
                )
                for record in records
            ),
        )

    def _write_artifact_manifests(
        self,
        connection: sqlite3.Connection,
        records: Iterable[ArtifactManifest],
    ) -> None:
        connection.executemany(
            """
            INSERT OR REPLACE INTO artifact_manifests
            (run_id, artifact_paths_json, trace_database_path, config_hash, corpus_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    record.run_id,
                    _json(record.artifact_paths),
                    record.trace_database_path,
                    record.config_hash,
                    record.corpus_version,
                )
                for record in records
            ),
        )


def build_case_study_trace_bundle(
    case_studies: Optional[Iterable[PortfolioCaseStudy]] = None,
    trace_database_path: str = "experiments/traces/phase16_trace.sqlite",
    corpus_version: str = DEFAULT_CORPUS_VERSION,
) -> EvidenceTraceBundle:
    """Build deterministic trace records for the three portfolio case studies."""

    cases = tuple(case_studies or build_portfolio_case_studies())
    run_manifests = []
    retrieval_traces = []
    verification_traces = []
    evidence_traces = []
    memo_traces = []
    artifact_manifests = []

    for index, case in enumerate(cases, start=1):
        method_result = case.method_results["full_engine_real"]
        artifact_paths = (
            f"experiments/case_studies/{case.case_id}.json",
            f"reports/case_studies/{case.case_id}.md",
        )
        config_hash = _config_hash(
            {
                "case_id": case.case_id,
                "task_id": case.task_id,
                "method": method_result.method,
                "expected_verdict": case.expected_verdict,
                "corpus_version": corpus_version,
                "artifact_paths": artifact_paths,
            }
        )
        run_id = f"trace:{case.case_id}:{config_hash[:12]}"
        retrieved_chunks = tuple(
            evidence.evidence_key for evidence in method_result.retrieved_evidence
        )
        validator_results = {
            check.validator: check.status for check in method_result.validator_checks
        }
        evidence_ids = _unique(
            tuple(evidence.evidence_key for evidence in case.gold_evidence)
            + tuple(evidence.evidence_key for evidence in method_result.retrieved_evidence)
        )
        source_documents = _unique(
            tuple(_source_document_id(evidence) for evidence in case.gold_evidence)
            + tuple(_source_document_id(evidence) for evidence in method_result.retrieved_evidence)
        )

        run_manifests.append(
            RunManifest(
                run_id=run_id,
                config_hash=config_hash,
                corpus_version=corpus_version,
                method=method_result.method,
                task_id=case.task_id,
                started_at=PHASE16_TRACE_TIMESTAMP,
                runtime_ms=25 + index,
                artifact_paths=artifact_paths,
            )
        )
        retrieval_traces.append(
            RetrievalTrace(
                run_id=run_id,
                method=method_result.method,
                task_id=case.task_id,
                retrieved_chunks=retrieved_chunks,
            )
        )
        verification_traces.append(
            VerificationTrace(
                run_id=run_id,
                task_id=case.task_id,
                validator_results=validator_results,
                final_verdict=case.final_full_engine_verdict,
                expected_verdict=case.expected_verdict,
            )
        )
        evidence_traces.append(
            EvidenceTrace(
                run_id=run_id,
                task_id=case.task_id,
                evidence_ids=evidence_ids,
                source_documents=source_documents,
            )
        )
        memo_traces.append(
            MemoTrace(
                run_id=run_id,
                memo_id=f"memo:{case.case_id}",
                conclusion_count=1,
                artifact_path=artifact_paths[1],
                memo_snippet=case.memo_snippet,
            )
        )
        artifact_manifests.append(
            ArtifactManifest(
                run_id=run_id,
                artifact_paths=artifact_paths,
                trace_database_path=trace_database_path,
                config_hash=config_hash,
                corpus_version=corpus_version,
            )
        )

    return EvidenceTraceBundle(
        run_manifests=tuple(run_manifests),
        retrieval_traces=tuple(retrieval_traces),
        verification_traces=tuple(verification_traces),
        evidence_traces=tuple(evidence_traces),
        memo_traces=tuple(memo_traces),
        artifact_manifests=tuple(artifact_manifests),
    )


def regenerate_case_studies_from_trace(bundle: EvidenceTraceBundle) -> Tuple[Mapping[str, object], ...]:
    """Regenerate compact case-study records from persisted trace data."""

    verification_by_run_id = {
        trace.run_id: trace for trace in bundle.verification_traces
    }
    artifact_by_run_id = {
        manifest.run_id: manifest for manifest in bundle.artifact_manifests
    }
    regenerated = []
    for run in bundle.run_manifests:
        case_id = _case_id_from_run_id(run.run_id)
        verification = verification_by_run_id[run.run_id]
        artifact = artifact_by_run_id[run.run_id]
        regenerated.append(
            {
                "case_id": case_id,
                "run_id": run.run_id,
                "task_id": run.task_id,
                "method": run.method,
                "final_verdict": verification.final_verdict,
                "artifact_paths": list(artifact.artifact_paths),
            }
        )
    return tuple(regenerated)


def write_trace_artifacts(
    bundle: EvidenceTraceBundle,
    trace_db_path: Path = Path("experiments/traces/phase16_trace.sqlite"),
    artifact_manifest_path: Path = Path("reports/traces/phase16_artifact_manifest.json"),
) -> TraceArtifactWriteResult:
    """Persist the trace bundle into SQLite and write a JSON artifact manifest."""

    if trace_db_path.exists():
        trace_db_path.unlink()
    store = TraceStore(trace_db_path)
    store.write_bundle(bundle)
    summary = store.integrity_summary()
    artifact_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    corpus_versions = sorted({record.corpus_version for record in bundle.run_manifests})
    payload = {
        "trace_db_path": str(trace_db_path),
        "run_count": len(bundle.run_manifests),
        "corpus_version": corpus_versions[0] if len(corpus_versions) == 1 else corpus_versions,
        "trace_integrity": summary["trace_integrity"],
        "integrity_summary": dict(summary),
        "runs": [record.to_dict() for record in bundle.run_manifests],
        "artifact_manifests": [record.to_dict() for record in bundle.artifact_manifests],
        "regenerated_case_studies": list(regenerate_case_studies_from_trace(bundle)),
    }
    artifact_manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return TraceArtifactWriteResult(
        trace_db_path=trace_db_path,
        artifact_manifest_path=artifact_manifest_path,
        integrity_summary=summary,
    )


def _config_hash(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _unique(values: Iterable[str]) -> Tuple[str, ...]:
    seen = set()
    ordered = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _source_document_id(evidence: EvidenceReference) -> str:
    metric = evidence.metric or "n/a"
    return f"{evidence.company_ticker}:{evidence.source_type}:{evidence.fiscal_period}:{metric}"


def _case_id_from_run_id(run_id: str) -> str:
    parts = run_id.split(":")
    if len(parts) < 3:
        raise ValueError(f"Invalid trace run id: {run_id}")
    return parts[1]


def _table_count(connection: sqlite3.Connection, table_name: str) -> int:
    cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
    return int(cursor.fetchone()[0])


def _json_array_total(connection: sqlite3.Connection, table_name: str, column_name: str) -> int:
    cursor = connection.execute(f"SELECT {column_name} FROM {table_name}")
    return sum(len(json.loads(row[0])) for row in cursor.fetchall())


def _json_object_total(connection: sqlite3.Connection, table_name: str, column_name: str) -> int:
    cursor = connection.execute(f"SELECT {column_name} FROM {table_name}")
    return sum(len(json.loads(row[0])) for row in cursor.fetchall())
