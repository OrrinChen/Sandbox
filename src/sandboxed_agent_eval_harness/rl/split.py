"""Family-level train/held-out split for the 64-task benchmark.

Benchmark rows are near-duplicate clones that share gold answers. Splitting by
row would leak. The initial suite is the template those clones were built from,
so it is not a held-out set. The trading suite is a separate domain and is not
mixed into this split.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import re

from sandboxed_agent_eval_harness.schemas import TaskSpec
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite


_CLONE_SUFFIX = re.compile(r"-\d{2}$")


@dataclass(frozen=True)
class TaskSplit:
    seed: int
    held_out_fraction: float
    train: list[TaskSpec]
    held_out: list[TaskSpec]
    train_families: list[str]
    held_out_families: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "held_out_fraction": self.held_out_fraction,
            "train_task_ids": [task.task_id for task in self.train],
            "held_out_task_ids": [task.task_id for task in self.held_out],
            "train_families": list(self.train_families),
            "held_out_families": list(self.held_out_families),
            "excluded_suites": ["initial-fixture-suite", "trading-fixture-suite"],
            "leakage_control": "family",
        }


def task_family(task_id: str) -> str:
    """Canonical family id. Clones that differ only by ``-benchmark`` and ``-NN`` match."""

    without_benchmark = task_id.replace("-benchmark", "")
    return _CLONE_SUFFIX.sub("", without_benchmark)


def split_tasks(
    tasks: list[TaskSpec],
    *,
    held_out_fraction: float = 0.25,
    seed: int = 7,
) -> TaskSplit:
    if not tasks:
        raise ValueError("split requires at least one task")
    if not 0 < held_out_fraction < 1:
        raise ValueError("held_out_fraction must be between 0 and 1")
    families = sorted({task_family(task.task_id) for task in tasks})
    if len(families) < 2:
        raise ValueError("split requires at least two task families")
    order = list(families)
    random.Random(seed).shuffle(order)
    held_count = int(round(len(families) * held_out_fraction))
    held_count = min(max(held_count, 1), len(families) - 1)
    held_families = set(order[:held_count])
    train: list[TaskSpec] = []
    held_out: list[TaskSpec] = []
    for task in sorted(tasks, key=lambda item: item.task_id):
        if task_family(task.task_id) in held_families:
            held_out.append(task)
        else:
            train.append(task)
    return TaskSplit(
        seed=seed,
        held_out_fraction=held_out_fraction,
        train=train,
        held_out=held_out,
        train_families=sorted(set(families) - held_families),
        held_out_families=sorted(held_families),
    )


def split_benchmark(held_out_fraction: float = 0.25, seed: int = 7) -> TaskSplit:
    return split_tasks(
        list(benchmark_task_suite().tasks),
        held_out_fraction=held_out_fraction,
        seed=seed,
    )
