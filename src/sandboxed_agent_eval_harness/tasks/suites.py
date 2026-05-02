"""Fixture-backed task suite loading utilities."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from sandboxed_agent_eval_harness.schemas import JsonDict, SchemaValidationError, TaskSpec


TASK_FIELDS = (
    "task_id",
    "domain",
    "instruction",
    "available_tools",
    "initial_state",
    "hidden_expected_state",
    "visible_files",
    "success_criteria",
    "validator_list",
    "max_turns",
    "max_cost",
    "timeout_seconds",
)
DEFAULT_TASK_SUITE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "tasks" / "initial_suite.json"
)
BENCHMARK_TASK_SUITE_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "tasks" / "benchmark_suite.json"
)


class TaskSuiteValidationError(ValueError):
    """Raised when a task suite manifest is malformed."""


@dataclass(frozen=True)
class TaskSuite:
    suite_id: str
    version: str
    tasks: list[TaskSpec]
    task_metadata: dict[str, JsonDict]

    def __post_init__(self) -> None:
        if not isinstance(self.suite_id, str) or not self.suite_id.strip():
            raise TaskSuiteValidationError("suite_id must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise TaskSuiteValidationError("version must be a non-empty string")
        if not self.tasks:
            raise TaskSuiteValidationError("task suite must contain at least one task")
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise TaskSuiteValidationError("task suite contains duplicate task_id values")
        for task in self.tasks:
            if task.task_id not in self.task_metadata:
                raise TaskSuiteValidationError(f"task metadata missing for {task.task_id}")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskSuite":
        suite_id = _require_non_empty_string(payload, "suite_id")
        version = _require_non_empty_string(payload, "version")
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list):
            raise TaskSuiteValidationError("tasks must be a list")

        tasks: list[TaskSpec] = []
        metadata: dict[str, JsonDict] = {}
        for index, raw_task in enumerate(raw_tasks):
            if not isinstance(raw_task, dict):
                raise TaskSuiteValidationError(f"tasks[{index}] must be an object")
            try:
                task = TaskSpec.from_dict({field_name: raw_task[field_name] for field_name in TASK_FIELDS})
            except (KeyError, SchemaValidationError, TypeError, ValueError) as exc:
                task_id = raw_task.get("task_id", f"tasks[{index}]")
                raise TaskSuiteValidationError(f"{task_id}: {exc}") from exc
            if not task.hidden_expected_state:
                raise TaskSuiteValidationError(f"{task.task_id}: hidden_expected_state must not be empty")

            task_metadata = _metadata_from_raw_task(raw_task, task.task_id)
            tasks.append(task)
            metadata[task.task_id] = task_metadata
        return cls(suite_id=suite_id, version=version, tasks=tasks, task_metadata=metadata)

    def task_ids(self) -> list[str]:
        return [task.task_id for task in self.tasks]

    def tasks_by_domain(self, domain: str) -> list[TaskSpec]:
        return [task for task in self.tasks if task.domain == domain]

    def metadata_for(self, task_id: str) -> JsonDict:
        try:
            return dict(self.task_metadata[task_id])
        except KeyError as exc:
            raise TaskSuiteValidationError(f"unknown task_id: {task_id}") from exc


def load_task_suite(path: Path | str) -> TaskSuite:
    suite_path = Path(path)
    try:
        payload = json.loads(suite_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskSuiteValidationError(f"could not load task suite: {suite_path}") from exc
    if not isinstance(payload, dict):
        raise TaskSuiteValidationError("task suite manifest must be an object")
    return TaskSuite.from_dict(payload)


def default_task_suite() -> TaskSuite:
    return load_task_suite(DEFAULT_TASK_SUITE_PATH)


def default_task_suite_path() -> Path:
    return DEFAULT_TASK_SUITE_PATH


def benchmark_task_suite() -> TaskSuite:
    return load_task_suite(BENCHMARK_TASK_SUITE_PATH)


def benchmark_task_suite_path() -> Path:
    return BENCHMARK_TASK_SUITE_PATH


def task_suite_by_name(name: str) -> TaskSuite:
    if name in {"smoke", "initial", "default"}:
        return default_task_suite()
    if name == "benchmark":
        return benchmark_task_suite()
    raise TaskSuiteValidationError(f"unknown task suite: {name}")


def known_task_suites() -> list[TaskSuite]:
    return [default_task_suite(), benchmark_task_suite()]


def _metadata_from_raw_task(raw_task: Mapping[str, Any], task_id: str) -> JsonDict:
    fixture_paths = raw_task.get("fixture_paths")
    gold_outputs = raw_task.get("gold_outputs")
    known_failure_traps = raw_task.get("known_failure_traps")
    final_answer_only_risk = raw_task.get("final_answer_only_risk")

    if not isinstance(fixture_paths, list) or any(not isinstance(path, str) for path in fixture_paths):
        raise TaskSuiteValidationError(f"{task_id}: fixture_paths must be a list of strings")
    if not isinstance(gold_outputs, dict) or not gold_outputs:
        raise TaskSuiteValidationError(f"{task_id}: gold_outputs must be a non-empty object")
    if not isinstance(known_failure_traps, list) or any(not isinstance(item, str) for item in known_failure_traps):
        raise TaskSuiteValidationError(f"{task_id}: known_failure_traps must be a list of strings")
    if not known_failure_traps:
        raise TaskSuiteValidationError(f"{task_id}: known_failure_traps must not be empty")
    if not isinstance(final_answer_only_risk, bool):
        raise TaskSuiteValidationError(f"{task_id}: final_answer_only_risk must be a boolean")

    return {
        "fixture_paths": list(fixture_paths),
        "gold_outputs": dict(gold_outputs),
        "known_failure_traps": list(known_failure_traps),
        "failure_taxonomy_traps": _optional_string_list(raw_task, "failure_taxonomy_traps"),
        "final_answer_only_risk": final_answer_only_risk,
    }


def _require_non_empty_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise TaskSuiteValidationError(f"{field_name} must be a non-empty string")
    return value


def _optional_string_list(payload: Mapping[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        task_id = payload.get("task_id", "unknown-task")
        raise TaskSuiteValidationError(f"{task_id}: {field_name} must be a list of strings")
    return list(value)
