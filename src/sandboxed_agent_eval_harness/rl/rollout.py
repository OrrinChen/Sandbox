"""Multi-turn rollouts against ``SandboxToolEnv``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.policies import PolicyDecision
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec


PolicyFn = Callable[[Mapping[str, Any]], PolicyDecision]


@dataclass(frozen=True)
class Trajectory:
    task_id: str
    reward: float
    passed: bool
    silent_failure: bool
    incomplete: bool
    logprob: float
    behavior_index: int | None
    steps: int
    info: JsonDict

    def to_dict(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "reward": self.reward,
            "passed": self.passed,
            "silent_failure": self.silent_failure,
            "incomplete": self.incomplete,
            "logprob": self.logprob,
            "behavior_index": self.behavior_index,
            "steps": self.steps,
        }


def rollout_task(env: SandboxToolEnv, task: TaskSpec, policy: PolicyFn) -> Trajectory:
    observation, _info = env.reset(task_id=task.task_id)
    logprob = 0.0
    behavior_index = None
    steps = 0
    info: JsonDict = {}
    terminated = False
    truncated = False
    reward = 0.0
    while not terminated and not truncated:
        decision = policy(observation)
        logprob += decision.logprob
        if decision.behavior_index is not None:
            behavior_index = decision.behavior_index
        observation, reward, terminated, truncated, info = env.step(decision.action)
        steps += 1
        if steps > task.max_turns + 1:
            raise RuntimeError(f"rollout exceeded the turn limit for {task.task_id}")
    return Trajectory(
        task_id=task.task_id,
        reward=reward,
        passed=bool(info.get("passed")),
        silent_failure=bool(info.get("silent_failure")),
        incomplete=bool(info.get("incomplete")),
        logprob=logprob,
        behavior_index=behavior_index,
        steps=steps,
        info=info,
    )


def summarize_trajectories(trajectories: Sequence[Trajectory], *, label: str) -> JsonDict:
    count = len(trajectories)
    if count == 0:
        return {
            "label": label,
            "run_count": 0,
            "task_success_count": 0,
            "task_success_rate": 0.0,
            "silent_failure_count": 0,
            "incomplete_count": 0,
            "mean_reward": 0.0,
        }
    successes = sum(1 for item in trajectories if item.passed)
    silent = sum(1 for item in trajectories if item.silent_failure)
    incomplete = sum(1 for item in trajectories if item.incomplete)
    return {
        "label": label,
        "run_count": count,
        "task_success_count": successes,
        "task_success_rate": successes / count,
        "silent_failure_count": silent,
        "incomplete_count": incomplete,
        "mean_reward": sum(item.reward for item in trajectories) / count,
        "evidence_label": "cpu_policy_rollout",
    }
