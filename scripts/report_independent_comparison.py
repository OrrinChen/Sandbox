"""Summarize paired outcomes and re-execute all recorded failed submissions."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
import statistics

from run_independent_comparison import (
    PROTOCOL,
    digest,
    expand,
    grade_one,
    load,
    predictions,
    seal,
    spreadsheets,
    suite,
)


def replay_failures(root, rows, workers):
    decisions = {(r["task"], r["arm"]): r for r in rows}
    results, ordinary = [], []
    for arm in load(PROTOCOL)["arms"]:
        books = {}
        for name in (root / "recordings" / arm).glob("*.json"):
            for task, submission in load(name)["submissions"].items():
                initial = decisions[task, arm]
                if initial["passed"]:
                    continue
                if suite.inventory()[task][0] is spreadsheets:
                    try:
                        candidate = expand(submission)
                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        IndexError,
                        AttributeError,
                    ):
                        candidate = {}
                    if suite.fingerprint(candidate) != initial["candidate_sha256"]:
                        raise ValueError("Changed workbook submission")
                    books[task] = candidate
                else:
                    ordinary.append((task, arm, submission))
        if books:
            results.extend(
                (task, arm, verdict)
                for task, verdict in spreadsheets.batch_grade(books).items()
            )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(grade_one, ordinary):
            if row != decisions[row["task"], row["arm"]]:
                raise ValueError("Changed submission or verdict")
            results.append((row["task"], row["arm"], row["passed"]))
    if any(x[2] for x in results) or len(results) != sum(not r["passed"] for r in rows):
        raise ValueError("Failed to reproduce complete failed subset")
    return [{"task": t, "arm": a, "passed_on_replay": v} for t, a, v in sorted(results)]


def paired_interval(cases, draws=10000):
    """Task-weighted self-check minus direct pass rate, resampling source groups."""
    groups = defaultdict(list)
    for task, values in sorted(cases.items()):
        group = suite.inventory()[task][1]["source_group"]
        groups[group].append(int(values["self_check"]) - int(values["direct"]))
    clusters = [(sum(v), len(v)) for _, v in sorted(groups.items())]
    rng = random.Random(20261124)
    samples = []
    for _ in range(draws):
        selected = rng.choices(clusters, k=len(clusters))
        samples.append(100 * sum(x[0] for x in selected) / sum(x[1] for x in selected))
    samples.sort()
    return {
        "groups": len(groups),
        "draws": draws,
        "seed": 20261124,
        "unit": "percentage points, self-check minus direct",
        "delta": 100 * sum(x[0] for x in clusters) / len(cases),
        "percentile_95": [samples[int((draws - 1) * p)] for p in (0.025, 0.975)],
    }


def analyze(root, workers):
    score = load(root / "score.json")
    if load(root / "prediction_lock.json") != predictions(root) or score[
        "prediction_lock_sha256"
    ] != digest(root / "prediction_lock.json"):
        raise ValueError("Sealed inputs or outputs differ")
    arms = load(PROTOCOL)["arms"]
    cases = defaultdict(dict)
    for r in score["rows"]:
        cases[r["task"]][r["arm"]] = r["passed"]
    if len(cases) != score["tasks"] or any(set(v) != set(arms) for v in cases.values()):
        raise ValueError("Incomplete pair")
    counts = defaultdict(Counter)
    origin_counts = defaultdict(Counter)
    for task, pair in cases.items():
        outcome = {
            (True, True): "both",
            (False, False): "neither",
            (True, False): "direct_only",
            (False, True): "self_check_only",
        }[pair["direct"], pair["self_check"]]
        adapter, task_info = suite.inventory()[task]
        counts[task_info["domain"]][outcome] += 1
        if adapter is spreadsheets:
            origin = "SpreadsheetBench"
        elif task_info["source_group"].startswith("exercism/"):
            origin = "Exercism"
        else:
            origin = "Sandbox original"
        origin_counts[origin][outcome] += 1
    usage = {}
    for arm in arms:
        records = [load(p) for p in (root / "recordings" / arm).glob("*.json")]
        total = Counter()
        for record in records:
            total.update(record["usage"])
        usage[arm] = {
            "accepted_sessions": len(records),
            "accepted_without_retry": sum(r["attempt"] == 1 for r in records),
            "tokens_for_accepted_sessions": dict(total),
            "median_output_tokens_per_accepted_session": statistics.median(
                r["usage"]["output_tokens"] for r in records
            ),
        }
    failed = replay_failures(root, score["rows"], workers)
    seal(
        root / "failure_replay.json",
        {
            "score_sha256": digest(root / "score.json"),
            "failed_submissions_replayed": len(failed),
            "rows": failed,
        },
    )
    analysis = {
        "score_sha256": digest(root / "score.json"),
        "paired_by_domain": counts,
        "paired_by_origin": origin_counts,
        "source_cluster_bootstrap": paired_interval(cases),
        "usage": usage,
        "failed_submissions_replayed": len(failed),
    }
    seal(root / "paired_summary.json", analysis)
    return analysis


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    r = analyze(args.out, args.workers)
    print("Reproduced failed submissions:", r["failed_submissions_replayed"])
