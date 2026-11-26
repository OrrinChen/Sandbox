"""Register issuer-relative fiscal observations and rebuild dated public inputs."""

from __future__ import annotations

import argparse
import calendar
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import build_cross_industry_panel as panel
import industry_evidence as evidence
import industry_revenue as revenue
import run_industry_watch as watch
from run_joint_watch import historical_sales

DATA = Path(__file__).with_name("t30_watch")
OLD = Path(__file__).with_name("cross_industry_watch")
JOINT = Path(__file__).with_name("joint_watch_dev")
SPLITS = {"development": (2022, 1, 8), "formal": (2021, 2, 20)}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def seal(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with NamedTemporaryFile(dir=path.parent) as temp:
            temp.write(content)
            temp.flush()
            try:
                os.link(temp.name, path)
                return
            except FileExistsError:
                pass
    if path.read_bytes() != content:
        raise ValueError(f"Locked content changed: {path}")


def lock_json(path, value):
    seal(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def table(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def csv_seal(path, rows):
    from io import StringIO

    buffer = StringIO()
    w = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    seal(path, buffer.getvalue().encode())


def waves(split):
    year, quarter, count = SPLITS[split]
    for i in range(count):
        offset = quarter - 1 + i
        y, q = year + offset // 4, 1 + offset % 4
        yield f"{y}Q{q}", date(y, 3 * q - 2, 1)


def register(root, raw_frame):
    parent = evidence.read(JOINT / "protocol.json")
    records = []
    with_inputs = evidence.read(OLD / "selection.json")["inputs"]
    for i, spec in enumerate(with_inputs, 1):
        file = raw_frame / f"2020q{i}-sub.txt"
        if digest(file) != spec["sha256"]:
            raise ValueError(f"Frozen 2020 sampling frame differs: {file}")
        with file.open(encoding="utf-8-sig", newline="") as f:
            records.extend(csv.DictReader(f, delimiter="\t"))
    past = [panel.select(records, i)[0] for i in (0, 6)]
    for roster, path in zip(past, (OLD, JOINT)):
        if [r["cik"] for r in roster] != [
            r["cik"] for r in table(path / "companies.csv")
        ]:
            raise ValueError("Prior roster mismatch")
    rosters = {"development": past[0], "formal": []}
    for skip in (12, 18, 24):
        rosters["formal"].extend(panel.select(records, skip)[0])
    for split, roster in rosters.items():
        rows = [
            {
                **r,
                "cohort": f"{r['sector']}-{(r['rank'] - (13 if split == 'formal' else 1)) // 6 + 1}",
            }
            for r in roster
        ]
        csv_seal(root / split / "companies.csv", rows)
    policy = {
        "version": "issuer-t30-v1",
        "parent_protocol_sha256": digest(JOINT / "protocol.json"),
        "circumstances": "Development reuses previously studied issuers and periods. Formal issuers use ranks 13 through 30, disjoint from either prior 36-issuer panel and the 6-issuer pilot. Historical model knowledge is possible.",
        "source_tables": with_inputs,
        "sampling": "First 2020 SEC roster with fixed sector/SIC rules, company eligibility and hash seed unchanged. Include every wave for every selected issuer; no replacement of missing or delisted firms.",
        "waves": {key: [w for w, _ in waves(key)] for key in SPLITS},
        "wave_assignment": "For each calendar quarter wave select prior-year fiscal period end + 1 closest to wave start + 40 days (within 46 days). Consider original SEC 10-Q/K filing dates up to wave start minus 60 days only. The most recent four distinct period ends before or on the source period identify month-end or fixed-weekday calendars. Each old period is mapped to at most one wave per issuer; ambiguous or duplicate targets are unresolved.",
        "calendar_projection": "For month-end calendars use the same month's first day one year later. For four period ends on the same weekday, move comparable fiscal start to the nearest matching weekday to its anniversary (possible 52/53-week drift). Source year must be the preceding comparable season. Otherwise calendar unavailable. Retain vintage filings, projected date and method. This is a prospectively computable expected date. Post-lock require unique actual target start within 14 days and actual lead at least 30 days for primary credit; report drift.",
        "cutoff": "Projected fiscal quarter start minus 30 calendar days, end of day America/New_York. A record cannot use a filing dated after its issuer's cutoff.",
        "inputs": parent["public_evidence"],
        "industry_slots_B_C": parent["industry_slots_B_C"],
        "trend": parent["trend"],
        "historical_sales": "Latest two consecutive quarters as reported, same-filing prior-year comparators and filing dates. Form 10-K Q4 subtract original Q3 year-to-date when appropriate. No later amendments.",
        "freshness": "Latest original 10-Q/K filed by cutoff; maximum period age 185 days and filing age 135 days. Unavailable/stale/partial text or missing historical comparisons are retained as unscorable matched opportunities.",
        "budget": "Fixed six-issuer cohorts per sector-wave. Stream dated decisions earliest first with at most two warnings over the whole cohort-wave per arm. Enforce joint decisions only among the same cutoff; no later packet or competitor ranking passed into an earlier decision. Zero alerts permitted.",
        "outcome": parent["outcome"],
        "first_disclosure": parent["first_disclosure"],
        "target": "Count only the named target fiscal quarter, inside the two following fiscal quarters from the then-filed anchor, with actual lead >= 30 and first verified explicit disclosure strictly later than cutoff. Retain misses, documented negatives, date drift and unknowns individually. Preserve all negative quarters and all issued alerts, including status of unscorable alerts.",
        "locking": "Register roster, protocol, and dates before preparing packets. Seal all reader packets and all predictions before future labels are opened. No filled-in or substituted firms, chronological or per-company leakage, and no post-hoc resizing the formal sample to achieve 100 events.",
    }
    lock_json(root / "protocol.json", policy)
    files = ["protocol.json", *(f"{s}/companies.csv" for s in SPLITS)]
    lock_json(root / "registration_lock.json", {f: digest(root / f) for f in files})


def verify(root, lock_path):
    for name, value in evidence.read(root / lock_path).items():
        if digest(root / name) != value:
            raise ValueError(f"Hash mismatch: {name}")


def verify_inputs(data: Path) -> None:
    root, split = data.parent, data.name
    for lock in (
        "registration_lock.json",
        f"{split}/schedule_lock.json",
        f"{split}/input_lock.json",
    ):
        verify(root, lock)
    rows = table(data / "schedule.csv")
    keys = [f"{split}/packets/{r['wave']}/{r['cik']}.json" for r in rows]
    expected = {
        *keys,
        "registration_lock.json",
        "prediction_experiment.json",
        f"{split}/schedule_lock.json",
        f"{split}/provenance.json",
    }
    if split == "formal":
        expected.update(
            f"{split}/{name}_sources.json"
            for name in ("filing", "companyfacts", "submissions")
        )
    if (
        len(keys) != len(set(keys))
        or set(evidence.read(data / "input_lock.json")) != expected
    ):
        raise ValueError("Input lock incomplete or duplicate company-wave")


def register_readers(root):
    verify(root, "registration_lock.json")
    lock_json(
        root / "prediction_experiment.json",
        {
            "registration_sha256": digest(root / "registration_lock.json"),
            "prompt_sha256": "4a2170f471a9953424385d3db6a936428083064b09d0ebbbefd77b50745e5e24",
            "readers": "Same Codex model, effort and tools disabled for filing-only and joint arms. Stream current day's available companies only, with outstanding alert slots. Model sessions isolated across cutoff, arm and wave.",
            "mechanical": "For the targeted fiscal quarter use projection step 1 when forecast start follows filed anchor by one day; step 2 when 71 to 120 days later. Use the preceding growth and target growth as projected for those steps. Within a day sort new crossings by smallest target projected growth then CIK, across no more than the remaining cohort-wave slots.",
        },
    )


def filing_metadata(cache, cik, identity, through):
    base = cache / f"{cik}-submissions.json"
    prefix = "https://data.sec.gov/submissions/"
    fetch(prefix + "CIK" + cik + ".json", base, identity)
    index = evidence.read(base)["filings"]
    parts = [index["recent"]]
    for page in index["files"]:
        if page["filingFrom"] <= through and page["filingTo"] >= "2017-01-01":
            file = cache / page["name"]
            fetch(prefix + page["name"], file, identity)
            parts.append(evidence.read(file))
    records = {}
    for part in parts:
        for i, form in enumerate(part["form"]):
            end, filed = part["reportDate"][i], part["filingDate"][i]
            if (
                form not in revenue.FORMS
                or not end
                or not "2017-01-01" <= filed <= through
                or end > filed
            ):
                continue
            f = {
                k: part[k][i]
                for k in (
                    "filingDate",
                    "reportDate",
                    "acceptanceDateTime",
                    "form",
                    "primaryDocument",
                    "primaryDocDescription",
                    "accessionNumber",
                )
            }
            acc = f["accessionNumber"].replace("-", "")
            f["url"] = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{f['primaryDocument']}"
            )
            records[f["accessionNumber"]] = f
    return sorted(
        records.values(),
        key=lambda x: (x["reportDate"], x["filingDate"], x["accessionNumber"]),
    )


def fetch(url, path, identity, compressed=False):
    if not path.exists():
        if not identity:
            raise FileNotFoundError(
                f"Missing cached source {path.name}. Supply --identity for acquisition."
            )
        evidence.download(url, path, identity, compressed)


def anniversary(d, years):
    year = d.year + years
    return d.replace(year=year, day=min(d.day, calendar.monthrange(year, d.month)[1]))


def project(wave_start, records):
    asof = wave_start - timedelta(days=60)
    center = wave_start + timedelta(days=40)
    prev = anniversary(center, -1)
    known = {}
    for f in records:
        if f["filingDate"] <= asof.isoformat():
            known[date.fromisoformat(f["reportDate"])] = f
    eligible = [d for d in known if abs((d + timedelta(days=1) - prev).days) <= 46]
    base = dict(
        calendar_asof=asof.isoformat(),
        calendar_source_accessions="",
        calendar_source_latest_filed="",
        calendar_status="unavailable",
        calendar_method="",
        projected_target_start="",
        cutoff="",
    )
    if not eligible:
        return base
    end = min(eligible, key=lambda d: (abs((d + timedelta(days=1) - prev).days), d))
    history = sorted(d for d in known if d <= end)[-4:]
    if len(history) != 4 or any(
        not 70 <= (b - a).days <= 119 for a, b in zip(history, history[1:])
    ):
        return base
    start = end + timedelta(days=1)
    expected = anniversary(start, 1)
    if all(d.day == calendar.monthrange(d.year, d.month)[1] for d in history):
        method = "calendar_month_end"
    elif len({d.weekday() for d in history}) == 1:
        method = "comparable_weekday"
        expected += timedelta(days=((start.weekday() - expected.weekday() + 3) % 7) - 3)
    else:
        return base
    cutoff = expected - timedelta(days=30)
    if cutoff < asof:
        raise ValueError("Target projection used a filing after forecast cutoff")
    return {
        **base,
        "calendar_status": "scheduled",
        "calendar_source_accessions": "|".join(
            known[d]["accessionNumber"] for d in history
        ),
        "calendar_source_latest_filed": max(known[d]["filingDate"] for d in history),
        "calendar_method": method,
        "projected_target_start": expected.isoformat(),
        "cutoff": cutoff.isoformat(),
    }


def schedules(root, split, cache, identity):
    verify(root, "registration_lock.json")
    roster = table(root / split / "companies.csv")
    cache.mkdir(parents=True, exist_ok=True)
    wave_list = list(waves(split))
    through = (wave_list[-1][1] + timedelta(days=100)).isoformat()

    def issuer_schedule(r):
        records = filing_metadata(cache, r["cik"], identity, through)
        rows = []
        seen = set()
        for wave, first in wave_list:
            cal = project(first, records)
            if cal["projected_target_start"]:
                if cal["projected_target_start"] in seen:
                    cal.update(
                        calendar_status="unavailable",
                        calendar_method="duplicate_previous_target",
                        projected_target_start="",
                        cutoff="",
                    )
                else:
                    seen.add(cal["projected_target_start"])
            rows.append(
                {
                    "wave": wave,
                    **{k: r[k] for k in ("cohort", "sector", "cik", "issuer")},
                    **cal,
                }
            )
        return rows

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [row for bucket in pool.map(issuer_schedule, roster) for row in bucket]
    rows.sort(key=lambda r: (r["wave"], r["cohort"], r["cik"]))
    file = f"{split}/schedule.csv"
    csv_seal(root / file, rows)
    lock_json(
        root / split / "schedule_lock.json",
        {f: digest(root / f) for f in ["registration_lock.json", file]},
    )
    print(split, len(rows), Counter(r["calendar_status"] for r in rows), flush=True)


def issuer_inputs(root, split, cache, identity, current):
    cik = current[0]["cik"]
    dated = [x["cutoff"] for x in current if x["cutoff"]]
    records = filing_metadata(cache, cik, identity, max(dated)) if dated else []
    reports = [
        {
            "end": f["reportDate"],
            "filed": f["filingDate"],
            "form": f["form"],
            "accn": f["accessionNumber"],
        }
        for f in records
    ]
    if reports:
        fetch(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            cache / f"{cik}-companyfacts.json",
            identity,
        )
    facts = (
        revenue.revenue_facts(cache, cik, {x["accn"] for x in reports})
        if reports
        else {}
    )
    series = revenue.as_reported(reports, facts)
    known_extractions = {}
    paths, provenance = [], []
    evidence.write(cache / (cik + "-filings.json"), records)
    with TemporaryDirectory() as temp:
        temp = Path(temp)
        for row in current:
            day = row["cutoff"]
            f = evidence.anchor(records, day) if day else None
            if (
                f
                and revenue.gap(day, f["reportDate"]) <= 185
                and revenue.gap(day, f["filingDate"]) <= 135
            ):
                fetch(
                    f["url"],
                    cache / (f["accessionNumber"] + ".html.gz"),
                    identity,
                    True,
                )
            evidence.build_origin(
                row["wave"],
                [{**row, "cutoff_us_eastern": day}],
                cache,
                temp,
                known_extractions,
            )
            el = evidence.read(temp / (row["wave"] + ".json"))
            co = el["companies"][0]
            text = watch.projections(el, [row])["text"]["companies"][0]
            fresh = co["status"] not in {"stale", "missing_anchor"}
            av = (
                [
                    x
                    for x in series
                    if x["latest_filed"] <= day and x["end"] <= co["period_end"]
                ]
                if fresh
                else []
            )
            anchor = co["period_end"] if fresh else None
            hist = historical_sales(
                {"anchor": anchor, "quarters": av[-2:]}, anchor, day
            )
            state = co["status"] if day else "calendar_unavailable"
            if state == "complete" and hist["status"] != "complete":
                state = "incomplete_trend"
            packet = {
                k: row[k]
                for k in (
                    "wave",
                    "cohort",
                    "sector",
                    "cik",
                    "issuer",
                    "cutoff",
                    "projected_target_start",
                )
            }
            packet.update(
                status=state,
                period_end=co["period_end"],
                filing_date=co["filing_date"],
                text=text,
                historical_sales=hist,
            )
            rel = f"{split}/packets/{row['wave']}/{cik}.json"
            lock_json(root / rel, packet)
            paths.append(rel)
            provenance.append(
                {
                    "wave": row["wave"],
                    "cik": cik,
                    "status": state,
                    "period_end": co["period_end"],
                    "filing_date": co["filing_date"],
                    "accession": co["accession"],
                    "source_url": co["source_url"],
                    "document_sha256": co.get("document_sha256"),
                    "locators": [
                        {k: v[k] for k in ("id", "locator", "selection")}
                        for v in co["slots"]
                    ],
                    "historical_source_accessions": [
                        q["source_accessions"] for q in av[-2:]
                    ],
                    "historical_tags": [q["tag"] for q in av[-2:]],
                }
            )
    return paths, provenance


def inputs(root, split, cache, identity, workers):
    verify(root, "registration_lock.json")
    verify(root, f"{split}/schedule_lock.json")
    rows = table(root / split / "schedule.csv")
    roster = table(root / split / "companies.csv")

    def one_issuer(r):
        group = [x for x in rows if x["cik"] == r["cik"]]
        return issuer_inputs(root, split, cache, identity, group)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        finish_inputs(root, split, list(pool.map(one_issuer, roster)))


def finish_inputs(root, split, groups):
    paths, provenance = [], []
    for found, rows_found in groups:
        paths.extend(found)
        provenance.extend(rows_found)
    file = f"{split}/provenance.json"
    lock_json(root / file, provenance)
    if split == "formal":
        names = [
            f"{split}/{k}_sources.json"
            for k in ("filing", "companyfacts", "submissions")
        ]
        receipts = {
            r["accession"]: r["source_sha256"] for r in evidence.read(root / names[0])
        }
        observed = {
            r["accession"]: r["document_sha256"]
            for r in provenance
            if r["document_sha256"]
        }
        if observed != receipts:
            raise ValueError("Filing acquisition and extraction hashes differ")
        paths.extend(names)
    paths.extend(
        [
            "registration_lock.json",
            "prediction_experiment.json",
            f"{split}/schedule_lock.json",
            file,
        ]
    )
    lock_json(
        root / split / "input_lock.json", {n: digest(root / n) for n in sorted(paths)}
    )
    print(split, len(provenance), Counter(x["status"] for x in provenance), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["register", "schedule", "inputs", "verify"])
    parser.add_argument("--root", type=Path, default=DATA)
    parser.add_argument("--raw-frame", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--identity")
    parser.add_argument("--split", choices=list(SPLITS), default="development")
    parser.add_argument("--workers", type=int, default=4)
    opt = parser.parse_args()
    if opt.action == "register":
        if not opt.raw_frame:
            parser.error("register requires --raw-frame")
        register(opt.root, opt.raw_frame)
        register_readers(opt.root)
    elif opt.action == "verify":
        verify_inputs(opt.root / opt.split)
    else:
        if not opt.cache:
            parser.error("schedule and inputs require --cache")
        if opt.action == "schedule":
            schedules(opt.root, opt.split, opt.cache, opt.identity)
        else:
            inputs(opt.root, opt.split, opt.cache, opt.identity, opt.workers)
