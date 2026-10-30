"""CPU tests for the Agentic RL environment, reward, split, and smoke trainer."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from sandboxed_agent_eval_harness.rl.actions import parse_action, parse_transcript, render_action
from sandboxed_agent_eval_harness.rl.commands import HF_TRAIN_COMMAND
from sandboxed_agent_eval_harness.rl.config import load_rl_config, load_split
from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.grpo import grpo_loss, group_advantages, scored_token_indices
from sandboxed_agent_eval_harness.rl.policies import MockedCategoricalPolicy, OraclePolicy
from sandboxed_agent_eval_harness.rl.reward import RewardWeights, anti_hack_flags, compute_reward, oracle_leak_findings
from sandboxed_agent_eval_harness.rl.rollout import rollout_task
from sandboxed_agent_eval_harness.rl.sft_export import export_sft_jsonl
from sandboxed_agent_eval_harness.rl.split import task_family
from sandboxed_agent_eval_harness.rl.train import main as train_main
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite, default_task_suite


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "agentic_rl.json"


def test_action_protocol_round_trips_and_rejects_ambiguous_text():
    tool = {"type": "tool_call", "name": "financial_statement.lookup", "arguments": {"ticker": "AAPL"}}
    finish = {"type": "finish", "final_answer": "revenue=1 [src]", "reported_metrics": {"revenue": 1}}

    assert parse_action(render_action(tool)).name == "financial_statement.lookup"
    assert parse_action(render_action(finish)).reported_metrics == {"revenue": 1}
    assert parse_action("hello").type == "invalid"
    assert parse_action(render_action(tool) + render_action(finish)).type == "invalid"
    transcript = parse_transcript(render_action(tool) + "\n" + render_action(finish))
    assert [action.type for action in transcript] == ["tool_call", "finish"]
    assert parse_transcript(render_action(finish) + render_action(tool))[0].type == "invalid"


def test_success_reward_dominates_silent_failure_and_format_errors():
    weights = RewardWeights()
    success = compute_reward(passed=True, final_answer_present=True, format_errors=0, invalid_tool_calls=0, weights=weights)
    silent = compute_reward(passed=False, final_answer_present=True, format_errors=0, invalid_tool_calls=0, weights=weights)
    incomplete = compute_reward(passed=False, final_answer_present=False, format_errors=0, invalid_tool_calls=0, weights=weights)
    messy_success = compute_reward(
        passed=True, final_answer_present=True, format_errors=20, invalid_tool_calls=20, weights=weights
    )
    format_only = compute_reward(passed=False, final_answer_present=False, format_errors=0, invalid_tool_calls=0, weights=weights)

    assert success.total == 1.0
    assert success.silent_failure == 0.0
    assert silent.silent_failure == 1.0
    assert silent.total <= 0.0
    assert incomplete.total <= 0.0
    assert messy_success.total >= 0.05
    assert messy_success.total > silent.total
    assert format_only.total <= 0.0
    assert success.total > silent.total


def test_anti_hack_flags_refusal_and_reward_without_success():
    reference = {
        "task_success_rate": 0.0,
        "silent_failure_count": 4,
        "incomplete_count": 0,
        "mean_reward": -0.2,
    }
    refusal = {
        "task_success_rate": 0.0,
        "silent_failure_count": 1,
        "incomplete_count": 3,
        "mean_reward": -0.05,
    }
    real_gain = {
        "task_success_rate": 0.5,
        "silent_failure_count": 1,
        "incomplete_count": 0,
        "mean_reward": 0.4,
    }

    assert "refusal_hack" in anti_hack_flags(reference, refusal)
    assert "reward_without_success" in anti_hack_flags(reference, refusal)
    assert anti_hack_flags(reference, real_gain) == []


def test_grpo_advantages_are_centered_and_clip_matches_a_hand_example():
    advantages = group_advantages([1.0, 1.0, 1.0, 1.0])
    assert advantages == [0.0, 0.0, 0.0, 0.0]
    centered = group_advantages([0.0, 2.0], normalization="mean")
    assert centered == [-1.0, 1.0]

    loss = grpo_loss([math.log(2.0), 0.0], [0.0, 0.0], [1.0, -1.0], clip_eps=0.2, beta=0.0)
    assert math.isclose(loss.policy_loss, -0.1, abs_tol=1e-9)
    identical = grpo_loss([0.0, 0.0], [0.0, 0.0], [1.0, -1.0], ref_logprobs=[0.0, 0.0], beta=0.04)
    assert identical.policy_loss == 0.0
    assert identical.kl == 0.0
    shifted = grpo_loss([0.0], [0.0], [0.0], ref_logprobs=[-1.0], beta=1.0)
    assert shifted.kl > 0.0
    assert scored_token_indices([0, 0, 0, 1, 1, 0]) == [3, 4]


def test_benchmark_split_keeps_clone_families_together():
    config = load_rl_config(CONFIG)
    task_split, _metadata = load_split(config)

    assert task_split.seed == 7
    assert set(task_split.train_families).isdisjoint(task_split.held_out_families)
    assert len(task_split.train_families) + len(task_split.held_out_families) == 11
    assert task_split.held_out_families == [
        "coding-discount-total-fix",
        "data-inventory-stockout-report",
        "optimization-newsvendor-order",
    ]
    assert len(task_split.train) == 36
    assert len(task_split.held_out) == 28
    train_ids = {task.task_id for task in task_split.train}
    held_ids = {task.task_id for task in task_split.held_out}
    assert train_ids.isdisjoint(held_ids)
    assert len(train_ids) + len(held_ids) == 64
    families: dict[str, str] = {}
    for task in task_split.train + task_split.held_out:
        family = task_family(task.task_id)
        side = "held_out" if family in task_split.held_out_families else "train"
        assert families.setdefault(family, side) == side
    assert task_family("finance-aapl-revenue-benchmark-01") == task_family("finance-aapl-revenue-benchmark-06")
    assert "finance-aapl-revenue-2023" not in train_ids | held_ids


def test_initial_observations_do_not_contain_oracle_fields():
    config = load_rl_config(CONFIG)
    task_split, metadata = load_split(config)
    tasks = task_split.train + task_split.held_out
    with SandboxToolEnv(tasks, task_metadata=metadata, split_name="audit") as env:
        for task in tasks:
            observation, info = env.reset(task_id=task.task_id)
            assert oracle_leak_findings(observation, task, metadata[task.task_id]) == []
            assert "hidden_expected_state" not in observation
            assert info["task_id"] == task.task_id
            prompt = env.render_prompt(observation, mode="tool")
            for citation in task.hidden_expected_state.get("citations", []):
                assert citation not in prompt


def test_oracle_passes_finance_task_and_answer_without_tools_is_a_silent_failure():
    suite = default_task_suite()
    task = next(item for item in suite.tasks if item.task_id == "finance-aapl-revenue-2023")
    coding = next(item for item in suite.tasks if item.task_id == "coding-discount-total-fix")
    with SandboxToolEnv([coding], task_metadata=suite.task_metadata, split_name="unit") as coding_env:
        coding_trajectory = rollout_task(coding_env, coding, OraclePolicy([coding]).act)
    assert coding_trajectory.passed is True
    assert coding_trajectory.reward == 1.0
    with SandboxToolEnv([task], task_metadata=suite.task_metadata, split_name="unit") as env:
        trajectory = rollout_task(env, task, OraclePolicy([task]).act)
        observation, _reset_info = env.reset(task_id=task.task_id)
        _observation, silent_reward, terminated, truncated, info = env.step(
            {
                "type": "finish",
                "final_answer": "revenue_usd_millions=1 [unsupported-source]",
                "reported_metrics": {"revenue_usd_millions": 1},
            }
        )

    assert trajectory.passed is True
    assert trajectory.silent_failure is False
    assert trajectory.reward == 1.0
    assert "383285" not in json.dumps(observation)
    assert terminated is True
    assert truncated is False
    assert info["passed"] is False
    assert info["silent_failure"] is True
    assert silent_reward < trajectory.reward
    assert silent_reward <= 0.0


def test_mocked_policy_update_increases_the_higher_reward_behavior():
    policy = MockedCategoricalPolicy(seed=0, logits=[0.0, 0.0, 0.0])
    before = policy.logits[0]
    policy.update([0, 1], [1.0, -1.0], learning_rate=0.5, beta=0.0)
    assert policy.logits[0] > before
    assert policy.logits[1] < 0.0


def test_cpu_smoke_and_gpu_dry_run(tmp_path):
    smoke_dir = tmp_path / "smoke"
    assert train_main(["--config", str(CONFIG), "--backend", "mocked", "--smoke", "--output-dir", str(smoke_dir)]) == 0
    report = json.loads((smoke_dir / "report.json").read_text())
    assert report["status"] == "cpu_smoke_completed"
    assert report["evidence_label"] == "cpu_smoke_mocked_policy"
    assert report["model_post_training"] == "not yet run"
    assert report["steps_completed"] == 2
    assert report["loss_finite"] is True
    assert report["gpu_command"] == HF_TRAIN_COMMAND
    assert report["held_out_eval"]["model_post_training"] == "not yet run"
    for step in report["steps"]:
        assert abs(sum(step["advantages"])) < 1e-6

    dry_dir = tmp_path / "dry"
    assert train_main(["--config", str(CONFIG), "--backend", "hf", "--dry-run", "--output-dir", str(dry_dir)]) == 0
    dry = json.loads((dry_dir / "dry_run.json").read_text())
    assert dry["status"] == "not yet run"
    assert dry["command"] == HF_TRAIN_COMMAND


def test_sft_export_uses_train_split_only(tmp_path):
    output = tmp_path / "sft.jsonl"
    report = export_sft_jsonl(CONFIG, output, max_tasks=1)
    assert report["trained"] is False
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    task_split, _metadata = load_split(load_rl_config(CONFIG))
    train_ids = {task.task_id for task in task_split.train}
    held_ids = {task.task_id for task in task_split.held_out}
    assert rows
    assert {row["task_id"] for row in rows} <= train_ids
    assert {row["task_id"] for row in rows}.isdisjoint(held_ids)
    assert rows[0]["split"] == "train"


def test_readme_and_design_keep_the_gpu_command_and_empty_result_marker():
    readme = (ROOT / "README.md").read_text()
    design = (ROOT / "docs" / "agentic_rl_design.md").read_text()
    for text in (readme, design):
        assert HF_TRAIN_COMMAND in text
        assert "not yet run" in text
    for family in (
        "coding-discount-total-fix",
        "data-inventory-stockout-report",
        "optimization-newsvendor-order",
    ):
        assert family in design
    assert "offline recorded" in readme
    assert "fixture-backed" in readme


def test_tracked_text_has_no_local_absolute_user_paths_or_agent_working_files():
    for name in ("AGENTS.md", "TASK_MEMORY.md", "RUNBOOK.md"):
        assert not (ROOT / name).exists()
    patterns = (
        re.compile(r"/Users/[A-Za-z0-9_]"),
        re.compile(r"[A-Za-z]:/Users/[A-Za-z0-9_]"),
        re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9_]"),
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", "artifacts", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt"}:
            continue
        text = path.read_text(errors="ignore")
        for pattern in patterns:
            assert pattern.search(text) is None, f"{path} contains a local user path"


def test_benchmark_suite_still_has_64_tasks():
    assert len(benchmark_task_suite().tasks) == 64
