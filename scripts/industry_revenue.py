"""Reconstruct reported quarterly revenue pairs from original SEC filing vintages."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).with_name("cross_industry_watch")
# Consolidated net sales, then consolidated total revenue. Contract revenue is a
# fallback only when the broader revenue concepts are absent from the filing.
TAGS = (
    "SalesRevenueNet",
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)
FORMS = {"10-Q", "10-K"}
# Manually verified field mapping from the two original consolidated statements.
# Both show the face line "REVENUES"; only the standardized XBRL tag changed.
VERIFIED_YTD_TAGS = {
    (
        "0001579910-21-000005",
        "0001579910-20-000019",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ): "RevenueFromContractWithCustomerIncludingAssessedTax",
}


def gap(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def submissions(cache: Path, cik: str, through: str) -> list[dict]:
    base = json.loads((cache / f"{cik}-submissions.json").read_bytes())["filings"]
    tables = [base["recent"]]
    for page in base["files"]:
        if page["filingFrom"] <= through and page["filingTo"] >= "2017-01-01":
            tables.append(json.loads((cache / page["name"]).read_bytes()))
    reports = {}
    for table in tables:
        for i, form in enumerate(table["form"]):
            filed, end = table["filingDate"][i], table["reportDate"][i]
            if form not in FORMS or not end or not "2017-01-01" <= filed <= through or end > filed:
                continue
            accn = table["accessionNumber"][i]
            reports[accn] = dict(end=end, filed=filed, form=form, accn=accn)
    return sorted(reports.values(), key=lambda r: (r["end"], r["filed"], r["accn"]))


def revenue_facts(cache: Path, cik: str, accessions: set[str]) -> dict:
    concepts = json.loads((cache / f"{cik}-companyfacts.json").read_bytes())["facts"].get("us-gaap", {})
    by_accession = defaultdict(lambda: defaultdict(dict))
    for tag in TAGS:
        for fact in concepts.get(tag, {}).get("units", {}).get("USD", []):
            accn = fact["accn"]
            if accn not in accessions or "start" not in fact:
                continue
            key = (fact["start"], fact["end"])
            amounts = by_accession[accn][tag]
            if key not in amounts:
                amounts[key] = fact["val"]
            elif amounts[key] != fact["val"]:
                amounts[key] = None
    return by_accession


def unique_period(values: dict, condition):
    selected = [
        (start, end, amount)
        for (start, end), amount in values.items()
        if amount is not None and condition(start, end)
    ]
    return selected[0] if len(selected) == 1 else None


def fiscal_fact(amounts, end: str, days: tuple[int, int], prior: bool = False):
    def eligible(start, last):
        distance = gap(end, last)
        matching = 350 <= distance <= 379 if prior else distance == 0
        return matching and days[0] <= gap(last, start) + 1 <= days[1]

    return unique_period(amounts, eligible)


def quarter_duration(days: int) -> bool:
    # Twelve-week Q1–Q3 can leave 16 or 17 weeks in the final quarter.
    return 70 <= days <= 112 or days == 119


def difference(annual, first_nine):
    if not annual or not first_nine or annual[0] != first_nine[0]:
        return None
    start = (date.fromisoformat(first_nine[1]) + timedelta(days=1)).isoformat()
    duration = gap(annual[1], start) + 1
    if not quarter_duration(duration):
        return None
    return start, annual[1], annual[2] - first_nine[2]


def as_reported(reports: list[dict], facts: dict, tags: tuple[str, ...] = TAGS) -> list[dict]:
    result = []
    for report in reports:
        end, accn = report["end"], report["accn"]
        row = dict(
            start=None,
            end=end,
            sales=None,
            year_ago_sales=None,
            source_accessions=[accn],
            latest_filed=report["filed"],
            tag=None,
            calculation=None,
        )
        report_facts = facts.get(accn, {})
        previous_q3 = [
            s
            for s in reports
            if s["form"] == "10-Q" and s["filed"] <= report["filed"] and 70 <= gap(end, s["end"]) <= 112
        ]
        q3 = previous_q3[-1] if previous_q3 else None
        for tag in tags:
            amounts = report_facts.get(tag, {})
            current = fiscal_fact(amounts, end, (70, 112))
            prior = fiscal_fact(amounts, end, (70, 112), prior=True)
            derivation = "reported_quarter"
            if not current and q3 and report["form"] == "10-K":
                nine_tag = VERIFIED_YTD_TAGS.get((accn, q3["accn"], tag), tag)
                nine = facts.get(q3["accn"], {}).get(nine_tag, {})
                current = difference(
                    fiscal_fact(amounts, end, (350, 379)),
                    fiscal_fact(nine, q3["end"], (245, 295)),
                )
                prior = difference(
                    fiscal_fact(amounts, end, (350, 379), prior=True),
                    fiscal_fact(nine, q3["end"], (245, 295), prior=True),
                )
                derivation = "fiscal_year_less_first_nine_months"
            if not current:
                continue
            if derivation == "fiscal_year_less_first_nine_months":
                row["source_accessions"].append(q3["accn"])
                row["first_nine_months_tag"] = nine_tag
            row.update(
                start=current[0],
                sales=current[2],
                year_ago_sales=prior[2] if prior else None,
                tag=tag,
                calculation=derivation,
            )
            break
        result.append(row)
    return result


def panel_revenue_tags(panel: Path) -> dict[str, tuple[str, ...]]:
    """Use a filing-verified net-sales face-line tag where standardized concepts disagree."""
    path = panel / "net_sales_tags.json"
    if not path.exists():
        return {}
    return {cik: (record["tag"],) for cik, record in json.loads(path.read_bytes()).items()}


def histories(cache: Path, companies: list[dict], through: str, tags_by_cik: dict | None = None) -> dict:
    result = {}
    for company in companies:
        cik = company["cik"]
        reports = submissions(cache, cik, through)
        factset = revenue_facts(cache, cik, {r["accn"] for r in reports})
        result[cik] = as_reported(reports, factset, (tags_by_cik or {}).get(cik, TAGS))
    return result


def trend_inputs(cache: Path, out: Path, panel: Path = DATA):
    schedule = list(csv.DictReader((panel / "company_quarters.csv").open()))
    companies = list(csv.DictReader((panel / "companies.csv").open()))
    history = histories(
        cache, companies, max(r["cutoff_us_eastern"] for r in schedule), panel_revenue_tags(panel)
    )
    out.mkdir(parents=True, exist_ok=True)
    for origin, cutoff in sorted({(r["origin"], r["cutoff_us_eastern"]) for r in schedule}):
        issuers = []
        for company in companies:
            cik = company["cik"]
            available = [r for r in history[cik] if r["latest_filed"] <= cutoff]
            anchor = available[-1] if available else None
            fresh = (
                anchor
                and gap(cutoff, anchor["end"]) <= 185
                and gap(cutoff, anchor["latest_filed"]) <= 135
            )
            issuers.append(
                dict(
                    cik=cik,
                    sector=company["sector"],
                    issuer=company["issuer"],
                    anchor=anchor["end"] if fresh else None,
                    quarters=available[-6:] if fresh else [],
                )
            )
        (out / f"{origin}.json").write_text(
            json.dumps(
                dict(origin=origin, cutoff=cutoff, issuers=issuers),
                separators=(",", ":"),
            )
            + "\n"
        )


def scorer_quarters(cache: Path, run: Path):
    from run_industry_watch import verify_lock

    # Verify every dated prediction before opening any resolution-period data.
    verify_lock(run)
    with (DATA / "companies.csv").open() as stream:
        companies = list(csv.DictReader(stream))
    series = histories(cache, companies, "2025-12-31")
    for cik, rows in series.items():
        # Maximum two fiscal quarters after the last registered cutoff.
        rows[:] = [q for q in rows if "2019-11-01" <= q["end"] <= "2024-08-15"]
        for q in rows:
            if q["source_accessions"][0] == "0001213900-21-047197":
                # The Lovesac filing's consolidated statements explicitly identify the
                # thirteen weeks ended August 1. The tagged start overlaps its Q1.
                q["xbrl_start"] = q["start"]
                q["start"] = "2021-05-03"
                q["calendar_evidence"] = (
                    "Thirteen weeks ended August 1, 2021; condensed consolidated statements "
                    "of operations, original filing 0001213900-21-047197."
                )
    # A directly reported quarter supersedes subtraction of rounded annual/YTD figures.
    for correction in json.loads((DATA / "run/scorer/reported_quarter_pairs.json").read_text()):
        q = next(q for q in series[correction["cik"]] if q["end"] == correction["end"])
        q["original_filing_pair"] = [q["sales"], q["year_ago_sales"]]
        q.update(
            sales=correction["sales"],
            year_ago_sales=correction["year_ago_sales"],
            calculation="direct_quarterly_earnings_release",
            latest_filed=correction["filed"],
            source_accessions=[correction["accession"]],
            direct_source=correction["url"],
        )
    path = run / "scorer" / "quarters.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(series, separators=(",", ":")) + "\n")


def download_cache(cache: Path, user_agent: str, panel: Path = DATA):
    """Opt-in acquisition of SEC Company Facts and submission metadata."""
    import time
    from urllib.request import Request, urlopen

    cache.mkdir(parents=True, exist_ok=True)

    def get(name: str, url: str):
        target = cache / name
        if target.exists():
            return json.loads(target.read_bytes())
        with urlopen(Request(url, headers={"User-Agent": user_agent}), timeout=60) as response:
            data = response.read()
        parsed = json.loads(data)
        target.write_bytes(data)
        time.sleep(0.25)
        return parsed

    with (panel / "companies.csv").open() as stream:
        for issuer in csv.DictReader(stream):
            cik = issuer["cik"]
            get(f"{cik}-companyfacts.json", f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
            url = "https://data.sec.gov/submissions/"
            meta = get(f"{cik}-submissions.json", f"{url}CIK{cik}.json")
            for page in meta["filings"]["files"]:
                if page["filingFrom"] <= "2025-12-31" and page["filingTo"] >= "2017-01-01":
                    get(page["name"], f"{url}{page['name']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sec_cache", type=Path, help="SEC companyfacts and submissions cache")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--scorer",
        action="store_true",
        help="export private quarter records after validating the run's global prediction lock",
    )
    parser.add_argument(
        "--fetch-with-user-agent",
        metavar="USER_AGENT",
        help="download missing public SEC inputs with identifying contact before building",
    )
    parser.add_argument("--panel", type=Path, default=DATA, help="registered panel for public inputs")
    opts = parser.parse_args()
    if opts.panel != DATA and opts.scorer:
        parser.error("Use the scoring command for the registered panel")
    if opts.fetch_with_user_agent:
        download_cache(opts.sec_cache, opts.fetch_with_user_agent, opts.panel)
    if opts.scorer:
        scorer_quarters(opts.sec_cache, opts.output)
    else:
        trend_inputs(opts.sec_cache, opts.output, opts.panel)
