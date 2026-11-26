"""Compare two complete MiniLM runs with the immutable historical 65-claim results."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

ARCHIVE = (
    Path(__file__).resolve().parents[1]
    / "experiments/hard_benchmark/hard_benchmark.json"
)
MODELS = {
    "bm25",
    "bm25_metadata_rerank",
    "dense_lsa",
    "dense_lsa_metadata_rerank",
    "dense_minilm",
    "dense_minilm_metadata_rerank",
    "full_engine",
}


def compare(active_dir: Path, historical_dir: Path):
    archived = json.loads(ARCHIVE.read_text())
    active, historical = [
        json.loads((p / "hard_benchmark.json").read_text())
        for p in (active_dir, historical_dir)
    ]
    if (
        active["setup"]["historical_canonical_boost"]
        or not historical["setup"]["historical_canonical_boost"]
    ):
        raise ValueError(
            "Pass an active and a historical canonical-boost run, in that order."
        )
    if set(archived["methods"]) != MODELS or any(
        report["provenance"] != archived["provenance"]
        for report in (active, historical)
    ):
        raise ValueError("Historical roster or provenance mismatch")
    if historical["methods"] != archived["methods"]:
        raise ValueError(
            "The historical replay differs from the published method metrics."
        )
    data_sha256 = {}
    for filename in (
        "public_questions.json",
        "public_documents.json",
        "scorer_labels.json",
    ):
        data = (active_dir / filename).read_bytes()
        if data != (historical_dir / filename).read_bytes():
            raise ValueError(f"Different inputs: {filename}")
        data_sha256[filename] = sha256(data).hexdigest()
    tasks = json.loads((active_dir / "public_questions.json").read_text())
    task_ids = {task["task_id"] for task in tasks}
    if len(tasks) != 65 or len(task_ids) != 65:
        raise ValueError("Expected 65 distinct claims")
    differences = {}
    for method in sorted(MODELS):
        before, after = [
            report["predictions"][method] for report in (historical, active)
        ]
        if any(
            len(rows) != 65 or {r["task_id"] for r in rows} != task_ids
            for rows in (before, after)
        ):
            raise ValueError(f"Missing task-method predictions for {method}")
        old = {r["task_id"]: r for r in before}
        differences[method] = {
            key: sorted(r["task_id"] for r in after if r[key] != old[r["task_id"]][key])
            for key in ("ranking_sha256", "top_10", "predicted_verdict")
        }
    return {
        "upstream_commit": "bf52440cc3f36b898a0c69ab5d0b25f5a5cea8f8",
        "archived_results_sha256": sha256(ARCHIVE.read_bytes()).hexdigest(),
        "inputs_sha256": data_sha256,
        "active_results_sha256": sha256(
            (active_dir / "hard_benchmark.json").read_bytes()
        ).hexdigest(),
        "historical_replay_sha256": sha256(
            (historical_dir / "hard_benchmark.json").read_bytes()
        ).hexdigest(),
        "active_encoder": active["setup"]["dense_encoder"],
        "historical_encoder": historical["setup"]["dense_encoder"],
        "methods_matching_original_on_both_splits": sorted(historical["methods"]),
        "matched_task_method_pairs": len(task_ids) * len(MODELS),
        "active_methods_with_changed_metrics": sorted(
            m for m in MODELS if active["methods"][m] != archived["methods"][m]
        ),
        "changed_tasks_by_method": differences,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("active_dir", type=Path)
    parser.add_argument("historical_dir", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            compare(args.active_dir, args.historical_dir), indent=2, sort_keys=True
        )
    )
