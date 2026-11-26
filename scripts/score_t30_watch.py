"""Resolve named T−30 targets using private evidence only after a verified replay."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from industry_disclosures import (
    archive_manifest,
    capture,
    checked_review,
    validate_source,
)
from industry_revenue import histories, panel_revenue_tags
from industry_score import (
    below_threshold,
    fiscal_window,
    quarter_index,
    validated_disclosure,
)
from run_industry_watch import digest, load, seal
from run_t30_watch import (
    ARMS,
    DATA,
    bucket,
    case_key,
    days,
    schedule,
    verify_predictions,
)


def label(row, source, quarters, disclosures):
    result = {
        "status": "unresolved",
        "reason": None,
        "actual_start": None,
        "actual_end": None,
        "days_to_start": None,
        "disclosure_date": None,
        "days_to_disclosure": None,
        "prior_yoy_pct": None,
        "target_yoy_pct": None,
        "disclosure_url": None,
    }
    if row["calendar_status"] != "scheduled" or source["status"] != "complete":
        result["reason"] = (
            source["status"]
            if row["calendar_status"] == "scheduled"
            else "calendar_unavailable"
        )
        return result
    by_end, by_start = quarters
    matches = [
        q
        for start, q in by_start.items()
        if abs(days(start, row["projected_target_start"])) <= 14
    ]
    if len(matches) != 1:
        result["reason"] = "unverified_target_calendar"
        return result
    target = matches[0]
    start, end = target["start"], target["end"]
    gap = days(start, row["cutoff"])
    result.update(actual_start=start, actual_end=end, days_to_start=gap)
    if gap < 30:
        result["reason"] = "actual_lead_under_30_days"
        return result
    horizon = fiscal_window(source["period_end"], by_end, by_start)
    if end not in {q["end"] for q in horizon[1:]}:
        result["reason"] = "outside_verified_two_quarter_horizon"
        return result
    prev_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    previous = by_end.get(prev_end)
    if previous is None:
        result["reason"] = "missing_preceding_quarter"
        return result
    before, current = below_threshold(previous), below_threshold(target)
    for key, q, known in (
        ("prior_yoy_pct", previous, before),
        ("target_yoy_pct", target, current),
    ):
        if known is not None:
            result[key] = format(
                (Decimal(str(q["sales"])) / Decimal(str(q["year_ago_sales"])) - 1)
                * 100,
                ".4f",
            )
    if before is True or current is False:
        result.update(status="negative", reason="no_new_crossing")
        return result
    if before is None or current is None:
        result["reason"] = "missing_comparable_sales"
        return result
    disclosure = disclosures.get(end, {})
    publication = validated_disclosure(disclosure, target)
    if publication is None:
        result["reason"] = "unverified_first_disclosure"
        return result
    gap = (publication - date.fromisoformat(row["cutoff"])).days
    result.update(
        status="positive" if gap > 0 else "negative",
        reason="undisclosed_new_crossing" if gap > 0 else "already_disclosed",
        disclosure_url=disclosure["url"],
        disclosure_date=publication.isoformat(),
        days_to_disclosure=gap,
    )
    return result


def all_cases(data, facts, labels):
    indices = {cik: quarter_index(qs) for cik, qs in facts.items()}
    rows, candidates = [], {}
    for row in schedule(data):
        cik = row["cik"]
        source = load(data / "packets" / (case_key(row) + ".json"))
        outcome = label(row, source, indices.get(cik, ({}, {})), labels.get(cik, {}))
        rows.append({**row, **outcome})
        if outcome["reason"] in {
            "undisclosed_new_crossing",
            "already_disclosed",
            "unverified_first_disclosure",
        }:
            end = outcome["actual_end"]
            if (cik, end) in candidates:
                raise ValueError("Duplicate named target in the selected fiscal waves")
            candidates[cik, end] = {
                "cik": cik,
                "issuer": row["issuer"],
                "sector": row["sector"],
                **indices[cik][0][end],
            }
    return rows, candidates


def prepare(data, forecasts, dest, cache=None):
    verify_predictions(data, forecasts)
    companies = sorted({r["cik"] for r in schedule(data)})
    existing_facts = {}
    for old in ("cross_industry_watch", "joint_watch_dev"):
        loc = DATA.parent / old / "run/scorer"
        for cik, qs in load(loc / "quarters.json").items():
            if cik in companies:
                existing_facts[cik] = qs
    facts = {}
    if cache:
        if data.name == "formal" and (cache / "ready.json").is_file():
            seal(dest / "metadata_coverage.json", load(cache / "ready.json"))
        tags = {
            **panel_revenue_tags(DATA.parent / "joint_watch_dev"),
            **panel_revenue_tags(data),
        }
        facts = histories(cache, [{"cik": c} for c in companies], "2026-11-24", tags)
    for cik in companies:
        # Earlier audited values override matching source periods; keep new company histories.
        indexed = {}
        for r in sorted(
            facts.get(cik, []),
            key=lambda x: (x["end"], x["latest_filed"], x["source_accessions"]),
        ):
            indexed.setdefault(r["end"], r)  # first original filing for a fiscal period
        indexed.update({r["end"]: r for r in existing_facts.get(cik, [])})
        facts[cik] = [indexed[k] for k in sorted(indexed)]
    if not cache and any(not facts[c] for c in companies):
        raise ValueError(
            "Missing private fiscal reports; supply --cache after prediction lock"
        )
    seal(dest / "quarters.json", facts)
    _, candidates = all_cases(data, facts, {})
    labels = {}
    for old in ("cross_industry_watch", "joint_watch_dev"):
        loc = DATA.parent / old / "run/scorer"
        registry = load(loc / "disclosures.json")
        for (cik, end), q in candidates.items():
            prior = registry.get(cik, {}).get(end)
            if prior and prior.get("date"):
                validate_source(q, prior, f"{cik}_{end}")
                labels.setdefault(cik, {})[end] = prior
    seal(dest / "existing_disclosures.json", labels)
    seal(
        dest / "outstanding_cases.json",
        [q for (c, e), q in sorted(candidates.items()) if e not in labels.get(c, {})],
    )
    return len(candidates)


def decide_sources(data, forecasts, dest, cache, archives, reviews, identity, workers):
    verify_predictions(data, forecasts)
    cases = load(dest / "outstanding_cases.json")
    if not cases:
        return
    for directory in (archives, reviews):
        directory.mkdir(parents=True, exist_ok=True)
    fetch = None
    if data.name == "formal":
        from industry_evidence import download

        def fetch(url, path, contact):
            prefix = "https://www.sec.gov/Archives/edgar/data/"
            if not url.startswith(prefix):
                raise ValueError(f"Expected original EDGAR URL: {url}")
            try:
                download(
                    "https://edgar-mirror.sec-api.io/" + url[len(prefix) :],
                    path,
                    contact,
                )
            except OSError:
                download(url, path, contact)

        seal(
            dest / "disclosure_transport.json",
            {
                "primary": "Filing index and exhibit URLs in the manifest identify originals in EDGAR.",
                "retrieval": "The formal collector requests matching accession/filenames through the public EDGAR mirror or official SEC archives. SHA-256 refers to received bytes.",
                "mirror": "https://edgar-mirror.sec-api.io/",
            },
        )
    with ThreadPoolExecutor(workers) as pool:
        jobs = []

        def start_review(c):
            jobs.append(pool.submit(checked_review, c, reviews, archives))

        capture(
            cases,
            cache,
            archives,
            identity,
            fetch,
            on_ready=start_review,
            max_workers=max(6, workers),
        )
        archive_manifest(cases, archives, dest / "filing_inventory.json")
        for job in jobs:
            job.result()
    for c in cases:
        key = f"{c['cik']}_{c['end']}"
        record = checked_review(c, reviews, archives)
        validate_source(c, record, key)
        seal(dest / "disclosure_reviews" / (key + ".json"), record)


def rescue_sources(data, forecasts, dest, archives, reviews, workers):
    verify_predictions(data, forecasts)
    reviews.mkdir(parents=True, exist_ok=True)
    pending = []
    for c in load(dest / "outstanding_cases.json"):
        key = f"{c['cik']}_{c['end']}"
        initial = load(dest / "disclosure_reviews" / (key + ".json"))
        if initial.get("date") is None:
            pending.append((c, initial))
    with ThreadPoolExecutor(workers) as pool:
        list(
            pool.map(
                lambda pair: checked_review(pair[0], reviews, archives, pair[1]),
                pending,
            )
        )
    for c, _ in pending:
        key = f"{c['cik']}_{c['end']}"
        record = checked_review(c, reviews, archives)
        validate_source(c, record, key)
        seal(dest / "disclosure_rescues" / (key + ".json"), record)


def stats(rows):
    result = {
        "cases": len(rows),
        "resolved": sum(r["status"] != "unresolved" for r in rows),
        "qualified_events": sum(r["status"] == "positive" for r in rows),
        "unresolved_reasons": dict(
            Counter(r["reason"] for r in rows if r["status"] == "unresolved")
        ),
    }
    by_arm = {}
    for arm in ARMS:
        counts = Counter(r[arm]["result"] for r in rows)
        by_arm[arm] = {
            "alerts": sum(bool(r[arm]["reason"]) for r in rows),
            **{
                key: counts[key]
                for key in (
                    "hit",
                    "false_alarm",
                    "miss",
                    "correct_negative",
                    "unresolved_alert",
                    "unresolved_abstention",
                )
            },
            "days_to_start_at_hits": [
                r["days_to_start"] for r in rows if r[arm]["result"] == "hit"
            ],
            "days_to_disclosure_at_hits": [
                r["days_to_disclosure"] for r in rows if r[arm]["result"] == "hit"
            ],
        }
    result["by_arm"] = by_arm
    paired = {}
    for ctrl in ("text", "trend"):
        diffs = {}
        for state in ("hit", "false_alarm"):
            for a, b in (("joint", ctrl), (ctrl, "joint")):
                diffs[f"{a}_only_{state}"] = [
                    case_key(r)
                    for r in rows
                    if r[a]["result"] == state and r[b]["result"] != state
                ]
        diffs["observed_gate_pass"] = (
            by_arm["joint"]["hit"] > by_arm[ctrl]["hit"]
            and by_arm["joint"]["false_alarm"] <= by_arm[ctrl]["false_alarm"]
        )
        paired[ctrl] = diffs
    return {
        **result,
        "paired": paired,
        "observed_gate_pass_both": all(
            p["observed_gate_pass"] for p in paired.values()
        ),
    }


def withhold_unverified_onsets(rows, candidates, attestation):
    checks = {(c["cik"], c["end"]): c for c in attestation["checks"]}
    for row in rows:
        key = row["cik"], row["actual_end"]
        if key not in candidates:
            continue
        prior_end = (
            date.fromisoformat(row["actual_start"]) - timedelta(days=1)
        ).isoformat()
        if all(
            checks.get((row["cik"], end), {}).get("matches") is True
            for end in (prior_end, row["actual_end"])
        ):
            continue
        row.update(
            status="unresolved",
            reason="unverified_original_sales",
            disclosure_url=None,
            disclosure_date=None,
            days_to_disclosure=None,
        )


def checked_primary_review(case, selected, certified, key):
    if not certified.get("primary_source_reason") or not certified.get("coverage"):
        raise ValueError(f"Missing primary-source verification: {key}")
    validate_source(case, certified, key)
    checked_urls = set(certified["rechecked_sources"]) | {
        r["url"] for r in certified["coverage"]
    }
    if selected["url"] in checked_urls or not selected.get("date"):
        return certified
    return selected


def score(data, forecasts, private, out):
    lock = verify_predictions(data, forecasts)
    labels = load(private / "existing_disclosures.json")
    label_files = [
        private / "quarters.json",
        private / "existing_disclosures.json",
        private / "outstanding_cases.json",
    ]
    if data.name == "formal":
        label_files.extend(
            p
            for p in (
                private / "metadata_coverage.json",
                private / "disclosure_transport.json",
                private / "filing_inventory.json",
                private / "independent_audit.json",
            )
            if p.is_file()
        )
    for case in load(private / "outstanding_cases.json"):
        path = private / "disclosure_reviews" / f"{case['cik']}_{case['end']}.json"
        if not path.is_file():
            raise ValueError(f"First-disclosure investigation missing: {path.stem}")
        d = load(path)
        if not d.get("basis") or not d.get("coverage"):
            raise ValueError(f"First-disclosure review lacks evidence: {path.stem}")
        validate_source(case, d, path.stem)
        label_files.append(path)
        rescue = private / "disclosure_rescues" / path.name
        if d.get("date") is None and rescue.is_file():
            d = load(rescue)
            if not d.get("basis") or not d.get("coverage"):
                raise ValueError(f"Follow-up review lacks evidence: {rescue.stem}")
            validate_source(case, d, rescue.stem)
            label_files.append(rescue)
        adjudication = private / "disclosure_adjudications" / path.name
        if adjudication.is_file():
            d = load(adjudication)
            if (
                not d.get("adjudication_reason")
                or not d.get("basis")
                or not d.get("coverage")
            ):
                raise ValueError(
                    f"Adjudication lacks its source comparison: {path.stem}"
                )
            validate_source(case, d, path.stem)
            label_files.append(adjudication)
        primary = private / "primary_source_reviews" / path.name
        if primary.is_file():
            d = checked_primary_review(case, d, load(primary), path.stem)
            label_files.append(primary)
        labels.setdefault(case["cik"], {})[case["end"]] = d
    numeric_audit = private / "onset_amount_audit.json"
    if data.name == "formal" and not numeric_audit.is_file():
        raise ValueError(
            "Formal scoring requires source checks for each numerical onset"
        )
    rows, candidates = all_cases(data, load(private / "quarters.json"), labels)
    if numeric_audit.exists():
        attestation = load(numeric_audit)
        if attestation["prediction_sha256"] != digest(
            forecasts / "prediction_lock.json"
        ) or attestation["quarters_sha256"] != digest(private / "quarters.json"):
            raise ValueError(
                "Revenue audit belongs to different forecasts or private facts"
            )
        label_files.append(numeric_audit)
        withhold_unverified_onsets(rows, candidates, attestation)
    decisions = {}
    for day in lock["days"]:
        for arm, sector_decisions in load(
            forecasts / "days" / day / "decisions.json"
        ).items():
            for s in sector_decisions:
                for alert in s["alerts"]:
                    decisions[
                        arm, day.rsplit("/", 1)[-1], s["sector"], alert["cik"]
                    ] = alert["reason"]
    for r in rows:
        for arm in ARMS:
            reason = decisions.get((arm, r["cutoff"], bucket(r), r["cik"]))
            verdict = {
                "positive": ("miss", "hit"),
                "negative": ("correct_negative", "false_alarm"),
                "unresolved": ("unresolved_abstention", "unresolved_alert"),
            }[r["status"]][bool(reason)]
            r[arm] = {"reason": reason, "result": verdict}
    groups = {
        s: stats([r for r in rows if r["sector"] == s])
        for s in sorted({r["sector"] for r in rows})
    }
    result = {
        "overall": stats(rows),
        "by_sector": groups,
        "rows": rows,
        "prediction_sha256": digest(forecasts / "prediction_lock.json"),
        "scorer_files": {
            p.relative_to(private).as_posix(): digest(p) for p in label_files
        },
    }
    seal(out / "report.json", result)
    rows_csv = [
        {
            **{k: v for k, v in row.items() if k not in ARMS},
            **{a: row[a]["result"] for a in ARMS},
        }
        for row in rows
    ]
    import io

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows_csv[0]))
    writer.writeheader()
    writer.writerows(rows_csv)
    csv_path = out / "company_quarters.csv"
    payload = buf.getvalue().encode("utf-8")
    if csv_path.exists() and csv_path.read_bytes() != payload:
        raise ValueError("Scored CSV differs from its archived version")
    if not csv_path.exists():
        csv_path.write_bytes(payload)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "research", "rescue", "score"))
    parser.add_argument("--data", type=Path, default=DATA / "development")
    for opt in ("forecasts", "private", "out", "cache", "archives", "reviews"):
        parser.add_argument("--" + opt, type=Path)
    parser.add_argument("--identity")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    forecasts = args.forecasts or args.data / "forecasts"
    private = args.private or args.data / "scorer"
    if args.action == "prepare":
        print(
            "numerical candidates", prepare(args.data, forecasts, private, args.cache)
        )
    elif args.action == "rescue":
        if not args.archives or not args.reviews:
            parser.error("follow-up investigation needs --archives and --reviews")
        rescue_sources(
            args.data, forecasts, private, args.archives, args.reviews, args.workers
        )
    elif args.action == "research":
        if not all((args.cache, args.archives, args.reviews, args.identity)):
            parser.error(
                "source review needs --cache, --archives, --reviews and --identity"
            )
        decide_sources(
            args.data,
            forecasts,
            private,
            args.cache,
            args.archives,
            args.reviews,
            args.identity,
            args.workers,
        )
    else:
        print(
            json.dumps(
                score(args.data, forecasts, private, args.out or args.data / "results")[
                    "overall"
                ]
            )
        )
