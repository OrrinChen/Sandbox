"""Runtime config loaders for project-owned configuration files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from sandboxed_agent_eval_harness.agents import default_agent_baselines
from sandboxed_agent_eval_harness.tasks import (
    benchmark_task_suite,
    default_task_suite,
    load_task_suite,
    trading_task_suite,
)
from sandboxed_agent_eval_harness.tools import default_tool_registry
from sandboxed_agent_eval_harness.validators import default_validator_names


class ProjectConfigValidationError(ValueError):
    """Raised when project config files are malformed or drift from runtime surfaces."""


@dataclass(frozen=True)
class ConfiguredTool:
    tool_name: str
    domain: str
    backing: str
    permissions: list[str]
    side_effects: list[str]
    failure_modes: list[str]


@dataclass(frozen=True)
class ToolsConfig:
    tools: list[ConfiguredTool]

    def names(self) -> list[str]:
        return sorted(tool.tool_name for tool in self.tools)


@dataclass(frozen=True)
class ConfiguredValidator:
    name: str
    purpose: str
    failure_types: list[str]


@dataclass(frozen=True)
class ValidatorsConfig:
    validators: list[ConfiguredValidator]

    def names(self) -> list[str]:
        return [validator.name for validator in self.validators]


@dataclass(frozen=True)
class ConfiguredTaskSuite:
    suite_id: str
    version: str
    manifest: Path
    status: str
    domains: list[str]
    tasks: list[str]


@dataclass(frozen=True)
class TaskSuitesConfig:
    task_suites: list[ConfiguredTaskSuite]

    def ids(self) -> list[str]:
        return [suite.suite_id for suite in self.task_suites]

    def manifest_paths(self) -> list[Path]:
        return [suite.manifest for suite in self.task_suites]

    def get(self, suite_id: str) -> ConfiguredTaskSuite:
        for suite in self.task_suites:
            if suite.suite_id == suite_id:
                return suite
        raise ProjectConfigValidationError(f"unknown configured task suite: {suite_id}")

    def task_ids_for(self, suite_id: str) -> list[str]:
        return list(self.get(suite_id).tasks)


@dataclass(frozen=True)
class ConfiguredEvalRun:
    run_id: str
    suite: str
    trials_per_task: int
    output_dir: str
    baselines: list[str]
    metrics: list[str]


@dataclass(frozen=True)
class EvalRunsConfig:
    eval_runs: list[ConfiguredEvalRun]

    def ids(self) -> list[str]:
        return [run.run_id for run in self.eval_runs]

    def get(self, run_id: str) -> ConfiguredEvalRun:
        for run in self.eval_runs:
            if run.run_id == run_id:
                return run
        raise ProjectConfigValidationError(f"unknown configured eval run: {run_id}")


@dataclass(frozen=True)
class ProjectConfigReport:
    config_dir: Path
    passed: bool
    tools: ToolsConfig
    validators: ValidatorsConfig
    task_suites: TaskSuitesConfig
    eval_runs: EvalRunsConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_dir": str(self.config_dir),
            "passed": self.passed,
            "tool_count": len(self.tools.tools),
            "tool_names": self.tools.names(),
            "validator_count": len(self.validators.validators),
            "validator_names": self.validators.names(),
            "task_suite_count": len(self.task_suites.task_suites),
            "task_suite_ids": self.task_suites.ids(),
            "eval_run_count": len(self.eval_runs.eval_runs),
            "eval_run_ids": self.eval_runs.ids(),
        }


def default_config_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "configs"


def load_tools_config(path: Optional[Path | str] = None) -> ToolsConfig:
    payload = _load_root_list_config(_resolve_config_path(path, "tools.yaml"), "tools")
    tools = [
        ConfiguredTool(
            tool_name=_require_string(item, "tool_name", f"tools[{index}]"),
            domain=_require_string(item, "domain", f"tools[{index}]"),
            backing=_require_string(item, "backing", f"tools[{index}]"),
            permissions=_require_string_list(item, "permissions", f"tools[{index}]"),
            side_effects=_require_string_list(item, "side_effects", f"tools[{index}]"),
            failure_modes=_require_string_list(item, "failure_modes", f"tools[{index}]"),
        )
        for index, item in enumerate(payload)
    ]
    _reject_duplicate_values([tool.tool_name for tool in tools], "tools.tool_name")
    return ToolsConfig(tools=tools)


def load_validators_config(path: Optional[Path | str] = None) -> ValidatorsConfig:
    payload = _load_root_list_config(_resolve_config_path(path, "validators.yaml"), "validators")
    validators = [
        ConfiguredValidator(
            name=_require_string(item, "name", f"validators[{index}]"),
            purpose=_require_string(item, "purpose", f"validators[{index}]"),
            failure_types=_require_string_list(item, "failure_types", f"validators[{index}]"),
        )
        for index, item in enumerate(payload)
    ]
    _reject_duplicate_values([validator.name for validator in validators], "validators.name")
    return ValidatorsConfig(validators=validators)


def load_task_suites_config(path: Optional[Path | str] = None) -> TaskSuitesConfig:
    payload = _load_root_list_config(_resolve_config_path(path, "task_suites.yaml"), "task_suites")
    task_suites = [
        ConfiguredTaskSuite(
            suite_id=_require_string(item, "id", f"task_suites[{index}]"),
            version=_require_string(item, "version", f"task_suites[{index}]"),
            manifest=Path(_require_string(item, "manifest", f"task_suites[{index}]")),
            status=_require_string(item, "status", f"task_suites[{index}]"),
            domains=_require_string_list(item, "domains", f"task_suites[{index}]"),
            tasks=_require_string_list(item, "tasks", f"task_suites[{index}]"),
        )
        for index, item in enumerate(payload)
    ]
    _reject_duplicate_values([suite.suite_id for suite in task_suites], "task_suites.id")
    return TaskSuitesConfig(task_suites=task_suites)


def load_eval_runs_config(path: Optional[Path | str] = None) -> EvalRunsConfig:
    payload = _load_root_list_config(_resolve_config_path(path, "eval_runs.yaml"), "eval_runs")
    eval_runs = [
        ConfiguredEvalRun(
            run_id=_require_string(item, "id", f"eval_runs[{index}]"),
            suite=_require_string(item, "suite", f"eval_runs[{index}]"),
            trials_per_task=_require_positive_int(item, "trials_per_task", f"eval_runs[{index}]"),
            output_dir=_require_string(item, "output_dir", f"eval_runs[{index}]"),
            baselines=_require_string_list(item, "baselines", f"eval_runs[{index}]"),
            metrics=_require_string_list(item, "metrics", f"eval_runs[{index}]"),
        )
        for index, item in enumerate(payload)
    ]
    _reject_duplicate_values([run.run_id for run in eval_runs], "eval_runs.id")
    return EvalRunsConfig(eval_runs=eval_runs)


def validate_project_config(config_dir: Optional[Path | str] = None) -> ProjectConfigReport:
    base_dir = Path(config_dir) if config_dir is not None else default_config_dir()
    project_root = base_dir.parent
    tools = load_tools_config(base_dir)
    validators = load_validators_config(base_dir)
    task_suites = load_task_suites_config(base_dir)
    eval_runs = load_eval_runs_config(base_dir)

    runtime_tool_names = default_tool_registry().names()
    if tools.names() != runtime_tool_names:
        raise ProjectConfigValidationError(
            "tools config names do not match runtime defaults: "
            f"config={tools.names()} runtime={runtime_tool_names}"
        )

    runtime_validator_names = default_validator_names()
    if validators.names() != runtime_validator_names:
        raise ProjectConfigValidationError(
            "validators config names do not match runtime defaults: "
            f"config={validators.names()} runtime={runtime_validator_names}"
        )

    expected_suites = {
        default_task_suite().suite_id: default_task_suite(),
        benchmark_task_suite().suite_id: benchmark_task_suite(),
        trading_task_suite().suite_id: trading_task_suite(),
    }
    if set(task_suites.ids()) != set(expected_suites):
        raise ProjectConfigValidationError(
            "task suite config ids do not match runtime suites: "
            f"config={task_suites.ids()} runtime={sorted(expected_suites)}"
        )
    for configured_suite in task_suites.task_suites:
        manifest_path = project_root / configured_suite.manifest
        runtime_suite = load_task_suite(manifest_path)
        expected_suite = expected_suites[configured_suite.suite_id]
        _validate_configured_task_suite(configured_suite, runtime_suite, expected_suite)

    runtime_baselines = [baseline.name for baseline in default_agent_baselines()]
    for eval_run in eval_runs.eval_runs:
        if eval_run.suite not in task_suites.ids():
            raise ProjectConfigValidationError(
                f"eval run {eval_run.run_id} references unknown task suite: {eval_run.suite}"
            )
        if eval_run.baselines != runtime_baselines:
            raise ProjectConfigValidationError(
                f"eval run {eval_run.run_id} baselines do not match runtime defaults: "
                f"config={eval_run.baselines} runtime={runtime_baselines}"
            )
        _validate_eval_run_metrics(eval_run)

    return ProjectConfigReport(
        config_dir=base_dir,
        passed=True,
        tools=tools,
        validators=validators,
        task_suites=task_suites,
        eval_runs=eval_runs,
    )


def _validate_configured_task_suite(
    configured_suite: ConfiguredTaskSuite,
    manifest_suite: Any,
    expected_suite: Any,
) -> None:
    if manifest_suite.suite_id != configured_suite.suite_id:
        raise ProjectConfigValidationError(
            f"task suite {configured_suite.suite_id} manifest suite_id mismatch: {manifest_suite.suite_id}"
        )
    if configured_suite.version != expected_suite.version:
        raise ProjectConfigValidationError(
            f"task suite {configured_suite.suite_id} version mismatch: "
            f"config={configured_suite.version} runtime={expected_suite.version}"
        )
    if configured_suite.tasks != expected_suite.task_ids():
        raise ProjectConfigValidationError(
            f"task suite {configured_suite.suite_id} task ids do not match manifest/runtime"
        )
    runtime_domains = sorted({task.domain for task in expected_suite.tasks})
    if sorted(configured_suite.domains) != runtime_domains:
        raise ProjectConfigValidationError(
            f"task suite {configured_suite.suite_id} domains do not match runtime: "
            f"config={sorted(configured_suite.domains)} runtime={runtime_domains}"
        )


def _validate_eval_run_metrics(eval_run: ConfiguredEvalRun) -> None:
    required_metrics = {
        "task_success_rate",
        "pass_at_k",
        "tool_selection_accuracy",
        "argument_correctness",
        "state_correctness",
        "numeric_correctness",
        "citation_correctness",
        "constraint_correctness",
        "unit_test_correctness",
        "policy_correctness",
        "cost_latency_correctness",
        "lookahead_correctness",
        "pnl_consistency_correctness",
        "cost_inclusion_correctness",
        "risk_limit_correctness",
        "artifact_grounding_correctness",
        "average_turns",
        "average_latency_seconds",
        "average_cost",
        "timeout_rate",
    }
    missing = sorted(required_metrics - set(eval_run.metrics))
    if missing:
        raise ProjectConfigValidationError(f"eval run {eval_run.run_id} missing configured metrics: {missing}")


def _resolve_config_path(path: Optional[Path | str], file_name: str) -> Path:
    if path is None:
        return default_config_dir() / file_name
    candidate = Path(path)
    if candidate.is_dir() or candidate.suffix == "":
        return candidate / file_name
    return candidate


def _load_root_list_config(path: Path, root_key: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise ProjectConfigValidationError(f"could not read config file: {path}") from exc

    entries: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    active_list_key: Optional[str] = None
    saw_root = False
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if indent == 0:
            if stripped != f"{root_key}:":
                raise ProjectConfigValidationError(f"{path}:{line_number}: expected root key {root_key!r}")
            saw_root = True
            continue
        if not saw_root:
            raise ProjectConfigValidationError(f"{path}:{line_number}: missing root key {root_key!r}")
        if indent == 2 and stripped.startswith("- "):
            if current is not None:
                entries.append(current)
            current = {}
            active_list_key = None
            _assign_key_value(current, stripped[2:], path, line_number)
            continue
        if current is None:
            raise ProjectConfigValidationError(f"{path}:{line_number}: expected list item")
        if indent == 4 and ":" in stripped:
            key, value = _split_key_value(stripped, path, line_number)
            if value == "":
                current[key] = []
                active_list_key = key
            else:
                current[key] = _parse_scalar(value)
                active_list_key = None
            continue
        if indent == 6 and stripped.startswith("- ") and active_list_key:
            current.setdefault(active_list_key, [])
            if not isinstance(current[active_list_key], list):
                raise ProjectConfigValidationError(f"{path}:{line_number}: {active_list_key} must be a list")
            current[active_list_key].append(_parse_scalar(stripped[2:]))
            continue
        # Nested descriptive mappings such as tools.state_mutation are not part of
        # the runtime loader contract yet. Ignore them, but keep malformed root
        # structure deterministic.
        if indent >= 6:
            continue
        raise ProjectConfigValidationError(f"{path}:{line_number}: unsupported config shape")
    if current is not None:
        entries.append(current)
    if not saw_root:
        raise ProjectConfigValidationError(f"{path}: missing root key {root_key!r}")
    if not entries:
        raise ProjectConfigValidationError(f"{path}: {root_key} must contain at least one item")
    return entries


def _assign_key_value(item: dict[str, Any], expression: str, path: Path, line_number: int) -> None:
    key, value = _split_key_value(expression, path, line_number)
    item[key] = _parse_scalar(value)


def _split_key_value(expression: str, path: Path, line_number: int) -> tuple[str, str]:
    if ":" not in expression:
        raise ProjectConfigValidationError(f"{path}:{line_number}: expected key/value pair")
    key, value = expression.split(":", 1)
    key = key.strip()
    if not key:
        raise ProjectConfigValidationError(f"{path}:{line_number}: empty key")
    return key, value.strip()


def _parse_scalar(value: str) -> Any:
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    try:
        return int(value)
    except ValueError:
        return value


def _require_string(item: Mapping[str, Any], key: str, context: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise ProjectConfigValidationError(f"{context}.{key} must be a non-empty string")
    return value


def _require_positive_int(item: Mapping[str, Any], key: str, context: str) -> int:
    value = item.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProjectConfigValidationError(f"{context}.{key} must be a positive integer")
    return value


def _require_string_list(item: Mapping[str, Any], key: str, context: str) -> list[str]:
    value = item.get(key)
    if not isinstance(value, list) or any(not isinstance(element, str) or not element for element in value):
        raise ProjectConfigValidationError(f"{context}.{key} must be a list of strings")
    return list(value)


def _reject_duplicate_values(values: Iterable[str], context: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ProjectConfigValidationError(f"{context} contains duplicate values: {duplicates}")
