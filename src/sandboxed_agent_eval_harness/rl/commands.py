"""Canonical shell commands for GPU runs that have not been executed."""

HF_TRAIN_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.train "
    "--config configs/agentic_rl.json --backend hf "
    "--output-dir artifacts/agentic_rl/qwen25_1p5b_grpo"
)
TRL_TRAIN_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.train "
    "--config configs/agentic_rl.json --backend trl "
    "--output-dir artifacts/agentic_rl/qwen25_1p5b_grpo_trl"
)
SFT_EXPORT_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.sft_export "
    "--config configs/agentic_rl.json "
    "--output artifacts/agentic_rl/sft_train.jsonl"
)
SFT_TRAIN_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.train "
    "--config configs/agentic_rl.json --backend sft "
    "--sft-data artifacts/agentic_rl/sft_train.jsonl "
    "--output-dir artifacts/agentic_rl/qwen25_1p5b_sft"
)
EVAL_BASE_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.eval "
    "--config configs/agentic_rl.json --split held_out --policy hf "
    "--prompt-mode bare --model-name Qwen/Qwen2.5-1.5B-Instruct "
    "--output artifacts/agentic_rl/heldout_base.json"
)
EVAL_PROMPT_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.eval "
    "--config configs/agentic_rl.json --split held_out --policy hf "
    "--prompt-mode tool --model-name Qwen/Qwen2.5-1.5B-Instruct "
    "--output artifacts/agentic_rl/heldout_prompt.json"
)
EVAL_GRPO_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.eval "
    "--config configs/agentic_rl.json --split held_out --policy hf "
    "--prompt-mode tool --model-path artifacts/agentic_rl/qwen25_1p5b_grpo "
    "--output artifacts/agentic_rl/heldout_grpo.json"
)
EVAL_SFT_COMMAND = (
    "python -m sandboxed_agent_eval_harness.rl.eval "
    "--config configs/agentic_rl.json --split held_out --policy hf "
    "--prompt-mode tool --model-path artifacts/agentic_rl/qwen25_1p5b_sft "
    "--output artifacts/agentic_rl/heldout_sft.json"
)
AGENTIC_RL_INSTALL = 'pip install -e ".[agentic-rl]"'
