"""Score sealed cross-industry forecasts against private fiscal-quarter and disclosure records."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import median

ARMS = ("text", "metadata", "trend")
DATA = Path(__file__).resolve().parent / "cross_industry_watch"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def quarter_index(facts: list[dict]) -> tuple[dict, dict]:
    """Require actual adjacent reporting periods. An absent quarter cannot move the horizon."""
    ends, successors = {}, {}
    for q in facts:
        end = date.fromisoformat(q["end"])
        start = date.fromisoformat(q["start"]) if q["start"] else None
        if q["end"] in ends or (start and (start > end or q["start"] in successors)):
            raise ValueError(f"Overlapping or duplicate fiscal quarter {q}")
        if q["latest_filed"] and date.fromisoformat(q["latest_filed"]) < end:
            raise ValueError("Quarter-end after filing")
        ends[q["end"]] = q
        if start:
            successors[q["start"]] = q
    return ends, successors


def below_threshold(q: dict) -> bool | None:
    a, b = q.get("sales"), q.get("year_ago_sales")
    if a is None or b is None or not q.get("source_accessions") or not q.get("latest_filed"):
        return None
    sales, previous = Decimal(str(a)), Decimal(str(b))
    if not (sales.is_finite() and previous.is_finite() and sales >= 0 and previous > 0):
        return None
    return sales * 100 <= previous * 95


def fiscal_window(anchor: str, by_end: dict, by_start: dict) -> list[dict]:
    window = []
    q = by_end.get(anchor)
    while q is not None and len(window) < 3:
        window.append(q)
        day_after = date.fromisoformat(q["end"]) + timedelta(days=1)
        q = by_start.get(day_after.isoformat())
    return window


def validated_disclosure(record: dict | None, q: dict) -> date | None:
    if not record or not record.get("date"):
        return None
    day = date.fromisoformat(record["date"])
    if (
        day > date.fromisoformat(q["latest_filed"])
        or not record.get("url", "").startswith("https://")
        or not record.get("basis")
        or not record.get("coverage")
    ):
        raise ValueError(f"Incomplete/discrepant disclosure record for {q['end']}")
    return day


def resolve(cutoff: str, anchor: dict, index: tuple[dict, dict], disclosures: dict) -> dict:
    result = dict(
        period_end=anchor.get("period_end"),
        horizon=[],
        evidence_status=anchor.get("status"),
        trend_available=anchor.get("trend_available"),
        status="unresolved",
        reason=None,
        event_start=None,
        event_end=None,
        first_disclosure=None,
        lead_days=None,
    )
    if anchor.get("unresolved_reason") or not anchor.get("period_end"):
        result["reason"] = anchor.get("unresolved_reason") or "missing_anchor"
        return result
    if date.fromisoformat(anchor["period_end"]) > date.fromisoformat(cutoff):
        raise ValueError("Future anchor")
    window = fiscal_window(anchor["period_end"], *index)
    result["horizon"] = [q["end"] for q in window[1:]]
    problem = None if len(window) == 3 else "incomplete_or_nonconsecutive_quarters"
    for previous, current in zip(window, window[1:]):
        before, after = below_threshold(previous), below_threshold(current)
        if before is True or after is False:
            continue
        if before is None or after is None:
            if problem is None:
                problem = "missing_comparable_revenue"
            continue
        # A crossing now mathematically rules out a second crossing in this two-quarter window.
        result["event_start"] = current["start"]
        result["event_end"] = current["end"]
        day = validated_disclosure(disclosures.get(current["end"]), current)
        if day is None:
            result["reason"] = "unverified_first_disclosure"
            return result
        lead = (day - date.fromisoformat(cutoff)).days
        result["first_disclosure"] = day.isoformat()
        result["status"] = "positive" if lead > 0 else "already_disclosed"
        result["lead_days"] = lead if lead > 0 else None
        return result
    result["reason"] = problem
    result["status"] = "unresolved" if problem else "absent"
    return result


def checked_alerts(schedule: list[dict], decisions: dict) -> dict:
    panels = defaultdict(set)
    seen = set()
    for r in schedule:
        issuer_origin = r["cik"], r["origin"]
        if issuer_origin in seen:
            raise ValueError(f"Duplicate observation {issuer_origin}")
        seen.add(issuer_origin)
        panels[r["origin"], r["sector"]].add(r["cik"])
    if set(decisions) != {(o, s, a) for o, s in panels for a in ARMS}:
        raise ValueError("Missing or extraneous panel/arm decisions")
    found = {}
    for (origin, sector, arm), alerts in decisions.items():
        members = panels[origin, sector]
        if len(alerts) > 2:
            raise ValueError("Exceeded two-alert budget")
        for alert in alerts:
            key = origin, sector, arm, alert["cik"]
            if key in found or alert["cik"] not in members or not alert.get("reason", "").strip():
                raise ValueError(f"Invalid or duplicate alert {key}")
            found[key] = alert["reason"]
    return found


def first_warning(row: dict, arm: str) -> dict:
    cutoff = row["cutoff_us_eastern"]
    if cutoff < row["event_start"]:
        timing = "before_quarter"
    elif cutoff < row["event_end"]:
        timing = "during_quarter_before_end"
    else:
        timing = "on_or_after_quarter_end"
    return dict(
        origin=row["origin"],
        cutoff=cutoff,
        lead_days=row["lead_days"],
        reason=row[arm]["reason"],
        timing=timing,
    )


def summarize(rows: list[dict], events: list[dict], arm: str) -> dict:
    counts = Counter(r[arm]["result"] for r in rows)
    detected = [event[arm] for event in events if event[arm]]
    leads = [x["lead_days"] for x in detected]
    hit, false, miss = counts["hit"], counts["false_alarm"], counts["miss"]
    return {
        "scheduled": len(rows),
        "resolved": len(rows) - counts["unresolved"],
        "alerts": sum(r[arm]["alert"] for r in rows),
        "unresolved_alerts": sum(r[arm]["alert"] and r["status"] == "unresolved" for r in rows),
        "hits": hit,
        "false_alarms": false,
        "misses": miss,
        "correct_negatives": counts["correct_negative"],
        "unresolved": counts["unresolved"],
        "precision": hit / (hit + false) if hit + false else None,
        "recall": hit / (hit + miss) if hit + miss else None,
        "eligible_distinct_events": len(events),
        "distinct_events_hit": len(detected),
        "distinct_events_missed": len(events) - len(detected),
        "first_hit_lead_days": leads,
        "first_hit_timing": {
            s: sum(x["timing"] == s for x in detected)
            for s in ("before_quarter", "during_quarter_before_end", "on_or_after_quarter_end")
        },
        "median_first_hit_lead_days": median(leads) if leads else None,
        "opportunity_hit_lead_days": [r["lead_days"] for r in rows if r[arm]["result"] == "hit"],
    }


def paired(rows: list[dict], events: list[dict]) -> dict:
    discordant = {arm: [] for arm in ("text", "trend")}
    for row in rows:
        for arm, other in (("text", "trend"), ("trend", "text")):
            if row[arm]["result"] == "false_alarm" and not row[other]["alert"]:
                discordant[arm].append(
                    {k: row[k] for k in ("cik", "issuer", "origin", "sector")}
                    | {"reason": row[arm]["reason"]}
                )
    return {
        "matched_resolved_company_quarters": sum(r["status"] != "unresolved" for r in rows),
        "both_detected_events": sum(bool(e["text"] and e["trend"]) for e in events),
        "text_only_events": [e for e in events if e["text"] and not e["trend"]],
        "trend_only_events": [e for e in events if e["trend"] and not e["text"]],
        "text_only_false_alarms": discordant["text"],
        "trend_only_false_alarms": discordant["trend"],
        "net_additional_text_false_alarms": len(discordant["text"]) - len(discordant["trend"]),
    }


def score_panel(
    schedule: list[dict], decisions: dict, anchors: dict, facts: dict, disclosures: dict
) -> dict:
    alerts = checked_alerts(schedule, decisions)
    if set(anchors) != {(r["origin"], r["cik"]) for r in schedule}:
        raise ValueError("Missing or extraneous anchor")
    companies = {r["cik"] for r in schedule}
    if set(facts) != companies or not set(disclosures) <= companies:
        raise ValueError("Unexpected or missing issuer fact set (empty history must be explicit)")
    indices = {cik: quarter_index(qs) for cik, qs in facts.items()}
    rows, distinct = [], {}
    for cell in sorted(schedule, key=lambda r: (r["cutoff_us_eastern"], r["cik"])):
        cik, origin, sector = cell["cik"], cell["origin"], cell["sector"]
        outcome = resolve(
            cell["cutoff_us_eastern"], anchors[origin, cik], indices[cik], disclosures.get(cik, {})
        )
        row = {**cell, **outcome}
        eligible = outcome["status"] == "positive"
        if eligible:
            key = cik, outcome["event_end"]
            event = distinct.setdefault(
                key,
                {
                    **{k: cell[k] for k in ("cik", "issuer", "sector")},
                    "start": outcome["event_start"],
                    "end": outcome["event_end"],
                    "disclosure": disclosures[cik][outcome["event_end"]],
                    "eligible_origins": [],
                    **dict.fromkeys(ARMS),
                },
            )
            event["eligible_origins"].append(origin)
        for arm in ARMS:
            reason = alerts.get((origin, sector, arm, cik))
            alert = reason is not None
            if eligible:
                label = "hit" if alert else "miss"
            elif outcome["status"] == "unresolved":
                label = "unresolved"
            else:
                label = "false_alarm" if alert else "correct_negative"
            row[arm] = {"alert": alert, "reason": reason, "result": label}
            if eligible and alert and event[arm] is None:
                event[arm] = first_warning(row, arm)
        rows.append(row)
    events = list(distinct.values())
    groups = {}
    for sector in ["all", *sorted({r["sector"] for r in rows})]:
        part = [r for r in rows if sector == "all" or r["sector"] == sector]
        observed = [e for e in events if sector == "all" or e["sector"] == sector]
        complete = [
            r
            for r in part
            if r["evidence_status"] == "complete"
            and r["trend_available"]
            and r["status"] != "unresolved"
        ]
        eligible_complete = {(r["cik"], r["event_end"]) for r in complete if r["status"] == "positive"}
        complete_events = []
        for e in observed:
            if (e["cik"], e["end"]) not in eligible_complete:
                continue
            eligible_rows = [
                r
                for r in complete
                if r["cik"] == e["cik"] and r["event_end"] == e["end"] and r["status"] == "positive"
            ]
            filtered = dict(e, eligible_origins=[r["origin"] for r in eligible_rows])
            for arm in ARMS:
                first = next((r for r in eligible_rows if r[arm]["alert"]), None)
                filtered[arm] = first_warning(first, arm) if first else None
            complete_events.append(filtered)
        groups[sector] = {
            "paired_complete_inputs": paired(complete, complete_events),
            "by_arm": {arm: summarize(part, observed, arm) for arm in ARMS},
            "unresolved_reasons": dict(
                Counter(r["reason"] for r in part if r["status"] == "unresolved")
            ),
            "paired_text_trend": paired(part, observed),
        }
    return {"groups": groups, "eligible_distinct_events": events, "rows": rows}


def save_report(root: Path, result: dict) -> None:
    (root / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fields = (
        "origin",
        "cutoff_us_eastern",
        "cik",
        "issuer",
        "sector",
        "period_end",
        "evidence_status",
        "status",
        "reason",
        "event_start",
        "event_end",
        "first_disclosure",
        "lead_days",
    )
    with (root / "scored_company_quarters.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*fields, *ARMS])
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow({**{f: row[f] for f in fields}, **{a: row[a]["result"] for a in ARMS}})


def score(root: Path) -> dict:
    from run_industry_watch import trend_rates, verify_lock

    verify_lock(root)
    schedule_file = DATA / "company_quarters.csv"
    roster_lock = read(DATA / "selection.json")["outputs_sha256"]["company_quarters.csv"]
    if sha256(schedule_file.read_bytes()).hexdigest() != roster_lock:
        raise ValueError("Changed registered observation schedule")
    with schedule_file.open(encoding="utf-8", newline="") as stream:
        schedule = list(csv.DictReader(stream))
    if len(schedule) != 432 or len({r["cik"] for r in schedule}) != 36:
        raise ValueError("Invalid 36-company/432-slot schedule")
    decisions, anchors = {}, {}
    for origin in sorted({r["origin"] for r in schedule}):
        responses = read(root / origin / "alerts.json")
        if responses["origin"] != origin:
            raise ValueError("Wrong response origin")
        for decision in responses["decisions"]:
            key = origin, decision["sector"], decision["arm"]
            if key in decisions:
                raise ValueError("Duplicate response for a sector/arm")
            decisions[key] = decision["alerts"]
        trend = read(root / "trend_inputs" / f"{origin}.json")
        issuers = {c["cik"]: c for c in trend["issuers"]}
        for company in read(root / "evidence" / f"{origin}.json")["companies"]:
            key = origin, company["cik"]
            if key in anchors:
                raise ValueError("Duplicate evidence anchor")
            anchor = {k: company.get(k) for k in ("period_end", "status")}
            if anchor["status"] in {"stale", "missing_anchor"}:
                anchor["unresolved_reason"] = anchor["status"]
            anchor["trend_available"] = (
                not anchor.get("unresolved_reason")
                and trend_rates(issuers[key[1]], anchor["period_end"], trend["cutoff"]) is not None
            )
            anchors[key] = anchor
    scorer = root / "scorer"
    files = [root / "prediction_lock.json", scorer / "quarters.json", scorer / "disclosures.json"]
    disclosures = read(files[2])
    result = score_panel(schedule, decisions, anchors, read(files[1]), disclosures)
    expected = {(r["cik"], r["event_end"]) for r in result["rows"] if r["event_end"]}
    supplied = {(cik, end) for cik, entries in disclosures.items() for end in entries}
    if supplied != expected:
        raise ValueError(
            f"Missing or extraneous explicit crossing investigations: {sorted(supplied ^ expected)}"
        )
    result["sha256"] = {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in files}
    result["scorer_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    save_report(root, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="?", default=DATA / "run")
    print(json.dumps(score(parser.parse_args().run)["groups"]["all"]["by_arm"], ensure_ascii=False))
