"""Roll out groups and apply a GRPO update.

``--backend mocked`` is the CPU smoke path. ``--backend hf`` is the multi-turn
GPU path. ``--backend trl`` is the single-completion TRL GRPOTrainer ablation.
``--backend sft`` is the optional supervised baseline. GPU backends refuse to
load weights without CUDA unless ``--dry-run`` is set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.rl.commands import (
    AGENTIC_RL_INSTALL,
    EVAL_BASE_COMMAND,
    EVAL_GRPO_COMMAND,
    EVAL_PROMPT_COMMAND,
    EVAL_SFT_COMMAND,
    HF_TRAIN_COMMAND,
    SFT_EXPORT_COMMAND,
    SFT_TRAIN_COMMAND,
    TRL_TRAIN_COMMAND,
)
from sandboxed_agent_eval_harness.rl.config import apply_smoke, load_rl_config, load_split
from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.grpo import grpo_loss, group_advantages
from sandboxed_agent_eval_harness.rl.policies import MockedCategoricalPolicy
from sandboxed_agent_eval_harness.rl.reward import RewardWeights
from sandboxed_agent_eval_harness.rl.rollout import rollout_task
from sandboxed_agent_eval_harness.schemas import JsonDict


def gpu_command(backend: str) -> str:
    commands = {
        "hf": HF_TRAIN_COMMAND,
        "trl": TRL_TRAIN_COMMAND,
        "sft": SFT_TRAIN_COMMAND,
    }
    try:
        return commands[backend]
    except KeyError as exc:
        raise ValueError(f"no GPU command for backend: {backend}") from exc


def train_mocked(config: JsonDict, output_dir: Path) -> JsonDict:
    task_split, metadata = load_split(config)
    weights = RewardWeights.from_dict(config.get("reward", {}))
    group_size = int(config["group_size"])
    steps = int(config.get("max_steps") or 1)
    tasks_per_step = int(config.get("tasks_per_step") or 1)
    policy = MockedCategoricalPolicy(seed=int(config.get("seed", 7)))
    step_reports = []
    env = SandboxToolEnv(
        task_split.train,
        task_metadata=metadata,
        reward_weights=weights,
        split_name="train",
    )
    try:
        for step_index in range(steps):
            batch = [
                task_split.train[(step_index + offset) % len(task_split.train)]
                for offset in range(tasks_per_step)
            ]
            for task in batch:
                group = [rollout_task(env, task, policy.act) for _ in range(group_size)]
                rewards = [item.reward for item in group]
                advantages = group_advantages(
                    rewards,
                    normalization=str(config.get("advantage_normalization", "std")),
                )
                indexes = [int(item.behavior_index if item.behavior_index is not None else 0) for item in group]
                logprobs = [item.logprob for item in group]
                ref_logprobs = [policy.reference_logprob(index) for index in indexes]
                loss = grpo_loss(
                    logprobs,
                    logprobs,
                    advantages,
                    ref_logprobs=ref_logprobs,
                    clip_eps=float(config.get("clip_eps", 0.2)),
                    beta=float(config.get("kl_beta", 0.0)),
                )
                policy.update(
                    indexes,
                    advantages,
                    learning_rate=float(config.get("learning_rate", 0.5)),
                    beta=float(config.get("kl_beta", 0.0)),
                )
                step_reports.append(
                    {
                        "step": step_index,
                        "task_id": task.task_id,
                        "rewards": rewards,
                        "advantages": advantages,
                        "loss": loss.to_dict(),
                        "logits": list(policy.logits),
                    }
                )
    finally:
        env.close()

    eval_tasks = int(config.get("eval_tasks") or 1)
    heldout_report = _smoke_heldout_eval(
        task_split,
        metadata,
        weights,
        policy,
        max_tasks=eval_tasks,
    )
    report: JsonDict = {
        "status": "cpu_smoke_completed",
        "evidence_label": "cpu_smoke_mocked_policy",
        "model_post_training": "not yet run",
        "backend": "mocked",
        "steps_completed": len(step_reports),
        "loss_finite": all(_finite(step["loss"]["total"]) for step in step_reports),
        "split": {
            "seed": task_split.seed,
            "train_families": task_split.train_families,
            "held_out_families": task_split.held_out_families,
            "train_task_count": len(task_split.train),
            "held_out_task_count": len(task_split.held_out),
        },
        "steps": step_reports,
        "held_out_eval": heldout_report,
        "gpu_command": HF_TRAIN_COMMAND,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def dry_run_report(backend: str, output_dir: Path) -> JsonDict:
    report: JsonDict = {
        "status": "not yet run",
        "evidence_label": "dry_run",
        "model_post_training": "not yet run",
        "backend": backend,
        "install": AGENTIC_RL_INSTALL,
        "command": gpu_command(backend),
        "related_commands": {
            "hf_train": HF_TRAIN_COMMAND,
            "trl_train": TRL_TRAIN_COMMAND,
            "sft_export": SFT_EXPORT_COMMAND,
            "sft_train": SFT_TRAIN_COMMAND,
            "eval_base": EVAL_BASE_COMMAND,
            "eval_prompt": EVAL_PROMPT_COMMAND,
            "eval_sft": EVAL_SFT_COMMAND,
            "eval_grpo": EVAL_GRPO_COMMAND,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "dry_run.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="GRPO training on the sandbox tool-use environment.")
    parser.add_argument("--config", default="configs/agentic_rl.json")
    parser.add_argument("--backend", choices=["mocked", "hf", "trl", "sft"], default="mocked")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/agentic_rl/run")
    parser.add_argument("--sft-data", default="artifacts/agentic_rl/sft_train.jsonl")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    if args.backend == "mocked":
        config = load_rl_config(args.config)
        if args.smoke:
            config = apply_smoke(config)
        elif int(config.get("max_steps") or 0) <= 0:
            config = dict(config)
            config["max_steps"] = 1
        report = train_mocked(config, output_dir)
        print(
            f"agentic_rl_smoke status={report['status']} steps={report['steps_completed']} "
            f"loss_finite={report['loss_finite']} model_post_training={report['model_post_training']}"
        )
        return 0

    if args.dry_run or args.smoke:
        report = dry_run_report(args.backend, output_dir)
        print(f"agentic_rl_dry_run backend={args.backend} status={report['status']}")
        print(report["command"])
        return 0

    config = load_rl_config(args.config)
    task_split, metadata = load_split(config)
    try:
        from sandboxed_agent_eval_harness.rl.hf import train_hf_multiturn, train_sft, train_trl_single_turn

        if args.backend == "hf":
            report = train_hf_multiturn(config, task_split.train, output_dir, task_metadata=metadata)
        elif args.backend == "trl":
            report = train_trl_single_turn(config, task_split.train, output_dir, task_metadata=metadata)
        else:
            report = train_sft(config, Path(args.sft_data), output_dir)
    except Exception as exc:
        from sandboxed_agent_eval_harness.rl.hf import GPUDependencyError

        if isinstance(exc, GPUDependencyError):
            print(str(exc))
            print(gpu_command(args.backend))
            return 2
        raise
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "train_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"agentic_rl_train backend={args.backend} status={report['status']}")
    return 0


def _smoke_heldout_eval(task_split, metadata, weights, trained_policy, *, max_tasks: int) -> JsonDict:
    from sandboxed_agent_eval_harness.rl.eval import evaluate_policies

    tasks = task_split.held_out[:max_tasks]
    return evaluate_policies(
        tasks,
        metadata,
        weights,
        policies=["oracle", "prompt_template", "mocked"],
        mocked_policy=trained_policy,
        evidence_label="cpu_smoke_heldout_subset",
    )


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and value == value and value not in (float("inf"), float("-inf"))


if __name__ == "__main__":
    raise SystemExit(main())
