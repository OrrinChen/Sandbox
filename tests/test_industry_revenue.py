import json
import runpy
from pathlib import Path

module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/industry_revenue.py"))


def test_fourth_quarter_uses_original_filing_and_matching_ytd_comparison():
    filings = [
        dict(end="2020-09-30", filed="2020-11-05", form="10-Q", accn="q3"),
        dict(end="2020-12-31", filed="2021-03-02", form="10-K", accn="fy"),
        dict(end="2020-09-30", filed="2021-04-01", form="10-Q", accn="late"),
    ]
    facts = {
        "fy": {"Revenues": {("2020-01-01", "2020-12-31"): 400, ("2019-01-01", "2019-12-31"): 350}},
        "q3": {"Revenues": {("2020-01-01", "2020-09-30"): 300, ("2019-01-01", "2019-09-30"): 230}},
        "late": {"Revenues": {("2020-01-01", "2020-09-30"): 200}},
    }
    year_end = module["as_reported"](filings, facts)[1]
    assert year_end["sales"] == 100 and year_end["year_ago_sales"] == 120
    assert year_end["start"] == "2020-10-01" and year_end["source_accessions"] == ["fy", "q3"]
    facts["q3"]["Revenues"] = {("2020-01-05", "2020-09-30"): 300}
    assert module["as_reported"](filings, facts)[1]["sales"] is None


def test_recorded_trend_inputs_exclude_future_filings_and_align_to_anchor():
    root = Path(__file__).resolve().parents[1] / "scripts/cross_industry_watch/run/trend_inputs"
    paths = sorted(root.glob("*.json"))
    assert len(paths) == 12
    for path in paths:
        packet = json.loads(path.read_bytes())
        assert len({r["cik"] for r in packet["issuers"]}) == 36
        for row in packet["issuers"]:
            quarters = row["quarters"]
            if not row["anchor"]:
                assert quarters == []
                continue
            assert [q["end"] for q in quarters] == sorted(q["end"] for q in quarters)
            assert quarters[-1]["end"] == row["anchor"]
            assert all(q["end"] <= q["latest_filed"] <= packet["cutoff"] for q in quarters)
            assert all(q["source_accessions"] for q in quarters)
