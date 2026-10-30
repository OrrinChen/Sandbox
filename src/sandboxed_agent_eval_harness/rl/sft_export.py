"""Export train-split oracle trajectories as SFT text. Does not train."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.rl.actions import render_action
from sandboxed_agent_eval_harness.rl.config import load_rl_config, load_split
from sandboxed_agent_eval_harness.rl.env import SandboxToolEnv
from sandboxed_agent_eval_harness.rl.policies import OraclePolicy
from sandboxed_agent_eval_harness.rl.split import task_family


def export_sft_jsonl(
    config_path: Path | str,
    output_path: Path | str,
    *,
    max_tasks: int | None = None,
) -> dict[str, object]:
    config = load_rl_config(config_path)
    task_split, metadata = load_split(config)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    selected = task_split.train if max_tasks is None else task_split.train[:max_tasks]
    policy = OraclePolicy(selected)
    rows = 0
    with SandboxToolEnv(selected, task_metadata=metadata, split_name="train") as env:
        with output.open("w") as handle:
            for task in selected:
                observation, _info = env.reset(task_id=task.task_id)
                terminated = False
                truncated = False
                while not terminated and not truncated:
                    decision = policy.act(observation)
                    if not isinstance(decision.action, dict):
                        raise RuntimeError("oracle actions are structured objects")
                    record = {
                        "task_id": task.task_id,
                        "family": task_family(task.task_id),
                        "split": "train",
                        "prompt": env.render_prompt(observation, mode="tool"),
                        "completion": render_action(decision.action),
                    }
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
                    rows += 1
                    observation, _reward, terminated, truncated, _info = env.step(decision.action)
    return {
        "status": "exported",
        "rows": rows,
        "train_tasks": len(task_split.train),
        "held_out_tasks_excluded": len(task_split.held_out),
        "output": str(output),
        "trained": False,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export train-split oracle SFT rows. Does not train a model.")
    parser.add_argument("--config", default="configs/agentic_rl.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = export_sft_jsonl(args.config, args.output)
    print(
        f"sft_export rows={report['rows']} train_tasks={report['train_tasks']} "
        f"held_out_excluded={report['held_out_tasks_excluded']} trained=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
