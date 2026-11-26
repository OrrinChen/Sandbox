"""Run the registered efficient-tier fallback with the original, byte-identical Sol answers."""

import argparse
from datetime import datetime
from pathlib import Path

import run_workbook_access_amended as prior

host = prior.host
MID = prior.DEFAULT_ROOT
DEFAULT_ROOT = host.STUDY / "paired"
MID_SHA = "5f3cae21310af4df04a15fa97e18ccf2be7c157092b366f9f1e98b83291db985"
TERRA = "gpt-6.1-terra"


def capacity():
    rule_file = host.STUDY / "efficient_capacity_rule.json"
    activation_file = host.STUDY / "efficient_capacity_activation.json"
    rule, activation = host.load(rule_file), host.load(activation_file)
    partial = {
        str(p.relative_to(MID)): host.digest(p)
        for p in sorted((MID / "turns" / prior.ALTERNATE).rglob("*.json"))
    }
    if not all(
        (
            rule["predecessor_registration_sha256"]
            == MID_SHA
            == activation["predecessor_registration_sha256"],
            rule["eligible_alternate"] == TERRA == activation["active_second_model"],
            activation["capacity_rule_sha256"] == host.digest(rule_file),
            rule["score_opened"] is False
            and activation["frozen_results_opened"] is False,
            rule["sol_complete_batches"] == 50
            and rule["current_professional_batches"] == 0,
            activation["observed"]["sol_batches"] == 50
            and activation["observed"]["professional_batches"] == 0,
            activation["observed"]["professional_turns"] == len(partial),
            activation["elapsed_seconds"] >= 480,
            datetime.fromisoformat(activation["time"])
            >= datetime.fromisoformat(rule["registered_at"]),
            not any((MID / "recordings" / prior.ALTERNATE).rglob("*.json")),
        )
    ):
        raise ValueError("Efficient tier capacity switch is invalid")
    return {
        "efficient_capacity_rule_sha256": host.digest(rule_file),
        "efficient_capacity_activation_sha256": host.digest(activation_file),
        "excluded_intermediate_turns_sha256": partial,
    }


def registration(root, create=False):
    root = Path(root)
    if any(
        root.resolve() == p.resolve() or p.resolve() in root.resolve().parents
        for p in (MID, prior.PARENT)
    ):
        raise ValueError("Use a fresh efficient-tier directory")
    if host.digest(MID / "registration.json") != MID_SHA:
        raise ValueError("Professional-tier registration changed")
    evidence = capacity()
    # Check both old registrations, public inputs, and all original Sol raw turns.
    cfg, original_rows = prior.registration(MID)
    if create:
        import openpyxl

        if host.load(MID / "engine.json") != {
            **prior.engine.engine_info(),
            "openpyxl": openpyxl.__version__,
        }:
            raise ValueError("Model client or workbook reader version changed")
    files = [Path("engine.json"), Path("source_sol_lock.json")]
    for batch in cfg["groups"]:
        files.append(Path("inputs") / (batch + ".json"))
        files.extend(
            host.record_path(MID, prior.SOL, arm, batch).relative_to(MID)
            for arm in prior.ARMS
        )
    for name in files:
        prior.checked_copy(MID / name, root / name, create)
    cfg = {
        **cfg,
        **evidence,
        "version": "workbook-access-efficient-tier-v1",
        "models": [prior.SOL, TERRA],
        "efficient_tier": TERRA,
        "new_model": TERRA,
        "excluded_models": [prior.ORIGINAL_ASTRA, prior.ALTERNATE],
        "predecessor_registration_sha256": MID_SHA,
        "efficient_driver_sha256": host.digest(Path(__file__)),
        "reason": "Both professional-tier collectors reached their pre-scoring capacity rule. No answer from either enters the efficient-tier comparison.",
    }
    prior.bound(root / "registration.json", cfg, create)
    return cfg, original_rows


def driver():
    # Reuse the frozen collector, replay and composite lock with a private
    # model allowlist and the additional predecessor/activation checks above.
    module = prior.private_copy(prior)
    module.ALTERNATE = TERRA
    module.MODELS = [prior.SOL, TERRA]
    module.registration = registration
    return module


def verified_records(root):
    return driver().verified_records(Path(root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("record", "verify"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--workers", type=int, default=prior.WORKERS)
    args = parser.parse_args()
    if args.action == "record":
        driver().record(args.root, args.workers)
    else:
        print(f"Verified {len(verified_records(args.root))} paired submissions")
