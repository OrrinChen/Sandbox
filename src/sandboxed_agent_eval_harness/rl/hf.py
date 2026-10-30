"""GPU GRPO and SFT entrypoints.

These functions import torch, transformers, and TRL only when a GPU backend
is actually invoked. CI calls the dry-run path and does not download weights.
The multi-turn loop samples one action per environment step, executes the
fixture tool, and applies the same GRPO surrogate as ``grpo.grpo_loss`` to
action-token log-probabilities. Tool-result tokens are masked out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from sandboxed_agent_eval_harness.rl.actions import parse_action, parse_transcript
from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.grpo import group_advantages, scored_token_indices
from sandboxed_agent_eval_harness.schemas import TaskSpec


class GPUDependencyError(RuntimeError):
    """Raised when the optional agentic-rl stack is missing or no GPU is visible."""


def require_gpu_stack() -> None:
    missing = []
    for module_name in ("torch", "transformers", "peft", "trl", "datasets"):
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        raise GPUDependencyError(
            "GPU training dependencies are not installed "
            f"({', '.join(missing)}). Install with: pip install -e \".[agentic-rl]\""
        )
    torch = __import__("torch")
    if not torch.cuda.is_available():
        raise GPUDependencyError(
            "HF/TRL backends require a CUDA GPU. No weights were loaded. "
            "Re-run the same command on a GPU machine."
        )


def train_hf_multiturn(
    config: Mapping[str, Any],
    train_tasks: Sequence[TaskSpec],
    output_dir: Path,
    *,
    task_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Turn-by-turn GRPO. Not executed in CI."""

    require_gpu_stack()
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    output_dir.mkdir(parents=True, exist_ok=True)
    model_name = str(config["model_name"])
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.bfloat16)
    model = get_peft_model(
        model,
        LoraConfig(
            r=int(config.get("lora_rank", 16)),
            lora_alpha=int(config.get("lora_alpha", 32)),
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        ),
    )
    if config.get("gradient_checkpointing", True):
        model.gradient_checkpointing_enable()
    model.train()
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=float(config.get("learning_rate", 1e-6)),
    )
    env = SandboxToolEnv(train_tasks, task_metadata=task_metadata, split_name="train")
    group_size = int(config.get("group_size", 4))
    steps = _step_count(config, len(train_tasks))
    history: list[dict[str, Any]] = []
    try:
        for step_index in range(steps):
            task = train_tasks[step_index % len(train_tasks)]
            rollouts = [
                _sample_episode(
                    model,
                    tokenizer,
                    env,
                    task,
                    max_new_tokens=int(config.get("max_new_tokens", 256)),
                    temperature=float(config.get("temperature", 0.8)),
                )
                for _ in range(group_size)
            ]
            rewards = [float(item["reward"]) for item in rollouts]
            advantages = group_advantages(
                rewards,
                normalization=str(config.get("advantage_normalization", "std")),
            )
            optimizer.zero_grad(set_to_none=True)
            loss_value = _grpo_backward(
                model,
                rollouts,
                advantages,
                clip_eps=float(config.get("clip_eps", 0.2)),
                beta=float(config.get("kl_beta", 0.04)),
            )
            optimizer.step()
            history.append(
                {
                    "step": step_index,
                    "task_id": task.task_id,
                    "rewards": rewards,
                    "loss": loss_value,
                    "mean_reward": sum(rewards) / len(rewards),
                }
            )
    finally:
        env.close()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    return {
        "status": "completed",
        "backend": "hf",
        "evidence_label": "gpu_grpo_run",
        "model_name": model_name,
        "steps": history,
        "output_dir": str(output_dir),
    }


