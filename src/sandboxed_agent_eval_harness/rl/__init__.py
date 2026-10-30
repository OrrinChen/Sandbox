"""Agentic RL environment, reward, and GRPO training loop.

The recorded harness study is unchanged. This package turns fixture-backed
tasks and deterministic validators into a multi-turn tool-use environment.
GPU post-training is implemented and not yet run.
"""

from sandboxed_agent_eval_harness.rl.commands import (
    EVAL_BASE_COMMAND,
    EVAL_GRPO_COMMAND,
    HF_TRAIN_COMMAND,
    SFT_EXPORT_COMMAND,
    SFT_TRAIN_COMMAND,
    TRL_TRAIN_COMMAND,
)
from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.reward import RewardWeights, compute_reward

__all__ = [
    "EVAL_BASE_COMMAND",
    "EVAL_GRPO_COMMAND",
    "HF_TRAIN_COMMAND",
    "RewardWeights",
    "SFT_EXPORT_COMMAND",
    "SFT_TRAIN_COMMAND",
    "SandboxToolEnv",
    "TRL_TRAIN_COMMAND",
    "compute_reward",
]
