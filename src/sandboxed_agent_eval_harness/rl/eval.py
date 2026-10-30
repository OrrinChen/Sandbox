"""Held-out evaluation: task success and silent-failure counts.

CPU policies (oracle, prompt template, mocked) run without a GPU. ``--policy hf``
loads a model and is not part of CI. This script does not invent model scores.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.rl.config import load_rl_config, load_split
from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.policies import MockedCategoricalPolicy, OraclePolicy, PromptTemplatePolicy
from sandboxed_agent_eval_harness.rl.reward import RewardWeights, anti_hack_flags
from sandboxed_agent_eval_harness.rl.rollout import Trajectory, rollout_task, summarize_trajectories
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec


def evaluate_policies(
    tasks: Sequence[TaskSpec],
    metadata: dict[str, JsonDict],
    weights: RewardWeights,
    *,
    policies: Sequence[str],
    mocked_policy: MockedCategoricalPolicy | None = None,
    evidence_label: str = "cpu_policy_eval",
    prompt_mode: str = "tool",
) -> JsonDict:
    if prompt_mode not in {"tool", "bare"}:
        raise ValueError("prompt_mode must be 'tool' or 'bare'")
    summaries = {}
    with SandboxToolEnv(tasks, task_metadata=metadata, reward_weights=weights, split_name="eval") as env:
        oracle = OraclePolicy(tasks)
        prompt_policy = PromptTemplatePolicy()
        mocked = mocked_policy or MockedCategoricalPolicy(seed=0)
        runners = {
            "oracle": oracle.act,
            "prompt_template": prompt_policy.act,
            "mocked": mocked.act,
        }
        for name in policies:
            if name == "hf":
                raise ValueError("use evaluate_hf for the hf policy")
            trajectories = [rollout_task(env, task, runners[name]) for task in tasks]
            summaries[name] = summarize_trajectories(trajectories, label=name)
    reference = summaries.get("prompt_template") or next(iter(summaries.values()))
    flags = {
        name: anti_hack_flags(reference, summary)
        for name, summary in summaries.items()
        if name != reference["label"]
    }
    return {
        "evidence_label": evidence_label,
        "model_post_training": "not yet run",
        "prompt_mode": prompt_mode,
        "run_count_per_policy": len(tasks),
        "policies": summaries,
        "anti_hack_flags": flags,
    }


def evaluate_hf(
    tasks: Sequence[TaskSpec],
    metadata: dict[str, JsonDict],
    weights: RewardWeights,
    *,
    model_name_or_path: str,
    prompt_mode: str,
    max_new_tokens: int,
    temperature: float,
) -> JsonDict:
    from sandboxed_agent_eval_harness.rl.hf import generate_hf_action

    trajectories: list[Trajectory] = []
    with SandboxToolEnv(tasks, task_metadata=metadata, reward_weights=weights, split_name="held_out") as env:
        for task in tasks:
            observation, _info = env.reset(task_id=task.task_id)
            terminated = False
            truncated = False
            reward = 0.0
            info: JsonDict = {}
            steps = 0
            while not terminated and not truncated:
                prompt = env.render_prompt(observation, mode=prompt_mode)
                completion = generate_hf_action(
                    model_name_or_path,
                    prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                )
                observation, reward, terminated, truncated, info = env.step(completion)
                steps += 1
            trajectories.append(
                Trajectory(
                    task_id=task.task_id,
                    reward=reward,
                    passed=bool(info.get("passed")),
                    silent_failure=bool(info.get("silent_failure")),
                    incomplete=bool(info.get("incomplete")),
                    logprob=0.0,
                    behavior_index=None,
                    steps=steps,
                    info=info,
                )
            )
    summary = summarize_trajectories(trajectories, label="hf")
    summary["evidence_label"] = "hf_model_eval"
    return {
        "evidence_label": "hf_model_eval",
        "model_post_training": "measured_this_run",
        "model": model_name_or_path,
        "prompt_mode": prompt_mode,
        "policies": {"hf": summary},
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate policies on the Agentic RL split.")
    parser.add_argument("--config", default="configs/agentic_rl.json")
    parser.add_argument("--split", choices=["train", "held_out"], default="held_out")
    parser.add_argument("--policy", action="append", dest="policies")
    parser.add_argument("--prompt-mode", choices=["tool", "bare"], default="tool")
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--max-tasks", type=int, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    config = load_rl_config(args.config)
    task_split, metadata = load_split(config)
    selected = task_split.held_out if args.split == "held_out" else task_split.train
    if args.max_tasks > 0:
        selected = selected[: args.max_tasks]
    weights = RewardWeights.from_dict(config.get("reward", {}))
    policies = args.policies or ["oracle", "prompt_template", "mocked"]
    if "hf" in policies:
        model = args.model_path or args.model_name or str(config["model_name"])
        if len(policies) != 1:
            print("hf eval is a separate model run; pass --policy hf alone")
            return 2
        try:
            report = evaluate_hf(
                selected,
                metadata,
                weights,
                model_name_or_path=model,
                prompt_mode=args.prompt_mode,
                max_new_tokens=int(config.get("max_new_tokens", 256)),
                temperature=0.0,
            )
        except Exception as exc:
            from sandboxed_agent_eval_harness.rl.hf import GPUDependencyError

            if isinstance(exc, GPUDependencyError):
                print(str(exc))
                return 2
            raise
    else:
        report = evaluate_policies(
            selected,
            metadata,
            weights,
            policies=policies,
            evidence_label="cpu_policy_eval",
            prompt_mode=args.prompt_mode,
        )
    report["split_name"] = args.split
    report["task_ids"] = [task.task_id for task in selected]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for name, summary in report["policies"].items():
        print(
            f"policy={name} runs={summary['run_count']} "
            f"task_success_rate={summary['task_success_rate']:.3f} "
            f"silent_failures={summary['silent_failure_count']} "
            f"evidence={report['evidence_label']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
