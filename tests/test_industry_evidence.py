"""Offline integrity checks for the cross-industry point-in-time source packets."""

import csv
from hashlib import sha256
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts" / "cross_industry_watch"
BUILDER = runpy.run_path(str(ROOT / "scripts" / "industry_evidence.py"))


def test_anchor_excludes_both_later_filing_and_later_period():
    def record(filed, end):
        return dict(
            filingDate=filed,
            reportDate=end,
            acceptanceDateTime=filed,
            accessionNumber=filed,
        )

    filings = [
        record("2022-02-28", "2021-12-31"),
        record("2022-03-30", "2022-01-31"),
        record("2022-04-01", "2022-03-01"),
        record("2022-03-15", "2022-04-30"),
    ]
    assert BUILDER["anchor"](filings, "2022-03-31") == filings[1]


def test_historical_span_excludes_guidance_and_accounting_definitions():
    keep = BUILDER["eligible_sentence"]
    assert keep(
        "Shipment volume decreased by 12% during the three months ended March 31, 2022."
    )
    assert not keep("Revenue was up 12% and we may experience weaker demand next year.")
    assert not keep(
        "Inventory was stated at the lower of cost or net realizable value."
    )


def test_frozen_evidence_matches_scheduled_companies_and_filing_dates():
    with (BASE / "company_quarters.csv").open() as file:
        schedule = list(csv.DictReader(file))
    reads = {}
    for origin in sorted({r["origin"] for r in schedule}):
        path = BASE / "run/evidence" / (origin + ".json")
        obj = json.loads(path.read_text())
        reads[origin] = sha256(path.read_bytes()).hexdigest()
        companies = obj["companies"]
        rows = [r for r in schedule if r["origin"] == origin]
        assert [(c["cik"], c["issuer"], c["sector"]) for c in companies] == [
            (r["cik"], r["issuer"], r["sector"]) for r in rows
        ]
        assert obj["origin"] == origin and obj["cutoff"] == rows[0]["cutoff_us_eastern"]
        for c in companies:
            if c["status"] in {"stale", "missing_anchor"}:
                assert not c["slots"]
                continue
            assert c["period_end"] <= c["filing_date"] <= obj["cutoff"]
            slots = c["slots"]
            assert (
                len(slots)
                == len({s["text"] for s in slots})
                == len({s["id"] for s in slots})
            )
            if c["status"] == "complete":
                assert [s["id"] for s in slots] == list("ABCDE")
            assert all(
                s["date"] == c["filing_date"]
                and s["url"] == c["source_url"]
                and s["title"] == c["title"]
                and s["locator"]
                for s in slots
            )
    assert len(reads) == 12
