from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_industry_watch

    return run_industry_watch


def test_forecast_fresh_crossing_and_vintage(runner):
    def q(end, sales, filed):
        return dict(end=end, sales=sales, year_ago_sales=100, latest_filed=filed)

    quarters = [q("2022-03-31", 105, "2022-04-19"), q("2022-06-30", 100, "2022-08-01")]
    args = {"quarters": quarters}, "2022-06-30", "2022-09-30"
    assert runner.forecast(*args)[0] == -10
    quarters[0]["sales"] = 95
    assert runner.forecast(*args) is None
    quarters[1]["sales"] = 90
    assert runner.forecast(*args) is None
    quarters[1]["latest_filed"] = "2022-10-01"
    with pytest.raises(ValueError, match="contemporaneous"):
        runner.trend_rates(*args)


def test_metadata_projection_and_alert_budget(runner):
    rows = [dict(cik="01", sector="software", issuer="Co")]
    records = [dict(id=x, title="10-Q", date="2022-05-01", text=f"fact {x}") for x in "ABCDE"]
    company = dict(**rows[0], period_end="2022-03-31", status="complete", slots=records)
    evidence = dict(origin="2022Q2", cutoff="2022-06-30", companies=[company])
    packets = runner.projections(evidence, rows)
    assert packets["text"]["companies"][0]["records"] == records
    assert all(set(s) == {"id", "title", "date"} for s in packets["metadata"]["companies"][0]["records"])
    bad = deepcopy(evidence)
    bad["companies"][0]["slots"][0]["date"] = "2022-07-01"
    with pytest.raises(ValueError, match="as-of"):
        runner.projections(bad, rows)
    duplicates = [dict(cik="01", reason="reason")] * 2
    with pytest.raises(ValueError, match="Invalid alert"):
        runner.validate({"sectors": [{"sector": "software", "alerts": duplicates}]}, rows, {"01"})
