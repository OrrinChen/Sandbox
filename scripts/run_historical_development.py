"""Freeze dated historical evidence and grade recorded reader and question-only arms."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from pathlib import Path
from random import Random

from run_financial_self_audit_blind import hashes, verify_hashes
from run_financial_self_audit_pilot import digest, indexed, read, write
from run_multidim_development import (
    AUDIT, BATCHES, COMMON, DIMENSIONS, REFS, SCRIPTS, STAGES,
    lock_initial, recordings, seal, verify_public,
)
from score_multidim_development import grade, paired_result, report_question, summarize


SOURCES = ("run_historical_development.py", "history_cases_companies.py", "history_cases_policy.py",
           "history_cases_studies.py", "run_multidim_development.py", "score_multidim_development.py",
           "run_financial_self_audit_blind.py", "run_financial_self_audit_pilot.py")
AS_OF = """Work as of the end of the stated cutoff date using only the assigned row. Excerpt locators
provide the publication's context (including units, groups and table columns). Do not open the URLs.
If the row contains forecast, supply a separate forecast_pct number between 0 and 100 giving your
probability as of the cutoff. This is a prediction; never cite or look up the eventual outcome.
The audit decision and issues concern choice, value and citations. If keeping the answer, keep
any initial probability as well. On rows without a forecast, omit forecast_pct.
"""
CONTROL = """Answer each dated question independently, with no source material or tools. Give your best
answer using your existing knowledge, using the choices, units and conventions requested by the
question. If you cannot answer, return choice unknown and value null. Return one JSON array with
row, choice, value (a decimal string or null) and citations (always an empty list). For a forecast,
also give forecast_pct as a number between 0 and 100 as of the cutoff. Use one completion, with
at most 480 output tokens per question. Do not look up sources, use calculation tools, or see feedback.
"""


def build_packets(events: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    if len(events) != 8 or len({e["id"] for e in events}) != 8:
        raise ValueError("Expected eight separate historical events")
    if {e["direction"] for e in events} != {"up", "down", "flat"}:
        raise ValueError("Expected rising, falling and flat observed outcomes")
    rng = Random(802611)
    buckets = [[] for _ in BATCHES]
    for i, event in enumerate(events):
        if Counter(q["dimension"] for q in event["questions"]) != Counter(DIMENSIONS):
            raise ValueError(f"Missing or duplicate dimension in {event['id']}")
        date.fromisoformat(event["outcome"]["date"])
        for q in event["questions"]:
            cutoff = date.fromisoformat(q["cutoff"])
            evidence = q["evidence"]
            if (len(evidence) != 5 or len({s["text"] for s in evidence}) != 5
                    or not all(all(s.get(k) for k in ("source", "text", "url", "published", "locator"))
                               and s["url"].startswith("https://") and date.fromisoformat(s["published"]) <= cutoff
                               for s in evidence)):
                raise ValueError(f"Missing, duplicated or late source in {event['id']} {q['dimension']}")
            gold = q["gold"]
            if (not gold["citations"] or any(not refs or grade({**gold, "citations": refs}, gold)
                                             for refs in gold["citations"])):
                raise ValueError(f"Invalid reference in {event['id']}")
            forecast = q.get("forecast")
            if forecast and (forecast["binary_outcome"] not in (0, 1)
                             or date.fromisoformat(forecast["resolution_date"]) <= cutoff
                             or not forecast["url"].startswith("https://")):
                raise ValueError(f"Invalid forecast resolution in {event['id']}")
            # The same context never receives another question (including later releases) from this event.
            slot = (i + DIMENSIONS.index(q["dimension"])) % len(buckets)
            buckets[slot].append((event, q))
    batches, labels = [], []
    for bucket in buckets:
        rng.shuffle(bucket)
        rows = []
        for event, q in bucket:
            n = len(labels) + 1
            public = {"row": n, "event": event["name"], "cutoff": q["cutoff"], "question": q["question"],
                      "evidence": [{"ref": ref, **{key: hit[key] for key in
                                    ("text", "source", "published", "locator", "url")}}
                                   for ref, hit in zip(REFS, q["evidence"])]}
            if "forecast" in q:
                public["forecast"] = q["forecast"]["question"]
            rows.append(public)
            labels.append({"row": n, "event_id": event["id"], "dimension": q["dimension"],
                           "famous": event["famous"], "direction": event["direction"],
                           "outcome": event["outcome"], "gold": q["gold"], "forecast": q.get("forecast")})
        batches.append(rows)
    return batches, labels


def freeze(root: Path) -> None:
    from history_cases_companies import build as companies
    from history_cases_policy import build as policy
    from history_cases_studies import build as studies

    batches, labels = build_packets(companies() + policy() + studies())
    famous = {label["row"] for label in labels if label["famous"]}
    if not famous:
        raise ValueError("No events designated for question-only control")
    for stage in (*STAGES, "memory", "private"):
        (root / stage).mkdir(exist_ok=True, parents=True)
    files = []
    for stage in (*STAGES, "memory"):
        path = root / stage / "prompt.txt"
        prompt = CONTROL if stage == "memory" else COMMON + AS_OF + (AUDIT if stage == "audit" else "")
        if path.exists() and path.read_text(encoding="utf-8") != prompt:
            raise ValueError(f"Prompt already locked: {stage}")
        if not path.exists():
            path.write_text(prompt, encoding="utf-8")
        files.append(path)
    for b, rows in zip(BATCHES, batches):
        for stage, payload in (("initial", rows), ("memory", [{**row, "evidence": []}
                                for row in rows if row["row"] in famous])):
            path = root / stage / f"inputs-{b}.json"
            seal(path, payload)
            files.append(path)
    path = root / "private/labels.json"
    seal(path, labels)
    seal(root / "freeze.json", {
        "version": 1, "question_count": len(labels), "files": hashes(root, files + [path]),
        "source_sha256": hashes(SCRIPTS, [SCRIPTS / name for name in SOURCES]),
        "protocol": {"model": "fresh inherited Codex contexts", "top_k": 5,
                     "completions_per_batch_per_stage": 1, "requested_output_tokens_per_row": 480,
                     "actual_reasoning_tokens": None, "calculation_tools": False,
                     "memory_control_rows": sorted(famous), "forecast_score": "mean squared probability error"},
    })


def group_summary(rows: list[dict]) -> dict:
    summary = summarize(rows, [])
    for key in ("pair_count", "pairs_both_passed"):
        summary.pop(key)
    summary["content_correct"] = {stage: sum(not ({"choice", "value"} & set(r["failed_fields"][stage]))
                                             for r in rows) for stage in STAGES}
    return summary


def forecast_result(answer: dict, outcome: int) -> dict:
    pct = answer.get("forecast_pct")
    valid = type(pct) in (int, float) and 0 <= pct <= 100
    return {"forecast_pct": pct, "outcome": outcome, "brier": (pct/100-outcome)**2 if valid else None}


def score(root: Path) -> None:
    manifest = verify_public(root)
    for name in ("comparison_lock", "initial_lock"):
        verify_hashes(root, read(root / f"{name}.json"))
    runs = {stage: recordings(root, stage) for stage in STAGES}
    paths = [p for _, files in runs.values() for p in files]
    memory, public = {}, {}
    for b in BATCHES:
        public.update({q["row"]: q for q in read(root / "initial" / f"inputs-{b}.json")})
        expected = {q["row"] for q in read(root / "memory" / f"inputs-{b}.json")}
        path = root / "memory" / f"responses-{b}.json"
        memory.update(indexed(read(path), expected))
        paths.append(path)
    if set(memory) != set(manifest["protocol"]["memory_control_rows"]):
        raise ValueError("Incomplete memory control")
    seal(root / "recording_lock.json", hashes(root, paths + [root / "comparison_lock.json"]))
    verify_hashes(root, manifest["files"])
    labels = indexed(read(root / "private/labels.json"), set(public))
    rows, forecasts, controls = [], [], []
    for n, q in sorted(public.items()):
        label = labels[n]
        answers = {s: runs[s][0][n] for s in STAGES}
        # The shared scorer's grouping fields are replaced by the historical event identity.
        result = report_question({**label, "pair_id": label["event_id"], "side": None}, answers)
        result.pop("pair_id")
        result.pop("side")
        result.update({"event": q["event"], "event_id": label["event_id"], "cutoff": q["cutoff"],
                       "question": q["question"], "packet": f"initial/inputs-{(n-1)//8+1}.json"})
        rows.append(result)
        if n in memory:
            if memory[n].get("citations") != []:
                raise ValueError(f"Memory response includes unavailable evidence on row {n}")
            failures = [f for f in grade(memory[n], label["gold"]) if f != "citations"]
            with_text = not ({"choice", "value"} & set(result["failed_fields"]["initial"]))
            controls.append({"row": n, "event": q["event"], "dimension": label["dimension"],
                             "with_text": with_text, "without_text": not failures, "answer": memory[n],
                             "failed_content_fields": failures, "pair": paired_result(with_text, not failures)})
        if label["forecast"]:
            actual = label["forecast"]
            submissions = {**answers, **({"memory": memory[n]} if n in memory else {})}
            forecasts.append({"row": n, "event": q["event"], **actual,
                              "arms": {s: forecast_result(a, actual["binary_outcome"])
                                       for s, a in submissions.items()}})
    brier = {}
    for stage in (*STAGES, "memory"):
        eligible = [f["arms"][stage]["brier"] for f in forecasts if stage in f["arms"]]
        valid = [v for v in eligible if v is not None]
        brier[stage] = {"eligible": len(eligible), "valid": len(valid),
                        "mean_brier": sum(valid)/len(valid) if valid else None}
    def comparison(items: list[dict]) -> dict:
        return {"questions": len(items), "with_text": sum(c["with_text"] for c in items),
                "without_text": sum(c["without_text"] for c in items),
                **{key: sum(c["pair"] == val for c in items) for key, val in
                   (("both_correct","both_pass"), ("text_only","left_only"),
                    ("no_text_only","right_only"), ("both_wrong","both_fail"))}}
    report = {
        "freeze_sha256": digest(root / "freeze.json"), "recording_sha256": digest(root / "recording_lock.json"),
        "protocol": manifest["protocol"], "overall": group_summary(rows),
        "by_dimension": {d: group_summary([r for r in rows if r["dimension"] == d]) for d in DIMENSIONS},
        "events": {q["event_id"]: {"outcome": q["outcome"], "direction": q["direction"], "famous": q["famous"]}
                   for q in labels.values()}, "per_question": rows,
        "no_material": {"comparison": comparison(controls), "rows": controls,
                        "by_dimension": {d: comparison([c for c in controls if c["dimension"] == d])
                                         for d in DIMENSIONS}},
        "forecasts": {"scores": brier, "rows": forecasts},
    }
    write(root / "report.json", report)
    with (root / "per_question.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["row", "event", "dimension", "cutoff", "question", *STAGES, "detected", "localized",
                  "repaired", "false_alarm", "spoiled", "initial_failed_fields", "audit_failed_fields",
                  "retry_failed_fields"]
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **row["passed"],
                             **{s + "_failed_fields": ",".join(row["failed_fields"][s]) for s in STAGES}})


if __name__ == "__main__":
    actions = {"freeze": freeze, "lock-initial": lock_initial, "score": score}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=actions)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    actions[args.action](args.directory)
