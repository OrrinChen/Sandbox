"""Privately resolve new-panel revenue onsets after the three-arm global prediction lock."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

from industry_disclosures import (
    archive_manifest,
    capture,
    import_sources,
    research,
    validate_source,
)
from industry_revenue import histories, panel_revenue_tags
from industry_score import first_warning, quarter_index, read, resolve, summarize
from run_industry_watch import trend_rates

DATA = Path(__file__).with_name("joint_watch_dev")
ARMS = ("text", "trend", "joint")
COMPARATORS = ("text", "trend")


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def scope(root: Path) -> tuple[list[dict], dict, dict]:
    from run_joint_watch import verify_lock

    verify_lock(root)
    with (DATA / "company_quarters.csv").open(encoding="utf-8") as stream:
        schedule = list(csv.DictReader(stream))
    by_issuer, decisions = {}, {}
    for origin in sorted({r["origin"] for r in schedule}):
        evidence = read(root / "evidence" / f"{origin}.json")
        trends = read(root / "trend_inputs" / f"{origin}.json")
        trend_rows = {r["cik"]: r for r in trends["issuers"]}
        for r in evidence["companies"]:
            anchor = {k: r.get(k) for k in ("period_end", "status")}
            if anchor["status"] in {"stale", "missing_anchor"}:
                anchor["unresolved_reason"] = anchor["status"]
            anchor["trend_available"] = trend_rates(
                trend_rows[r["cik"]], anchor["period_end"], trends["cutoff"]
            ) is not None and not anchor.get("unresolved_reason")
            by_issuer[origin, r["cik"]] = anchor
        for d in read(root / origin / "alerts.json")["decisions"]:
            key = origin, d["sector"], d["arm"]
            if key in decisions:
                raise ValueError("Duplicate decisions")
            decisions[key] = d["alerts"]
    return schedule, by_issuer, decisions


def export_quarters(cache: Path, root: Path) -> None:
    rows, _, _ = scope(root)
    houses = [{"cik": cik} for cik in sorted({r["cik"] for r in rows})]
    quarters = histories(cache, houses, "2025-12-31", panel_revenue_tags(DATA))
    # Include the latest fresh anchor before the first cutoff and the last two
    # following quarters. Retain original/accession-specific sales comparables.
    filtered = {
        c: [r for r in qs if "2023-04-01" <= r["end"] <= "2025-08-15"]
        for c, qs in quarters.items()
    }
    save(root / "scorer/quarters.json", filtered)


def crossings(root: Path) -> list[dict]:
    rows, anchors, _ = scope(root)
    facts = {
        k: quarter_index(v) for k, v in read(root / "scorer/quarters.json").items()
    }
    targets = {}
    for row in rows:
        cik = row["cik"]
        result = resolve(
            row["cutoff_us_eastern"], anchors[row["origin"], cik], facts[cik], {}
        )
        end = result["event_end"]
        if end:
            q = facts[cik][0][end]
            targets[cik, end] = {
                "cik": cik,
                "issuer": row["issuer"],
                "sector": row["sector"],
                **q,
                "review_rules": (
                    "Confirm the GAAP quarterly reported amount, comparable year-ago denominator, and restatement scope. "
                    "Quarterly exact points or ranges with a wholly qualifying upper bound only. 'Approximately', "
                    "'roughly', annual forecasts minus nine-month actuals, and open indications are insufficient. "
                    "Look for later explicit bounds or actuals after such indications. Name unavailable material "
                    "meetings, prior earning calls, presentations and any doubts explicitly."
                ),
            }
    return [targets[k] for k in sorted(targets)]


def compare(rows: list[dict], events: list[dict], control: str) -> dict:
    def early(event, arm):
        return bool(event[arm] and event[arm]["timing"] == "before_quarter")

    added, lost, both = [], [], []
    added_false, saved_false = [], []
    for event in events:
        a, b = early(event, "joint"), early(event, control)
        ref = {"cik": event["cik"], "end": event["end"], "issuer": event["issuer"]}
        if a and b:
            both.append(ref)
        elif a:
            added.append(ref)
        elif b:
            lost.append(ref)
    for row in rows:
        a, b = (
            row["joint"]["result"] == "false_alarm",
            row[control]["result"] == "false_alarm",
        )
        ref = {k: row[k] for k in ("origin", "cik", "issuer")}
        if a and not b:
            added_false.append(ref)
        if b and not a:
            saved_false.append(ref)
    return {
        "comparison": f"joint_vs_{control}",
        "paired_resolved_rows": sum(r["status"] != "unresolved" for r in rows),
        "pre_start_common": both,
        "pre_start_joint_only": added,
        "pre_start_control_only": lost,
        "pre_start_net_gain": len(added) - len(lost),
        "joint_only_false_alarms": added_false,
        "control_only_false_alarms": saved_false,
        "net_additional_false_alarms": len(added_false) - len(saved_false),
        "observed_gate_pass": len(added) > len(lost)
        and len(added_false) <= len(saved_false),
    }


def score_data(schedule, anchors, decisions, facts, disclosures) -> dict:
    members = {}
    for r in schedule:
        members.setdefault((r["origin"], r["sector"]), set()).add(r["cik"])
    if set(decisions) != {(o, s, a) for o, s in members for a in ARMS}:
        raise ValueError("Incomplete decision matrix")
    if set(facts) != {r["cik"] for r in schedule}:
        raise ValueError("Issuer facts missing")
    alerts = {}
    for (o, s, arm), entries in decisions.items():
        if len(entries) > 2 or len({a["cik"] for a in entries}) != len(entries):
            raise ValueError("Invalid budget or duplicate alert")
        for a in entries:
            if a["cik"] not in members[o, s] or not a["reason"].strip():
                raise ValueError("Unknown issuer or missing reason")
            alerts[o, a["cik"], arm] = a["reason"]
    indexed = {k: quarter_index(v) for k, v in facts.items()}
    for cik, records in disclosures.items():
        for end, record in records.items():
            validate_source(indexed[cik][0][end], record, f"{cik}_{end}")
    rows, events, examined = [], {}, set()
    for item in sorted(schedule, key=lambda x: (x["cutoff_us_eastern"], x["cik"])):
        cik, o, day = item["cik"], item["origin"], item["cutoff_us_eastern"]
        outcome = resolve(day, anchors[o, cik], indexed[cik], disclosures.get(cik, {}))
        r = {**item, **outcome}
        r["days_before_quarter_start"] = None
        key = (cik, r["event_end"])
        if r["event_end"]:
            examined.add(key)
            r["days_before_quarter_start"] = (
                date.fromisoformat(r["event_start"]) - date.fromisoformat(day)
            ).days
        if r["status"] == "positive":
            event = events.setdefault(
                key,
                {
                    "cik": cik,
                    "issuer": r["issuer"],
                    "sector": r["sector"],
                    "start": r["event_start"],
                    "end": r["event_end"],
                    "disclosure": disclosures[cik][r["event_end"]],
                    "eligible_origins": [],
                    "eligible_pre_start_origins": [],
                    **dict.fromkeys(ARMS),
                },
            )
            event["eligible_origins"].append(o)
            if day < r["event_start"]:
                event["eligible_pre_start_origins"].append(o)
        for arm in ARMS:
            reason = alerts.get((o, cik, arm))
            if r["status"] == "positive":
                result = "hit" if reason else "miss"
            elif r["status"] == "unresolved":
                result = "unresolved"
            else:
                result = "false_alarm" if reason else "correct_negative"
            r[arm] = {"alert": bool(reason), "reason": reason, "result": result}
            if result == "hit" and event[arm] is None:
                event[arm] = {
                    **first_warning(r, arm),
                    "days_before_quarter_start": r["days_before_quarter_start"],
                }
        rows.append(r)
    if examined != {(c, e) for c, d in disclosures.items() for e in d}:
        raise ValueError(
            "Explicit disclosure investigation required for each numeric crossing"
        )
    distinct = list(events.values())
    groups = {}
    for sector in ("all", *sorted({r["sector"] for r in rows})):
        part = [r for r in rows if sector in ("all", r["sector"])]
        subset = [e for e in distinct if sector in ("all", e["sector"])]
        comparisons = {arm: compare(part, subset, arm) for arm in COMPARATORS}
        groups[sector] = {
            "scheduled": len(part),
            "status": dict(Counter(r["status"] for r in part)),
            "unresolved_reasons": dict(
                Counter(r["reason"] for r in part if r["status"] == "unresolved")
            ),
            "events_with_pre_start_opportunity": sum(
                bool(e["eligible_pre_start_origins"]) for e in subset
            ),
            "by_arm": {a: summarize(part, subset, a) for a in ARMS},
            "paired": comparisons,
            "observed_gate_pass_both": all(
                c["observed_gate_pass"] for c in comparisons.values()
            ),
        }
    return {"groups": groups, "events": distinct, "rows": rows}


def score(root: Path) -> dict:
    schedule, anchors, decisions = scope(root)
    fact_path = root / "scorer/quarters.json"
    label_path = root / "scorer/disclosures.json"
    result = score_data(schedule, anchors, decisions, read(fact_path), read(label_path))
    audits = [root / "prediction_lock.json", fact_path, label_path]
    result["sha256"] = {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in audits
    }
    save(root / "report.json", result)
    fields = [
        "origin",
        "cutoff_us_eastern",
        "cik",
        "issuer",
        "sector",
        "period_end",
        "status",
        "reason",
        "event_start",
        "event_end",
        "first_disclosure",
        "lead_days",
        "days_before_quarter_start",
    ]
    with (root / "scored_company_quarters.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields + list(ARMS))
        writer.writeheader()
        for r in result["rows"]:
            writer.writerow(
                {**{k: r[k] for k in fields}, **{a: r[a]["result"] for a in ARMS}}
            )
    return result


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument(
        "action",
        choices=[
            "quarters",
            "cases",
            "capture",
            "research",
            "rescue",
            "archive",
            "import",
            "score",
        ],
    )
    args.add_argument("--root", type=Path, default=DATA / "run")
    args.add_argument("--cache", type=Path)
    args.add_argument("--archives", type=Path)
    args.add_argument("--reviews", type=Path)
    args.add_argument("--rescues", type=Path)
    args.add_argument("--identity")
    args.add_argument("--workers", type=int, default=6)
    opt = args.parse_args()
    for field in {
        "quarters": ["cache"],
        "capture": ["cache", "archives", "identity"],
        "archive": ["archives"],
        "research": ["reviews"],
        "rescue": ["reviews", "rescues"],
        "import": ["reviews"],
    }.get(opt.action, []):
        if not getattr(opt, field):
            args.error(f"{opt.action} requires --{field}")
    if opt.action == "score":
        print(json.dumps(score(opt.root)["groups"]["all"]["by_arm"]))
    elif opt.action == "quarters":
        export_quarters(opt.cache, opt.root)
    else:
        cases = crossings(opt.root)
        if opt.action == "cases":
            print(json.dumps(cases))
        elif opt.action == "capture":
            capture(cases, opt.cache, opt.archives, opt.identity)
        elif opt.action == "archive":
            archive_manifest(
                cases, opt.archives, opt.root / "scorer/filing_inventory.json"
            )
        elif opt.action == "import":
            import_sources(
                cases, opt.reviews, opt.root / "scorer/research_draft.json", opt.rescues
            )
        else:
            output = opt.rescues if opt.action == "rescue" else opt.reviews
            output.mkdir(parents=True, exist_ok=True)
            jobs = []
            with ThreadPoolExecutor(max_workers=opt.workers) as pool:
                for c in cases:
                    previous = None
                    if opt.action == "rescue":
                        previous = read(opt.reviews / f"{c['cik']}_{c['end']}.json")
                        if previous.get("date"):
                            continue
                    jobs.append(
                        pool.submit(research, c, output, opt.archives, previous)
                    )
                for future in jobs:
                    print(future.result(), flush=True)
