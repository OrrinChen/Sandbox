"""Record a third workbook model against the frozen Sol/Terra inputs and budgets."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import run_workbook_access_efficient as paired

host = paired.host
shared = paired.prior
PARENT = paired.DEFAULT_ROOT
DEFAULT_ROOT = host.STUDY / "luna"
MODEL = "gpt-6-luna"
PARENT_REG = "f4cbe1cdf18fa0496c8064bc5cd6f8f563c4899d1a9d418ca1bbd2039a344c07"
PARENT_LOCK = "dda2bfaa9a144382d2879b459071dfe2461d9a149fc69013767cc84e71e6f9ee"


def registration(root, create=False):
    """Bind only the earlier registrations and public inputs used for collection."""
    root = Path(root)
    if any(
        root.resolve().is_relative_to(path.resolve())
        for path in (PARENT, paired.MID, shared.PARENT)
    ):
        raise ValueError("Use a separate Luna archive")
    for name, expected in (
        ("registration.json", PARENT_REG),
        ("prediction_lock.json", PARENT_LOCK),
    ):
        if host.digest(PARENT / name) != expected:
            raise ValueError(f"Parent archive changed: {name}")
    parent = host.load(PARENT / "registration.json")
    if (
        host.digest(host.PUBLIC) != parent["public_xlsx_zip_sha256"]
        or host.digest(host.STUDY / "protocol.json") != parent["protocol_sha256"]
        or host.digest(PARENT / "engine.json") != parent["engine_sha256"]
    ):
        raise ValueError("Public workbook, protocol or engine changed")
    for name, expected in parent["code_sha256"].items():
        if host.digest(Path(__file__).with_name(name)) != expected:
            raise ValueError(f"Frozen study implementation changed: {name}")
    if create:
        import openpyxl

        if host.load(PARENT / "engine.json") != {
            **shared.engine.engine_info(),
            "openpyxl": openpyxl.__version__,
        }:
            raise ValueError("Live model client or reader differs from frozen runtime")
    shared.checked_copy(PARENT / "engine.json", root / "engine.json", create)
    for batch, expected in parent["input_hashes"].items():
        name = Path("inputs") / (batch + ".json")
        if host.digest(PARENT / name) != expected:
            raise ValueError(f"Public observation changed: {batch}")
        shared.checked_copy(PARENT / name, root / name, create)
    cfg = {
        key: parent[key]
        for key in (
            "arms",
            "tasks",
            "groups",
            "input_hashes",
            "release_sha256",
            "wheel_sha256",
            "public_xlsx_zip_sha256",
            "protocol_sha256",
            "engine_sha256",
            "code_sha256",
            "archive_sha256",
        )
    }
    cfg.update(
        version="workbook-access-luna-addition-v1",
        models=[MODEL],
        parent_root="../paired",
        parent_registration_sha256=PARENT_REG,
        parent_prediction_lock_sha256=PARENT_LOCK,
        luna_driver_sha256=host.digest(Path(__file__)),
        workers_per_model=shared.WORKERS,
        scoring="Previous study scores were known when the third model was requested. "
        "Seal all 200 new submissions before scoring Luna. Reuse the original "
        "grading rule and both public and hidden input states. Replay every failure.",
    )
    shared.bound(root / "registration.json", cfg, create)
    return cfg


def collector():
    runner = shared.private_copy(host)
    engine = shared.private_copy(shared.engine)
    engine.MODELS = (MODEL,)
    runner.ask = engine.ask
    return runner


def record(root):
    root = Path(root)
    cfg = registration(root, create=True)
    runner = collector()
    with ThreadPoolExecutor(max_workers=shared.WORKERS) as pool:
        futures = [
            pool.submit(runner.experiment, root, group, model, arm, True)
            for group, model, arm in host.jobs(cfg)
        ]
        for future in futures:
            future.result()
    host.seal(root / "prediction_lock.json", host.lock_value(root, cfg))
    print("Sealed 200 Luna submissions", flush=True)


def verified_records(root):
    root = Path(root)
    cfg = registration(root)
    shared.bound(root / "prediction_lock.json", host.lock_value(root, cfg), False)
    return [
        row
        for group, model, arm in host.jobs(cfg)
        for row in host.experiment(root, group, model, arm, False)
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "verify"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    if args.action == "record":
        record(args.root)
    else:
        print(f"Verified {len(verified_records(args.root))} Luna submissions")