def train_trl_single_turn(
    config: Mapping[str, Any],
    train_tasks: Sequence[TaskSpec],
    output_dir: Path,
    *,
    task_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stock TRL GRPOTrainer. One completion is a full action transcript.

    This is the single-turn ablation. Tool results do not condition later
    tokens inside the completion. The multi-turn GPU path is ``train_hf_multiturn``.
    """

    require_gpu_stack()
    from datasets import Dataset
    from trl import GRPOConfig, GRPOTrainer

    output_dir.mkdir(parents=True, exist_ok=True)
    import threading

    env = SandboxToolEnv(train_tasks, task_metadata=task_metadata, split_name="train")
    reward_lock = threading.Lock()
    prompts = []
    task_ids = []
    for task in train_tasks:
        observation, _info = env.reset(task_id=task.task_id)
        prompts.append(env.render_prompt(observation, mode="tool"))
        task_ids.append(task.task_id)
    dataset = Dataset.from_dict({"prompt": prompts, "task_id": task_ids})

    def reward_func(completions: list[Any], task_id: list[str] | None = None, **kwargs: Any) -> list[float]:
        del kwargs
        if task_id is None:
            raise GPUDependencyError("TRL reward expects the task_id column. Set remove_unused_columns=False.")
        rewards = []
        with reward_lock:
            for completion, sample_task_id in zip(_completion_texts(completions), task_id):
                rewards.append(_reward_transcript(env, sample_task_id, completion))
        return rewards

    group_size = int(config.get("group_size", 4))
    trainer = GRPOTrainer(
        model=str(config["model_name"]),
        reward_funcs=reward_func,
        args=GRPOConfig(
            output_dir=str(output_dir),
            num_generations=group_size,
            per_device_train_batch_size=group_size,
            gradient_accumulation_steps=1,
            learning_rate=float(config.get("learning_rate", 1e-6)),
            max_completion_length=int(config.get("max_new_tokens", 256)),
            beta=float(config.get("kl_beta", 0.04)),
            num_train_epochs=int(config.get("epochs", 1)),
            logging_steps=1,
            remove_unused_columns=False,
            report_to=[],
        ),
        train_dataset=dataset,
    )
    try:
        trainer.train()
        trainer.save_model(str(output_dir))
    finally:
        env.close()
    return {
        "status": "completed",
        "backend": "trl",
        "evidence_label": "gpu_grpo_run",
        "model_name": str(config["model_name"]),
        "output_dir": str(output_dir),
    }


def train_sft(
    config: Mapping[str, Any],
    sft_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    require_gpu_stack()
    import json

    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    rows = []
    for line in sft_path.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            rows.append({"text": record["prompt"] + record["completion"]})
    if not rows:
        raise GPUDependencyError(f"SFT file is empty: {sft_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    trainer = SFTTrainer(
        model=str(config["model_name"]),
        args=SFTConfig(
            output_dir=str(output_dir),
            num_train_epochs=int(config.get("epochs", 1)),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            learning_rate=float(config.get("sft_learning_rate", 2e-5)),
            logging_steps=1,
            dataset_text_field="text",
            max_length=1024,
            report_to=[],
        ),
        train_dataset=Dataset.from_list(rows),
    )
    trainer.train()
    trainer.save_model(str(output_dir))
    return {
        "status": "completed",
        "backend": "sft",
        "evidence_label": "gpu_sft_run",
        "rows": len(rows),
        "output_dir": str(output_dir),
    }


def generate_hf_action(
    model_name_or_path: str,
    prompt: str,
    *,
    max_new_tokens: int,
    temperature: float,
) -> str:
    """One completion from a local or Hub model. Used by held-out eval."""

    require_gpu_stack()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
    model = AutoModelForCausalLM.from_pretrained(model_name_or_path, torch_dtype=torch.bfloat16)
    model.eval()
    device = torch.device("cuda")
    model.to(device)
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    generate_kwargs: dict[str, Any] = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.eos_token_id,
    }
    if temperature > 0:
        generate_kwargs["do_sample"] = True
        generate_kwargs["temperature"] = temperature
    else:
        generate_kwargs["do_sample"] = False
    with torch.no_grad():
        generated = model.generate(**inputs, **generate_kwargs)
    new_tokens = generated[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def _sample_episode(
    model: Any,
    tokenizer: Any,
    env: SandboxToolEnv,
    task: TaskSpec,
    *,
    max_new_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    import torch

    observation, _info = env.reset(task_id=task.task_id)
    segments: list[dict[str, Any]] = []
    terminated = False
    truncated = False
    reward = 0.0
    info: dict[str, Any] = {}
    while not terminated and not truncated:
        prompt = env.render_prompt(observation, mode="tool")
        action_text, prompt_ids, full_ids = _generate_action(
            model, tokenizer, prompt, max_new_tokens=max_new_tokens, temperature=temperature
        )
        action_mask = [0] * len(prompt_ids) + [1] * max(0, len(full_ids) - len(prompt_ids))
        if len(action_mask) < len(full_ids):
            action_mask.extend([1] * (len(full_ids) - len(action_mask)))
        action_mask = action_mask[: len(full_ids)]
        segments.append({"input_ids": full_ids, "action_mask": action_mask, "prompt_length": len(prompt_ids)})
        parsed = parse_action(action_text)
        observation, reward, terminated, truncated, info = env.step(parsed if parsed.type != "invalid" else action_text)
    return {
        "reward": reward,
        "passed": bool(info.get("passed")),
        "segments": segments,
        "task_id": task.task_id,
    }


def _generate_action(
    model: Any,
    tokenizer: Any,
    prompt: str,
    *,
    max_new_tokens: int,
    temperature: float,
) -> tuple[str, list[int], list[int]]:
    import torch

    device = next(model.parameters()).device
    prompt_ids = tokenizer(prompt, add_special_tokens=True)["input_ids"]
    input_ids = torch.tensor([prompt_ids], device=device)
    was_training = model.training
    model.eval()
    with torch.no_grad():
        generated = model.generate(
            input_ids=input_ids,
            do_sample=temperature > 0,
            temperature=max(temperature, 1e-5),
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
        )
    if was_training:
        model.train()
    full_ids = [int(token) for token in generated[0].tolist()]
    action_text = tokenizer.decode(generated[0][len(prompt_ids) :], skip_special_tokens=True)
    return action_text, list(prompt_ids), full_ids


def _grpo_backward(
    model: Any,
    rollouts: Sequence[Mapping[str, Any]],
    advantages: Sequence[float],
    *,
    clip_eps: float,
    beta: float,
) -> float:
    import torch
    import torch.nn.functional as F

    losses = []
    for rollout, advantage in zip(rollouts, advantages):
        advantage_tensor = torch.tensor(float(advantage), device=next(model.parameters()).device)
        for segment in rollout["segments"]:
            input_ids = torch.tensor([segment["input_ids"]], device=advantage_tensor.device)
            if input_ids.shape[1] < 2:
                continue
            outputs = model(input_ids=input_ids)
            logprobs = F.log_softmax(outputs.logits[:, :-1, :], dim=-1)
            target = input_ids[:, 1:]
            token_logprobs = logprobs.gather(2, target.unsqueeze(-1)).squeeze(-1)
            scored = scored_token_indices(segment["action_mask"])
            if not scored:
                continue
            # token t's logprob lives at index t-1
            positions = [index - 1 for index in scored]
            action_logprob = token_logprobs[0, positions].sum()
            with model.disable_adapter():
                with torch.no_grad():
                    reference_outputs = model(input_ids=input_ids)
                    reference_logprobs = F.log_softmax(reference_outputs.logits[:, :-1, :], dim=-1)
                    reference_token_logprobs = reference_logprobs.gather(2, target.unsqueeze(-1)).squeeze(-1)
                    reference_action_logprob = reference_token_logprobs[0, positions].sum()
            # On-policy ratio is 1 at the sampling policy. The sampled action is
            # treated as the old policy, so the surrogate gradient is advantage
            # times the current action log-probability, clipped in log space.
            detached = action_logprob.detach()
            log_ratio = torch.clamp(action_logprob - detached, -20.0, 20.0)
            ratio = torch.exp(log_ratio)
            clipped_ratio = torch.clamp(ratio, 1.0 - clip_eps, 1.0 + clip_eps)
            surrogate = -torch.min(ratio * advantage_tensor, clipped_ratio * advantage_tensor)
            delta = torch.clamp(reference_action_logprob - action_logprob, -20.0, 20.0)
            kl = torch.exp(delta) - delta - 1.0
            losses.append(surrogate + beta * kl)
    if not losses:
        return 0.0
    loss = torch.stack(losses).mean()
    loss.backward()
    return float(loss.detach().cpu())


def _reward_transcript(env: SandboxToolEnv, task_id: str, completion: str) -> float:
    env.reset(task_id=task_id)
    actions = parse_transcript(completion)
    info: dict[str, Any] = {}
    terminated = False
    truncated = False
    reward = 0.0
    for action in actions:
        _observation, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            return reward
    _observation, reward, _terminated, _truncated, info = env.force_terminate()
    return reward


def _completion_texts(completions: Sequence[Any]) -> list[str]:
    texts = []
    for completion in completions:
        if isinstance(completion, str):
            texts.append(completion)
        elif isinstance(completion, list) and completion and isinstance(completion[0], Mapping):
            texts.append(str(completion[-1].get("content", "")))
        else:
            texts.append(str(completion))
    return texts


def _step_count(config: Mapping[str, Any], task_count: int) -> int:
    configured = int(config.get("max_steps") or 0)
    if configured > 0:
        return configured
    return max(1, int(config.get("epochs", 1)) * task_count)
