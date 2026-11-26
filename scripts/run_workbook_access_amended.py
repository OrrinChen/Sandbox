"""Record a pre-scoring alternate tier, retaining the original sealed Sol turns and bindings."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib.util
from pathlib import Path
import tempfile

import run_workbook_access as host
import workbook_model as engine

PARENT = host.STUDY / "formal"
DEFAULT_ROOT = host.STUDY / "available"
PARENT_SHA = "9adcb92d3aaa3d58777742927c817f6cf8aa6fa05106f6b73cf9a9c4a07ac1f6"
SOL, ORIGINAL_ASTRA, ALTERNATE = "gpt-6.2-sol", "gpt-6.2-astra", "gpt-6-astra"
MODELS = [SOL, ALTERNATE]
ARMS = ["fixed", "browse"]
WORKERS = 4
REASON = (
    "Registered before grading, after prolonged HTTP 429 rate limiting on gpt-6.2-astra. "
    "Carry forward all gpt-6.2-sol submissions with their original bindings. "
    "Collect both gpt-6-astra arms from scratch. All gpt-6.2-astra turns are excluded."
)


def checked_copy(src, dst, create):
    """Carry an artifact byte-for-byte, without rebinding the original registration."""
    if not dst.exists() and create:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dst.parent, delete=False) as temp:
            temp.write(src.read_bytes())
        Path(temp.name).replace(dst)
    if host.digest(dst) != host.digest(src):
        raise ValueError(f"Moved artifact differs from source: {dst.name}")


def bound(path, value, create):
    if create:
        host.seal(path, value)
    elif host.load(path) != value:
        raise ValueError(f"Archived binding differs: {path.name}")


def private_copy(module):
    spec = importlib.util.spec_from_file_location(
        "amended_" + module.__name__, module.__file__
    )
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


def alternate_host():
    # Only this instance can call the replacement tier. v1's process and its
    # modules, CLI flags, timeout, transport handling and prompt builder stay intact.
    alternate = private_copy(engine)
    alternate.MODELS = (ALTERNATE,)
    runner = private_copy(host)
    runner.ask = alternate.ask
    return runner


def capacity_receipts():
    rule_file = PARENT.parent / "capacity_rule.json"
    activation_file = PARENT.parent / "capacity_activation.json"
    rule, activation = host.load(rule_file), host.load(activation_file)
    receipt = activation["observed"]
    if not all(
        (
            rule["initial_registration_sha256"]
            == activation["original_registration_sha256"]
            == PARENT_SHA,
            activation["capacity_rule_sha256"] == host.digest(rule_file),
            rule["eligible_alternate"]
            == activation["active_professional_model"]
            == ALTERNATE,
            rule["same_budget_and_public_inputs"] is True,
            rule["observed_pre_score"]["formal_score_opened"] is False,
            activation["frozen_results_opened"] is False,
            datetime.fromisoformat(activation["time"])
            >= datetime.fromisoformat(rule["registered_at"]),
            activation["elapsed_seconds"] >= 480,
            receipt
            == {
                "sol_batches": 50,
                "sol_turns": 150,
                "astra_batches": 0,
                "astra_turns": 0,
            },
            not any((PARENT / "recordings" / ORIGINAL_ASTRA).rglob("*.json")),
            not any((PARENT / "turns" / ORIGINAL_ASTRA).rglob("*.json")),
        )
    ):
        raise ValueError(
            "Original capacity criterion or recorded cutoff does not match"
        )
    return {
        "capacity_rule_sha256": host.digest(rule_file),
        "capacity_activation_sha256": host.digest(activation_file),
    }


def registration(root, create=False):
    root = Path(root)
    if root.resolve() == PARENT.resolve() or PARENT.resolve() in root.resolve().parents:
        raise ValueError("Use a separate amendment output directory")
    if host.digest(PARENT / "registration.json") != PARENT_SHA:
        raise ValueError("Original workbook registration changed")
    capacity = capacity_receipts()
    cfg = host.registration(PARENT, replay=True)
    if (
        cfg["models"] != [SOL, ORIGINAL_ASTRA]
        or cfg["arms"] != ARMS
        or cfg["development_smoke"]
    ):
        raise ValueError("Unrecognized original study")
    book = PARENT / "engine.json"
    if create:
        import openpyxl

        if host.load(book) != {
            **engine.engine_info(),
            "openpyxl": openpyxl.__version__,
        }:
            raise ValueError("Runtime differs from original study")
    checked_copy(book, root / "engine.json", create)
    sol_files, original_rows = {}, []
    for group in cfg["groups"].items():
        batch, _ = group
        checked_copy(
            PARENT / "inputs" / (batch + ".json"),
            root / "inputs" / (batch + ".json"),
            create,
        )
        for arm in ARMS:
            # Recompute each of the three prompt bindings, tool results, candidate and
            # aggregate from original raw Sol turns using the unchanged v1 registration.
            original_rows.extend(host.experiment(PARENT, group, SOL, arm, False))
            group_path = host.record_path(PARENT, SOL, arm, batch)
            turn_paths = [
                PARENT / "turns" / SOL / arm / batch / (stage + ".json")
                for stage in host.NAMES
            ]
            for path in [group_path, *turn_paths]:
                sol_files[str(path.relative_to(PARENT))] = host.digest(path)
            checked_copy(group_path, root / group_path.relative_to(PARENT), create)
    if len(sol_files) != 200 or len(original_rows) != 200:
        raise ValueError(
            "All 150 original Sol turns and 50 batch summaries are required"
        )
    imported = root / "source_sol_lock.json"
    bound(
        imported,
        {
            "parent_registration_sha256": PARENT_SHA,
            "source": "../formal",
            "files_sha256": sol_files,
        },
        create,
    )
    amended = {
        **cfg,
        **capacity,
        "version": "workbook-access-alternate-tier-v1",
        "models": MODELS,
        "parent_registration_sha256": PARENT_SHA,
        "parent_root": "../formal",
        "reason": REASON,
        "workers_per_model": WORKERS,
        "copied_model": SOL,
        "new_model": ALTERNATE,
        "excluded_model": ORIGINAL_ASTRA,
        "source_sol_lock_sha256": host.digest(imported),
        "amendment_driver_sha256": host.digest(Path(__file__)),
        "model_override": "Only the isolated workbook_model.MODELS allowlist changes for new calls.",
        "wheel_sha256": host.load(host.OLD_DATA / "wheel_verification.json")[
            "wheel_sha256"
        ],
    }
    bound(root / "registration.json", amended, create)
    return amended, original_rows


def new_jobs(cfg):
    return [(group, arm) for group in cfg["groups"].items() for arm in ARMS]


def lock(root, cfg):
    value = host.lock_value(root, cfg)
    value["parent_registration_sha256"] = PARENT_SHA
    value["source_sol_lock_sha256"] = host.digest(root / "source_sol_lock.json")
    return value


def verified_records(root):
    root = Path(root)
    cfg, records = registration(root)
    bound(root / "prediction_lock.json", lock(root, cfg), False)
    for group, arm in new_jobs(cfg):
        records.extend(host.experiment(root, group, ALTERNATE, arm, False))
    expected = {(t, m, a) for t in cfg["tasks"] for m in MODELS for a in ARMS}
    seen = Counter((r["task_id"], r["model"], r["arm"]) for r in records)
    if len(expected) != 400 or seen != Counter(expected):
        raise ValueError("Incomplete or contaminated amended comparison")
    return records


def record(root, workers):
    root = Path(root)
    if workers != WORKERS:
        raise ValueError(f"Use the original {WORKERS} workers per collecting tier")
    cfg, _ = registration(root, create=True)
    runner = alternate_host()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(runner.experiment, root, g, ALTERNATE, a, True)
            for g, a in new_jobs(cfg)
        ]
        for f in futures:
            f.result()
    # Every newly collected group must replay before the global lock is created.
    for group, arm in new_jobs(cfg):
        host.experiment(root, group, ALTERNATE, arm, False)
    host.seal(root / "prediction_lock.json", lock(root, cfg))
    print(f"Verified {len(verified_records(root))} paired submissions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "verify"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    if args.action == "record":
        record(args.root, args.workers)
    else:
        print(f"Verified {len(verified_records(args.root))} paired submissions")
