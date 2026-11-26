"""Checks for the disjoint 2024 development panel and its public filing vintages."""

import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "scripts"


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def test_independent_roster_rank_and_document_disjointness():
    prior = BASE / "cross_industry_watch"
    panel = BASE / "joint_watch_dev"
    original = rows(prior / "companies.csv")
    selected = rows(panel / "companies.csv")
    issuers = {r["cik"] for r in selected}
    assert len(selected) == len(issuers) == 36
    assert not issuers.intersection(r["cik"] for r in original)
    for sector in {r["sector"] for r in original}:
        assert [int(r["rank"]) for r in selected if r["sector"] == sector] == list(range(7, 13))
    observations = rows(panel / "company_quarters.csv")
    assert len(observations) == len({(r["origin"], r["cik"]) for r in observations}) == 144
    assert {r["origin"] for r in observations} == {f"2024Q{i}" for i in range(1, 5)}

    def accessions(study):
        return {
            c["accession"]
            for f in (study / "run/evidence").glob("*.json")
            for c in json.loads(f.read_bytes())["companies"]
            if c.get("accession")
        }

    assert accessions(panel) and accessions(prior).isdisjoint(accessions(panel))


def test_joint_public_inputs_have_matching_cutoffs_and_anchors():
    panel = BASE / "joint_watch_dev"
    observations = rows(panel / "company_quarters.csv")
    for origin in sorted({r["origin"] for r in observations}):
        expected = [r for r in observations if r["origin"] == origin]
        evidence = json.loads((panel / "run/evidence" / f"{origin}.json").read_bytes())
        trend = json.loads((panel / "run/trend_inputs" / f"{origin}.json").read_bytes())
        assert evidence["origin"] == trend["origin"] == origin
        assert evidence["cutoff"] == trend["cutoff"] == expected[0]["cutoff_us_eastern"]
        assert [r["cik"] for r in expected] == [c["cik"] for c in evidence["companies"]]
        assert [r["cik"] for r in expected] == [c["cik"] for c in trend["issuers"]]
        for c, t in zip(evidence["companies"], trend["issuers"]):
            if c["status"] in {"stale", "missing_anchor"}:
                assert not t["anchor"] and not t["quarters"] and not c["slots"]
                continue
            assert t["anchor"] == c["period_end"] == t["quarters"][-1]["end"]
            assert all(q["end"] <= q["latest_filed"] <= trend["cutoff"] for q in t["quarters"])
            if c["status"] == "complete":
                assert [s["id"] for s in c["slots"]] == list("ABCDE")
            assert c["period_end"] <= c["filing_date"] <= evidence["cutoff"]
            assert all(s["date"] == c["filing_date"] and s["url"] == c["source_url"] for s in c["slots"])


def test_verified_net_sales_lines_and_53_week_comparator(monkeypatch):
    monkeypatch.syspath_prepend(str(BASE))
    from industry_revenue import difference, panel_revenue_tags

    tags = panel_revenue_tags(BASE / "joint_watch_dev")
    assert tags["0000935703"] == ("RevenueFromContractWithCustomerExcludingAssessedTax",)
    assert tags["0000024545"] == ("RevenueFromContractWithCustomerIncludingAssessedTax",)
    assert difference(("2021-12-26", "2022-12-31", 86392), ("2021-12-26", "2022-09-03", 58396)) == (
        "2022-09-04",
        "2022-12-31",
        27996,
    )


def test_quarter_audit_excludes_dimensional_and_non_usd_facts(monkeypatch):
    import pytest

    pytest.importorskip("lxml")
    monkeypatch.syspath_prepend(str(BASE))
    from audit_joint_quarters import parse_document

    raw = b"""<html><body>
    <xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <xbrli:unit id="v"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
    <xbrli:context id="all"><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate>
    <xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="part"><xbrli:entity><xbrli:segment></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate>
    <xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context>
    <table><tr><td>Net sales</td><td>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="all" unitRef="u" scale="3" decimals="-3">12</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="all" unitRef="u" scale="4" decimals="-4">1</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="all" unitRef="v" scale="3">11</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Revenues" contextRef="part" unitRef="u" scale="3">4</ix:nonFraction>
    </td></tr></table></body></html>"""
    assert parse_document(raw, {"Revenues"}) == {
        ("Revenues", "2024-01-01", "2024-03-31"): {12000: {"Net sales"}}
    }
