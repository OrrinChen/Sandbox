"""Outcome reward from the existing evaluator, plus anti-hacking checks.

The scalar reward is not the reported result. Held-out task success and
silent-failure counts are. A higher scalar with no success gain is flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence

from sandboxed_agent_eval_harness.evaluation.runner import _validate_plan
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec, TraceEvent, ValidatorResult
from sandboxed_agent_eval_harness.tools import ToolRegistry


SUCCESS_FLOOR = 0.05
FAILURE_CAP = 1.0
ORACLE_KEYS = (
    "hidden_expected_state",
    "gold_outputs",
    "known_failure_traps",
    "failure_taxonomy_traps",
    "success_criteria",
    "expected_tool_sequence",
    "tool_arguments",
)


@dataclass(frozen=True)
class RewardWeights:
    outcome: float = 1.0
    silent_failure: float = 0.2
    format_error: float = 0.05
    invalid_tool: float = 0.05
    incomplete: float = 0.05

    def __post_init__(self) -> None:
        for name in ("outcome", "silent_failure", "format_error", "invalid_tool", "incomplete"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{name} weight must be a non-negative number")
        if self.outcome <= SUCCESS_FLOOR:
            raise ValueError("outcome weight must be greater than the success floor")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RewardWeights":
        return cls(
            outcome=float(payload.get("outcome", 1.0)),
            silent_failure=float(payload.get("silent_failure", 0.2)),
            format_error=float(payload.get("format_error", 0.05)),
            invalid_tool=float(payload.get("invalid_tool", 0.05)),
            incomplete=float(payload.get("incomplete", 0.05)),
        )


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    passed: bool
    outcome: float
    silent_failure: float
    format_errors: int
    invalid_tool_calls: int
    incomplete: float
    final_answer_present: bool
    validator_results: tuple[ValidatorResult, ...]

    def to_dict(self) -> JsonDict:
        return {
            "total": self.total,
            "passed": self.passed,
            "outcome": self.outcome,
            "silent_failure": self.silent_failure,
            "format_errors": self.format_errors,
            "invalid_tool_calls": self.invalid_tool_calls,
            "incomplete": self.incomplete,
            "final_answer_present": self.final_answer_present,
            "validator_results": [result.to_dict() for result in self.validator_results],
        }


def compute_reward(
    *,
    passed: bool,
    final_answer_present: bool,
    format_errors: int,
    invalid_tool_calls: int,
    weights: RewardWeights | None = None,
    validator_results: Sequence[ValidatorResult] = (),
) -> RewardBreakdown:
    """Map an evaluator outcome to a scalar in a success-dominates-failure range.

    A passing episode is at least ``SUCCESS_FLOOR`` and at most the outcome
    weight. A failing episode is at most 0. Format compliance alone cannot
    make a failing episode positive.
    """

    reward_weights = weights or RewardWeights()
    if format_errors < 0 or invalid_tool_calls < 0:
        raise ValueError("error counts must be non-negative")
    silent = 1.0 if final_answer_present and not passed else 0.0
    incomplete = 1.0 if not passed and not final_answer_present else 0.0
    outcome = 1.0 if passed else 0.0
    penalty = (
        reward_weights.silent_failure * silent
        + reward_weights.format_error * format_errors
        + reward_weights.invalid_tool * invalid_tool_calls
        + reward_weights.incomplete * incomplete
    )
    if passed:
        total = min(reward_weights.outcome, max(reward_weights.outcome - penalty, SUCCESS_FLOOR))
    else:
        total = -min(penalty, FAILURE_CAP)
    return RewardBreakdown(
        total=total,
        passed=passed,
        outcome=outcome,
        silent_failure=silent,
        format_errors=format_errors,
        invalid_tool_calls=invalid_tool_calls,
        incomplete=incomplete,
        final_answer_present=final_answer_present,
        validator_results=tuple(validator_results),
    )


def score_trajectory(
    task: TaskSpec,
    *,
    final_answer: str,
    reported_metrics: Mapping[str, Any],
    plan_metrics: Mapping[str, Any],
    state_diff: Mapping[str, Any],
    trace_events: Sequence[TraceEvent],
    registry: ToolRegistry,
    format_errors: int,
    invalid_tool_calls: int,
    execution_errors: Sequence[str],
    timed_out: bool,
    weights: RewardWeights | None = None,
) -> RewardBreakdown:
    """Score a finished episode with the same validators as the eval runner."""

    validator_results = _validate_plan(
        task,
        final_answer,
        dict(reported_metrics),
        dict(plan_metrics),
        dict(state_diff),
        trace_events,
        registry,
    )
    if execution_errors:
        validator_results.append(
            ValidatorResult(
                validator_name="tool_execution",
                passed=False,
                failure_type="tool_execution_error",
                message="One or more fixture-backed tool calls failed.",
                details={"errors": list(execution_errors)},
            )
        )
    passed = (not timed_out) and all(result.passed for result in validator_results)
    return compute_reward(
        passed=passed,
        final_answer_present=bool(final_answer.strip()),
        format_errors=format_errors,
        invalid_tool_calls=invalid_tool_calls,
        weights=weights,
        validator_results=validator_results,
    )


def oracle_leak_findings(
    observation: Mapping[str, Any],
    task: TaskSpec,
    metadata: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return oracle strings that should not be visible before tool results exist.

    Tool results may legally contain numbers the agent just retrieved. The gold
    check therefore runs only on the initial observation, when history is empty.
    ``success_criteria`` strings are checked only when they are not already part
    of the visible instruction.
    """

    blob = json.dumps(observation, sort_keys=True)
    findings = [key for key in ORACLE_KEYS if f'"{key}"' in blob]
    history = observation.get("history", [])
    if history:
        return findings
    allowed_blob = json.dumps(_public_observation_fields(observation), sort_keys=True)
    hidden = task.hidden_expected_state
    for citation in hidden.get("citations", []):
        if isinstance(citation, str) and citation and _contains_token(blob, citation) and not _contains_token(allowed_blob, citation):
            findings.append(f"citation:{citation}")
    for metric, value in hidden.get("numeric", {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        rendered = str(int(value)) if isinstance(value, int) and not isinstance(value, bool) else str(value)
        if _contains_token(blob, rendered) and not _contains_token(allowed_blob, rendered):
            findings.append(f"numeric:{metric}")
    extra = metadata or {}
    for criterion in extra.get("success_criteria", []):
        if (
            isinstance(criterion, str)
            and criterion
            and criterion not in task.instruction
            and criterion in blob
        ):
            findings.append("success_criteria")
            break
    gold_outputs = extra.get("gold_outputs")
    if isinstance(gold_outputs, Mapping):
        gold_blob = json.dumps(gold_outputs, sort_keys=True)
        if gold_blob and gold_blob in blob:
            findings.append("gold_outputs")
    return findings


def _public_observation_fields(observation: Mapping[str, Any]) -> JsonDict:
    return {
        "available_tools": observation.get("available_tools"),
        "domain": observation.get("domain"),
        "history": [],
        "instruction": observation.get("instruction"),
        "max_turns": observation.get("max_turns"),
        "split": observation.get("split"),
        "task_id": observation.get("task_id"),
        "turn_index": observation.get("turn_index"),
        "visible_files": observation.get("visible_files"),
    }


def _contains_token(blob: str, token: str) -> bool:
    if not token:
        return False
    return re.search(rf"(?<![\w.]){re.escape(token)}(?![\w.])", blob) is not None


def anti_hack_flags(reference: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[str]:
    """Flag reward improvements that do not raise held-out task success.

    ``refusal_hack``: silent failures fell because the policy stopped answering,
    while success did not rise. ``reward_without_success``: the scalar rose
    without a success-rate rise. Neither flag is a substitute for the two
    reported metrics.
    """

    flags: list[str] = []
    ref_success = float(reference.get("task_success_rate", 0.0))
    cand_success = float(candidate.get("task_success_rate", 0.0))
    success_rose = cand_success > ref_success + 1e-9
    if (
        not success_rose
        and int(candidate.get("silent_failure_count", 0)) < int(reference.get("silent_failure_count", 0))
        and int(candidate.get("incomplete_count", 0)) > int(reference.get("incomplete_count", 0))
    ):
        flags.append("refusal_hack")
    if not success_rose and float(candidate.get("mean_reward", 0.0)) > float(reference.get("mean_reward", 0.0)) + 1e-9:
        flags.append("reward_without_success")
    return flags
