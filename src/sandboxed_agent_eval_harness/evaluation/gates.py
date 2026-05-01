"""Configurable regression threshold gates for evaluation artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor


@dataclass(frozen=True)
class RegressionGatePreset:
    preset_id: str
    description: str
    thresholds: JsonDict
    replay: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "id": self.preset_id,
            "description": self.description,
            "thresholds": dict(self.thresholds),
            "replay": dict(self.replay),
        }


@dataclass(frozen=True)
class RegressionGateResult:
    name: str
    passed: bool
    message: str
    details: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class RegressionGateReport:
    results: list[RegressionGateResult]
    replay_divergence_summary: JsonDict
    preset: Optional[RegressionGatePreset] = None

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> JsonDict:
        return {
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
            "failed_results": [result.to_dict() for result in self.results if not result.passed],
            "replay_divergence_summary": dict(self.replay_divergence_summary),
            "preset": self.preset.to_dict() if self.preset else None,
        }


def evaluate_regression_gates(
    summary: Any,
    thresholds: Mapping[str, Any],
    previous_summary: Optional[Any] = None,
    replay_results: Optional[Sequence[Any]] = None,
    preset: Optional[RegressionGatePreset] = None,
) -> RegressionGateReport:
    """Evaluate configured pass/fail gates against an evaluation summary."""

    if not isinstance(thresholds, Mapping):
        raise TypeError("thresholds must be a mapping")

    summary_dict = _summary_to_dict(summary)
    previous_dict = _summary_to_dict(previous_summary) if previous_summary is not None else None
    metrics = _metrics(summary_dict)
    results: list[RegressionGateResult] = []

    if "min_task_success_rate" in thresholds:
        minimum = _as_float(thresholds["min_task_success_rate"], "min_task_success_rate")
        current = _metric_float(metrics, "task_success_rate")
        results.append(
            _gate_result(
                "task_success_rate",
                current >= minimum,
                f"Task success rate {current:.3f} must be at least {minimum:.3f}.",
                {"current": current, "minimum": minimum},
            )
        )

    if "min_pass_at_k" in thresholds:
        minimum = _as_float(thresholds["min_pass_at_k"], "min_pass_at_k")
        current = _pass_at_k_value(metrics)
        results.append(
            _gate_result(
                "pass_at_k",
                current >= minimum,
                f"pass@k {current:.3f} must be at least {minimum:.3f}.",
                {"current": current, "minimum": minimum},
            )
        )

    if "max_task_success_rate_drop" in thresholds:
        maximum = _as_float(thresholds["max_task_success_rate_drop"], "max_task_success_rate_drop")
        results.append(
            _drop_gate_result(
                name="task_success_rate_drop",
                current_metrics=metrics,
                previous_summary=previous_dict,
                metric_name="task_success_rate",
                maximum=maximum,
            )
        )

    if "max_pass_at_k_drop" in thresholds:
        maximum = _as_float(thresholds["max_pass_at_k_drop"], "max_pass_at_k_drop")
        if previous_dict is None:
            results.append(_missing_previous_result("pass_at_k_drop"))
        else:
            previous_value = _pass_at_k_value(_metrics(previous_dict))
            current_value = _pass_at_k_value(metrics)
            drop = previous_value - current_value
            results.append(
                _gate_result(
                    "pass_at_k_drop",
                    drop <= maximum,
                    f"pass@k drop {drop:.3f} must be no more than {maximum:.3f}.",
                    {
                        "current": current_value,
                        "previous": previous_value,
                        "drop": drop,
                        "maximum": maximum,
                    },
                )
            )

    if "max_failure_taxonomy" in thresholds:
        failure_limits = thresholds["max_failure_taxonomy"]
        if not isinstance(failure_limits, Mapping):
            raise ValueError("max_failure_taxonomy must be a mapping of failure type to maximum count")
        failure_taxonomy = _failure_taxonomy(metrics)
        for failure_type, raw_maximum in sorted(failure_limits.items()):
            maximum = _as_int(raw_maximum, f"max_failure_taxonomy.{failure_type}")
            current = int(failure_taxonomy.get(str(failure_type), 0))
            results.append(
                _gate_result(
                    f"failure_taxonomy.{failure_type}",
                    current <= maximum,
                    f"Failure type {failure_type} count {current} must be no more than {maximum}.",
                    {"current": current, "maximum": maximum, "failure_type": str(failure_type)},
                )
            )

    replay_summary = _replay_divergence_summary(summary_dict, replay_results)
    if "max_replay_divergences" in thresholds:
        maximum = _as_int(thresholds["max_replay_divergences"], "max_replay_divergences")
        if replay_summary.get("available") is not True:
            results.append(
                _gate_result(
                    "replay_divergences",
                    False,
                    "Replay divergence threshold was configured but no replay data was supplied.",
                    {"maximum": maximum, "available": False},
                )
            )
        else:
            current = int(replay_summary.get("divergence_count", 0))
            results.append(
                _gate_result(
                    "replay_divergences",
                    current <= maximum,
                    f"Replay divergence count {current} must be no more than {maximum}.",
                    {"current": current, "maximum": maximum},
                )
            )

    return RegressionGateReport(results=results, replay_divergence_summary=replay_summary, preset=preset)


def default_threshold_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / "regression_gates.json"


def load_threshold_preset(
    preset_id: str,
    config_path: Optional[Path | str] = None,
) -> RegressionGatePreset:
    config = _load_json(config_path or default_threshold_config_path())
    presets = config.get("presets", [])
    if not isinstance(presets, list):
        raise ValueError("threshold config presets must be a list")
    for preset in presets:
        if not isinstance(preset, Mapping):
            raise ValueError("threshold config presets must be objects")
        if preset.get("id") != preset_id:
            continue
        thresholds = preset.get("thresholds", {})
        replay = preset.get("replay", {})
        if not isinstance(thresholds, Mapping):
            raise ValueError(f"threshold preset {preset_id} thresholds must be an object")
        if not isinstance(replay, Mapping):
            raise ValueError(f"threshold preset {preset_id} replay must be an object")
        description = preset.get("description", "")
        return RegressionGatePreset(
            preset_id=preset_id,
            description=description if isinstance(description, str) else "",
            thresholds=dict(thresholds),
            replay=dict(replay),
        )
    raise ValueError(f"unknown threshold preset: {preset_id}")


def discover_trace_paths(summary: Any) -> list[str]:
    summary_dict = _summary_to_dict(summary)
    raw_runs = summary_dict.get("runs", [])
    if not isinstance(raw_runs, list):
        raise ValueError("summary runs must be a list")
    trace_paths: set[str] = set()
    for run in raw_runs:
        if not isinstance(run, Mapping):
            continue
        trace_path = run.get("trace_path")
        if isinstance(trace_path, str) and trace_path.strip():
            trace_paths.add(trace_path)
    return sorted(trace_paths)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate regression threshold gates.")
    parser.add_argument("--summary", required=True, help="Path to the current summary.json artifact.")
    parser.add_argument("--thresholds", help="Path to a JSON threshold configuration.")
    parser.add_argument(
        "--threshold-config",
        default=str(default_threshold_config_path()),
        help="Path to a JSON threshold preset configuration.",
    )
    parser.add_argument("--threshold-preset", help="Preset id to load from the threshold config.")
    parser.add_argument("--previous-summary", help="Optional previous summary.json artifact.")
    parser.add_argument("--replay-trace", action="append", default=[], help="Trace JSONL path to replay before gating.")
    parser.add_argument("--discover-traces", action="store_true", help="Replay traces listed in summary run records.")
    parser.add_argument(
        "--replay-workspace",
        default="/tmp/sandboxed-agent-eval-gates-replay",
        help="Base workspace directory for replayed traces.",
    )
    args = parser.parse_args(argv)
    if args.thresholds and args.threshold_preset:
        parser.error("--thresholds and --threshold-preset are mutually exclusive")

    summary = _load_json(args.summary)
    preset = load_threshold_preset(args.threshold_preset, args.threshold_config) if args.threshold_preset else None
    if args.thresholds:
        thresholds = _load_json(args.thresholds)
    elif preset is not None:
        thresholds = preset.thresholds
    else:
        parser.error("one of --thresholds or --threshold-preset is required")
    previous = _load_json(args.previous_summary) if args.previous_summary else None
    replay_traces = list(args.replay_trace)
    if args.discover_traces or (preset is not None and preset.replay.get("discover_from_summary") is True):
        replay_traces.extend(discover_trace_paths(summary))
    replay_results = _execute_replay_traces(_unique_sorted(replay_traces), Path(args.replay_workspace))
    report = evaluate_regression_gates(
        summary,
        thresholds=thresholds,
        previous_summary=previous,
        replay_results=replay_results if replay_traces else None,
        preset=preset,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


def _summary_to_dict(summary: Any) -> JsonDict:
    if hasattr(summary, "to_dict"):
        return summary.to_dict()
    if isinstance(summary, Mapping):
        return dict(summary)
    raise TypeError("summary must be an EvaluationSummary or mapping")


def _load_json(path: Path | str) -> JsonDict:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return payload


def _execute_replay_traces(trace_paths: Sequence[str], workspace: Path) -> list[JsonDict]:
    executor = TraceReplayExecutor()
    replay_results: list[JsonDict] = []
    for index, trace_path in enumerate(trace_paths):
        try:
            result = executor.replay(trace_path, workspace=workspace / f"trace-{index:03d}")
            replay_results.append(result.to_dict())
        except Exception as exc:  # pragma: no cover - defensive CLI reporting path
            replay_results.append(
                {
                    "trace_path": str(trace_path),
                    "passed": False,
                    "divergences": [
                        {
                            "type": "replay_execution_error",
                            "message": str(exc),
                        }
                    ],
                }
            )
    return replay_results


def _unique_sorted(values: Sequence[str]) -> list[str]:
    return sorted({value for value in values if value})


def _metrics(summary: Mapping[str, Any]) -> JsonDict:
    metrics = summary.get("metrics", {})
    if not isinstance(metrics, Mapping):
        raise ValueError("summary metrics must be an object")
    return dict(metrics)


def _metric_float(metrics: Mapping[str, Any], name: str) -> float:
    return _as_float(metrics.get(name, 0.0), name)


def _pass_at_k_value(metrics: Mapping[str, Any]) -> float:
    pass_at_k = metrics.get("pass_at_k", {})
    if isinstance(pass_at_k, Mapping):
        return _as_float(pass_at_k.get("value", 0.0), "pass_at_k.value")
    return _as_float(pass_at_k, "pass_at_k")


def _failure_taxonomy(metrics: Mapping[str, Any]) -> JsonDict:
    failure_taxonomy = metrics.get("failure_taxonomy", {})
    if not isinstance(failure_taxonomy, Mapping):
        raise ValueError("summary metrics failure_taxonomy must be an object")
    return dict(failure_taxonomy)


def _drop_gate_result(
    name: str,
    current_metrics: Mapping[str, Any],
    previous_summary: Optional[Mapping[str, Any]],
    metric_name: str,
    maximum: float,
) -> RegressionGateResult:
    if previous_summary is None:
        return _missing_previous_result(name)
    previous_value = _metric_float(_metrics(previous_summary), metric_name)
    current_value = _metric_float(current_metrics, metric_name)
    drop = previous_value - current_value
    return _gate_result(
        name,
        drop <= maximum,
        f"{metric_name} drop {drop:.3f} must be no more than {maximum:.3f}.",
        {
            "current": current_value,
            "previous": previous_value,
            "drop": drop,
            "maximum": maximum,
        },
    )


def _missing_previous_result(name: str) -> RegressionGateResult:
    return _gate_result(
        name,
        False,
        "Previous summary is required for this configured regression drop gate.",
        {"previous_summary_required": True},
    )


def _gate_result(name: str, passed: bool, message: str, details: JsonDict) -> RegressionGateResult:
    return RegressionGateResult(name=name, passed=passed, message=message, details=details)


def _replay_divergence_summary(summary: Mapping[str, Any], replay_results: Optional[Sequence[Any]]) -> JsonDict:
    if replay_results is not None:
        return replay_divergence_summary_from_results(replay_results)
    candidate = summary.get("replay_divergence_summary")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    return _empty_replay_divergence_summary(available=False)


def replay_divergence_summary_from_results(replay_results: Sequence[Any]) -> JsonDict:
    divergence_types: Counter[str] = Counter()
    replayed_traces = 0
    passed_trace_count = 0
    divergent_trace_count = 0
    divergence_count = 0
    for result in replay_results:
        result_dict = _replay_result_to_dict(result)
        divergences = [dict(item) for item in result_dict.get("divergences", []) if isinstance(item, Mapping)]
        replayed_traces += 1
        divergence_count += len(divergences)
        if result_dict.get("passed") is True and not divergences:
            passed_trace_count += 1
        else:
            divergent_trace_count += 1
        divergence_types.update(str(item.get("type", "unknown")) for item in divergences)
    return {
        "available": True,
        "replayed_traces": replayed_traces,
        "passed_trace_count": passed_trace_count,
        "divergent_trace_count": divergent_trace_count,
        "divergence_count": divergence_count,
        "divergence_types": dict(sorted(divergence_types.items())),
    }


def _replay_result_to_dict(result: Any) -> JsonDict:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError("replay_results entries must be TraceReplayExecutionResult objects or mappings")


def _empty_replay_divergence_summary(available: bool) -> JsonDict:
    return {
        "available": available,
        "replayed_traces": 0,
        "passed_trace_count": 0,
        "divergent_trace_count": 0,
        "divergence_count": 0,
        "divergence_types": {},
    }


def _as_float(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _as_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
