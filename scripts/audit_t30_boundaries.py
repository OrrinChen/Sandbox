"""Check every released T−30 packet, decision date and rolling allowance without opening any outcome."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import build_t30_inputs as study
from run_t30_watch import ARMS, bucket, case_key, days, load, project, schedule

PUBLIC = {
    "wave",
    "cohort",
    "sector",
    "cik",
    "issuer",
    "cutoff",
    "projected_target_start",
    "status",
    "period_end",
    "filing_date",
    "text",
    "historical_sales",
}
RECORD = {"id", "date", "title", "text", "headings"}
AMOUNT = {
    "quarter_end",
    "filed",
    "reported_sales_usd",
    "year_ago_reported_sales_usd",
    "yoy_percent",
}


def expect(condition, context):
    if not condition:
        raise ValueError(f"Public data boundary failed: {context}")


def audit_packets(data, cache):
    study.verify_inputs(data)
    rows = schedule(data)
    sources = {}
    for r in rows:
        k = r["cik"]
        if k not in sources:
            # Cover the last *public* decision date only.
            dates = [x["cutoff"] for x in rows if x["cik"] == k and x["cutoff"]]
            originals = study.filing_metadata(
                cache, k, None, max(dates, default="2017-01-01")
            )
            sources[k] = {f["accessionNumber"]: f for f in originals}
    by_day = defaultdict(list)
    totals = Counter()
    for row in rows:
        key = case_key(row)
        packet = load(data / "packets" / (key + ".json"))
        expect(set(packet) == PUBLIC, key)
        raw = packet["text"]
        expect(set(raw) == {"cik", "issuer", "sector", "records"}, key)
        expect(set(packet["historical_sales"]) == {"quarters", "status"}, key)
        for r in raw["records"]:
            expect(
                set(r) <= RECORD
                and r["date"] == packet["filing_date"] <= row["cutoff"],
                key,
            )
        for q in packet["historical_sales"]["quarters"]:
            expect(
                set(q) == AMOUNT and q["quarter_end"] <= q["filed"] <= row["cutoff"],
                key,
            )
        if row["calendar_status"] == "scheduled":
            by_day[row["wave"], row["cutoff"]].append((row, packet))
            originals = sources[row["cik"]]
            cal = [
                originals[acc] for acc in row["calendar_source_accessions"].split("|")
            ]
            expect(len(cal) == 4 and len({f["reportDate"] for f in cal}) == 4, key)
            expect(
                max(f["filingDate"] for f in cal)
                == row["calendar_source_latest_filed"]
                <= row["calendar_asof"]
                <= row["cutoff"],
                key,
            )
            expect(days(row["projected_target_start"], row["cutoff"]) == 30, key)
        view = project(row, packet)
        if view is not None:
            expect(
                len(raw["records"]) == 5
                and len(packet["historical_sales"]["quarters"]) == 2,
                key,
            )
            totals.update({"complete": 1, "quarterly_pairs": 2, "passages": 5})
        else:
            totals[packet["status"]] += 1
    return by_day, dict(totals)


def audit_days(data, by_day):
    forecasts = data / "forecasts"
    receipt = load(forecasts / "prediction_lock.json")
    expect(set(receipt["days"]) == {f"{w}/{d}" for w, d in by_day}, "decision dates")
    remaining = defaultdict(lambda: 2)
    presented, alerts = Counter(), Counter()
    previous = {}
    for wave, date in sorted(by_day):
        day = forecasts / "days" / wave / date
        lock = load(day / "lock.json")
        scheduled = by_day[wave, date]
        expect(lock["previous"] == previous.get(wave), (wave, date, "previous"))
        expect(
            set(lock["packet_sha256"]) == {case_key(r) for r, _ in scheduled},
            (wave, date, "schedule"),
        )
        previous[wave] = study.digest(day / "lock.json")
        expect(
            previous[wave] == receipt["days"][f"{wave}/{date}"], (wave, date, "receipt")
        )
        complete = defaultdict(dict)
        for row, packet in scheduled:
            view = project(row, packet)
            if view:
                complete[bucket(row)][row["cik"]] = row, packet, view
        for arm in ARMS[:2]:
            batch = load(day / f"{arm}_input.json")
            expect(
                set(batch) == {"cutoff", "sectors"} and batch["cutoff"] == date,
                (wave, date, arm),
            )
            expected_groups = {g for g in complete if remaining[arm, g] > 0}
            expect(
                set(batch["sectors"]) == expected_groups, (wave, date, arm, "cohorts")
            )
            for name, s in batch["sectors"].items():
                expect(
                    set(s) == {"remaining_alerts", "companies"}
                    and s["remaining_alerts"] == remaining[arm, name],
                    (wave, date, name),
                )
                expect(
                    [v["cik"] for v in s["companies"]] == sorted(complete[name]),
                    (wave, date, name, "competitors"),
                )
                for c in s["companies"]:
                    row, packet, view = complete[name][c["cik"]]
                    expected = dict(view)
                    if arm == "joint":
                        expected["historical_sales"] = {
                            "quarters": packet["historical_sales"]["quarters"]
                        }
                    expect(
                        c == expected and row["cutoff"] == date, (wave, date, c["cik"])
                    )
                    presented[arm] += 1
        # Only aggregate counts leave this function. No scorer data are accessed.
        decisions = load(day / "decisions.json")
        expect(set(decisions) == set(ARMS), (wave, date, "arms"))
        for arm, responses in decisions.items():
            used = set()
            for s in responses:
                g = s["sector"]
                selected = [a["cik"] for a in s["alerts"]]
                expect(g not in used and g in complete, (wave, date, g))
                expect(
                    len(set(selected)) == len(selected) <= remaining[arm, g],
                    (wave, date, g, "allowance"),
                )
                expect(
                    set(selected) <= set(complete[g]),
                    (wave, date, g, "eligible issuers"),
                )
                remaining[arm, g] -= len(selected)
                used.add(g)
                alerts[arm] += len(selected)
    return {
        "prediction_lock_sha256": study.digest(forecasts / "prediction_lock.json"),
        "date_waves": len(by_day),
        "model_presentations": dict(presented),
        "alerts_by_arm": dict(alerts),
    }


def run(data, cache, forecasts=False):
    groups, counts = audit_packets(data, cache)
    summary = {
        "input_lock_sha256": study.digest(data / "input_lock.json"),
        "public_packets": counts,
        "scheduled_six_company_cohort_waves": len({bucket(r) for r in schedule(data)}),
        "observed_date_waves": len(groups),
    }
    if forecasts:
        summary["chronological_reservations"] = audit_days(data, groups)
    path = data / (
        "reader_boundary_audit.json" if forecasts else "packet_boundary_audit.json"
    )
    study.lock_json(path, summary)
    return summary


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--data", type=Path, required=True)
    cli.add_argument("--cache", type=Path, required=True)
    cli.add_argument("--forecasts", action="store_true")
    a = cli.parse_args()
    print(run(a.data, a.cache, a.forecasts))
