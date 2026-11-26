"""Independently search for earliest disclosures and compare scorer evidence after the global lock."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import build_t30_inputs as study
from industry_disclosures import checked_review, validate_source
from run_t30_watch import load, verify_predictions


def source_key(c):
    return f"{c['cik']}_{c['end']}"


def read_candidates(data):
    verify_predictions(data, data / "forecasts")
    cases = load(data / "scorer/outstanding_cases.json")
    if len({source_key(c) for c in cases}) != len(cases):
        raise ValueError("Duplicate private onset")
    return cases


def independent_review(data, dest, workers):
    """The independent searcher receives only privately determined numeric periods and source IDs."""
    cases = read_candidates(data)
    dest.mkdir(parents=True, exist_ok=True)

    def check(case):
        # No first-review answers, user alerts, or unrelated cross-case context.
        # Search independently on public websites without building a second EDGAR archive.
        verdict = checked_review(case, dest, None)
        if not verdict.get("basis") or not verdict.get("coverage"):
            raise ValueError(f"Review has no documented sources: {source_key(case)}")
        return source_key(case)

    with ThreadPoolExecutor(workers) as pool:
        for k in pool.map(check, cases):
            print("Independent public source search", k, flush=True)


def primary_source(private, key):
    path = private / "disclosure_reviews" / (key + ".json")
    first = load(path)
    followup = private / "disclosure_rescues" / path.name
    if not first["date"] and followup.exists():
        return followup, load(followup)
    return path, first


def adjudicate(data, separate, workspace, archives, workers):
    cases = read_candidates(data)
    private = data / "scorer"
    workspace.mkdir(parents=True, exist_ok=True)
    jobs = []
    for c in cases:
        key = source_key(c)
        _, primary = primary_source(private, key)
        second = checked_review(c, separate, None)
        if primary["date"] != second["date"]:
            jobs.append((c, primary, second))

    def reconcile(job):
        c, first, second = job
        key = source_key(c)
        # No alert outputs or outcome-by-method scores enter the adjudicator.
        dossier = {
            "scope": "Two independent source searches disagree or one could not prove a date. Re-open both actual primary sources, verify publication, target quarter and the entire stated upper bound. Inspect all earlier potentially material disclosures, especially the reasons a reviewer could not verify an earlier date. Document the exact source and numerical period that resolves the difference. If doubts remain, return a null date.",
            "research_a": first,
            "research_b": second,
        }
        decision = checked_review(c, workspace, archives, dossier)
        if not decision.get("basis") or not decision.get("coverage"):
            raise ValueError("Incomplete adjudication: " + key)
        result = dict(
            decision,
            adjudication_reason=decision["basis"],
            reviewed_dates=[first["date"], second["date"]],
        )
        study.lock_json(private / "disclosure_adjudications" / (key + ".json"), result)
        return key

    with ThreadPoolExecutor(workers) as pool:
        for key in pool.map(reconcile, jobs):
            print("Adjudicated independent reviews", key, flush=True)


def corroborate(data, private_reviews, numeric, private):
    cases = read_candidates(data)
    facts = load(private / "quarters.json")
    checks = load(numeric)
    if checks["prediction_sha256"] != study.digest(
        data / "forecasts/prediction_lock.json"
    ) or checks["quarters_sha256"] != study.digest(private / "quarters.json"):
        raise ValueError("Numeric statement evidence belongs to another vintage")
    statements = {(v["cik"], v["end"]): v for v in checks["checks"]}
    counts = Counter()
    results = []
    for c in sorted(cases, key=source_key):
        fn = source_key(c) + ".json"
        path, first = primary_source(private, source_key(c))
        independent = checked_review(c, private_reviews, None)
        for value in (first, independent):
            if not value["basis"] or not value["coverage"]:
                raise ValueError(f"Unauditable source assessment for {fn}")
        prior_end = (date.fromisoformat(c["start"]) - timedelta(days=1)).isoformat()
        qs = {r["end"]: r for r in facts[c["cik"]]}
        p, n = qs[prior_end], qs[c["end"]]
        # Exact integer/decimal multiplication, using independent checks of both original statements.
        dates = (p["end"], n["end"])
        evidence = [statements[c["cik"], d] for d in dates]
        exact = all(s["matches"] for s in evidence)
        whether_crossing = (
            Decimal(str(p["sales"])) * 100 > Decimal(str(p["year_ago_sales"])) * 95
            and Decimal(str(n["sales"])) * 100 <= Decimal(str(n["year_ago_sales"])) * 95
        )
        if not whether_crossing:
            raise ValueError(f"Candidate fails independent threshold computation: {fn}")
        dates_match = first["date"] == independent["date"]
        if first["date"] and dates_match:
            status = "two_independent_searches_same_date"
        elif dates_match:
            status = "both_dates_unresolved"
        elif first["date"] and independent["date"]:
            status = "date_disagreement_requires_adjudication"
        elif first["date"]:
            status = "only_initial_search_verified_date"
        else:
            status = "only_independent_search_verified_date"
        adjudicated = None
        if not dates_match:
            resolution = private / "disclosure_adjudications" / fn
            adjudicated = load(resolution)
            validate_source(c, adjudicated, source_key(c))
        counts[status] += 1
        results.append(
            {
                "cik": c["cik"],
                "end": c["end"],
                "status": status,
                "onset_math_verified": whether_crossing,
                "both_original_quarter_pairs_verified": exact,
                "source_accessions": [s["accessions"] for s in evidence],
                "primary_review": str(path.relative_to(private)),
                "primary_date": first["date"],
                "primary_url": first["url"],
                "independent_review": independent,
                "adjudication": ("disclosure_adjudications/" + fn)
                if adjudicated
                else None,
                "adjudicated_date": adjudicated["date"]
                if adjudicated
                else first["date"],
            }
        )
    report = {
        "method": "Separate public source searches in new reader sessions received only the issuer and independently identified numerical target. Both sides had to substantiate the date, consolidated whole-range guidance or actuals, category and prior disclosure coverage. A null or differing date stays explicit. Source-window coverage still depends on the available issuer archive.",
        "prediction_sha256": study.digest(data / "forecasts/prediction_lock.json"),
        "numeric_audit_sha256": study.digest(numeric),
        "onsets": len(results),
        "both_original_quarters_verified": sum(
            r["both_original_quarter_pairs_verified"] for r in results
        ),
        "dates": dict(counts),
        "events": results,
    }
    study.lock_json(private / "independent_audit.json", report)
    return report


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=["review", "adjudicate", "compare"])
    cli.add_argument("--data", type=Path, required=True)
    cli.add_argument("--reviews", type=Path, required=True)
    cli.add_argument("--numeric", type=Path)
    cli.add_argument("--adjudications", type=Path)
    cli.add_argument("--archives", type=Path)
    cli.add_argument("--workers", type=int, default=5)
    a = cli.parse_args()
    if a.action == "review":
        independent_review(a.data, a.reviews, a.workers)
    elif a.action == "adjudicate":
        if not a.adjudications:
            cli.error("A separate adjudication workspace is required")
        adjudicate(a.data, a.reviews, a.adjudications, a.archives, a.workers)
    else:
        if not a.numeric:
            cli.error("Comparison requires the independent original statement audit")
        result = corroborate(a.data, a.reviews, a.numeric, a.data / "scorer")
        print({k: v for k, v in result.items() if k != "events"})
