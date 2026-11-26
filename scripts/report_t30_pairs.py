"""Export paired warning disagreements and sector lead times from a sealed T−30 score."""

import argparse
import csv
import io
from collections import Counter
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path
from statistics import median

from industry_score import below_threshold
from run_t30_watch import ARMS, case_key, digest, load


PAIRED_COLUMNS = (
    "comparison",
    "task",
    "issuer",
    "sector",
    "alerting_arm",
    "abstaining_arm",
    "alerting_arm_slots_at_cutoff",
    "abstaining_arm_slots_at_cutoff",
    "result",
    "locked_alert_reason",
    "cutoff",
    "actual_target_start",
    "target_yoy_pct",
    "first_explicit_disclosure",
    "primary_url",
    "days_to_target",
    "days_to_disclosure",
    "outcome_reason",
    "locked_packet",
)


def write_csv(path, rows, columns=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    payload = stream.getvalue().encode("utf-8")
    if path.exists() and path.read_bytes() != payload:
        raise ValueError(f"Different archived table: {path}")
    if not path.exists():
        path.write_bytes(payload)


def days_summary(values):
    if not values:
        return [None, None, None]
    return [min(values), median(values), max(values)]


def sector_rows(report):
    rows = []
    for sector, stats in [("all", report["overall"]), *report["by_sector"].items()]:
        for arm, counts in stats["by_arm"].items():
            row = dict(
                sector=sector,
                arm=arm,
                registered=stats["cases"],
                resolved=stats["resolved"],
                events=stats["qualified_events"],
            )
            row.update(
                {
                    k: counts[k]
                    for k in (
                        "alerts",
                        "hit",
                        "miss",
                        "false_alarm",
                        "unresolved_alert",
                    )
                }
            )
            for measure in ("days_to_start", "days_to_disclosure"):
                for name, value in zip(
                    ("min", "median", "max"), days_summary(counts[measure + "_at_hits"])
                ):
                    row[f"{measure}_{name}_at_hits"] = value
            rows.append(row)
    return rows


def paired_rows(rows):
    contrasts = (("joint", "text"), ("joint", "trend"), ("text", "trend"))
    spent = Counter()

    def chronology(r):
        return r["wave"], r["cohort"], r["cutoff"] or ""

    for (wave, cohort, _), cohort_day in groupby(
        sorted(rows, key=chronology), chronology
    ):
        day = list(cohort_day)
        slots = {arm: 2 - spent[wave, cohort, arm] for arm in ARMS}
        yield from day_pairs(day, contrasts, slots)
        for arm in ARMS:
            spent[wave, cohort, arm] += sum(bool(r[arm]["reason"]) for r in day)
            if spent[wave, cohort, arm] > 2:
                raise ValueError(
                    f"Archived alerts exceed the registered cohort budget: {cohort}"
                )


def day_pairs(rows, contrasts, slots):
    for r in rows:
        for first, second in contrasts:
            if bool(r[first]["reason"]) == bool(r[second]["reason"]):
                continue
            alerting, abstaining = (
                (first, second) if r[first]["reason"] else (second, first)
            )
            yield {
                "comparison": first + "_vs_" + second,
                "task": case_key(r),
                "issuer": r["issuer"],
                "sector": r["sector"],
                "alerting_arm": alerting,
                "abstaining_arm": abstaining,
                "alerting_arm_slots_at_cutoff": slots[alerting],
                "abstaining_arm_slots_at_cutoff": slots[abstaining],
                "result": r[alerting]["result"],
                "locked_alert_reason": r[alerting]["reason"],
                "cutoff": r["cutoff"],
                "actual_target_start": r["actual_start"],
                "target_yoy_pct": r["target_yoy_pct"],
                "first_explicit_disclosure": r["disclosure_date"],
                "primary_url": r["disclosure_url"],
                "days_to_target": r["days_to_start"],
                "days_to_disclosure": r["days_to_disclosure"],
                "outcome_reason": r["reason"],
                "locked_packet": "../packets/" + case_key(r) + ".json",
            }


def false_alarm_rows(rows, facts):
    lookup = {(cik, q["end"]): q for cik, quarters in facts.items() for q in quarters}
    counts = Counter()
    for r in rows:
        if not any(r[a]["result"] == "false_alarm" for a in ARMS):
            continue
        previous_end = (
            date.fromisoformat(r["actual_start"]) - timedelta(days=1)
        ).isoformat()
        prior = below_threshold(lookup[r["cik"], previous_end])
        current = below_threshold(lookup[r["cik"], r["actual_end"]])
        if r["reason"] == "already_disclosed":
            cause = "already_disclosed"
        elif current is False:
            cause = "target_sales_above_decline_threshold"
        elif current is True and prior is True:
            cause = "continued_prior_decline"
        else:
            cause = "prior_already_below_threshold_target_comparison_unavailable"
        for arm in ARMS:
            if r[arm]["result"] != "false_alarm":
                continue
            counts[arm, "all", cause] += 1
            for control in ARMS:
                if control != arm and not r[control]["reason"]:
                    counts[arm, "exclusive_vs_" + control, cause] += 1
    return [
        {"arm": a, "comparison": b, "outcome": c, "count": n}
        for (a, b, c), n in sorted(counts.items())
    ]


def export(data, out):
    report = load(data / "results/report.json")
    if report["prediction_sha256"] != digest(data / "forecasts/prediction_lock.json"):
        raise ValueError("Report and locked predictions differ")
    for name, expected in report["scorer_files"].items():
        if digest(data / "scorer" / name) != expected:
            raise ValueError(f"Scorer evidence changed: {name}")
    if set(report["overall"]["by_arm"]) != set(ARMS):
        raise ValueError("Report is missing a registered arm")
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "industry_results.csv", sector_rows(report))
    write_csv(
        out / "paired_disagreements.csv", paired_rows(report["rows"]), PAIRED_COLUMNS
    )
    write_csv(
        out / "false_alarm_outcomes.csv",
        false_alarm_rows(report["rows"], load(data / "scorer/quarters.json")),
        ("arm", "comparison", "outcome", "count"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    export(args.data, args.out or args.data / "results")
