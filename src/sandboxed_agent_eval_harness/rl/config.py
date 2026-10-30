"""Load the Agentic RL JSON config and the benchmark split it names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from sandboxed_agent_eval_harness.rl.reward import RewardWeights
from sandboxed_agent_eval_harness.rl.split import TaskSplit, split_benchmark
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite, benchmark_task_suite_path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "agentic_rl.json"


def load_rl_config(path: Path | str | None = None) -> JsonDict:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    payload = json.loads(config_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("agentic RL config must be a JSON object")
    if payload.get("suite") != "benchmark":
        raise ValueError("agentic RL config suite must be 'benchmark'")
    if int(payload.get("group_size", 0)) < 2:
        raise ValueError("group_size must be at least 2")
    RewardWeights.from_dict(payload.get("reward", {}))
    smoke = payload.get("smoke", {})
    if smoke and int(smoke.get("group_size", 2)) < 2:
        raise ValueError("smoke.group_size must be at least 2")
    return payload


def load_split(config: Mapping[str, Any]) -> tuple[TaskSplit, dict[str, JsonDict]]:
    suite = benchmark_task_suite()
    raw_tasks = json.loads(benchmark_task_suite_path().read_text())["tasks"]
    metadata = {task_id: dict(values) for task_id, values in suite.task_metadata.items()}
    for raw_task in raw_tasks:
        task_metadata = metadata[raw_task["task_id"]]
        task_metadata["success_criteria"] = list(raw_task.get("success_criteria", []))
    task_split = split_benchmark(
        held_out_fraction=float(config.get("held_out_fraction", 0.25)),
        seed=int(config.get("seed", 7)),
    )
    return task_split, metadata


def apply_smoke(config: Mapping[str, Any]) -> JsonDict:
    resolved = dict(config)
    smoke = dict(config.get("smoke", {}))
    for key, value in smoke.items():
        if key == "reward":
            continue
        resolved[key] = value
    resolved["smoke_run"] = True
    resolved["reward"] = dict(config.get("reward", {}))
    return resolved
