from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_joint_watch as joint


def fixture():
    cutoff = "2024-09-30"
    cik = "100"
    row = {"cik": cik, "sector": "food", "issuer": "Test"}
    slots = [{"id": i, "title": "10-Q", "date": "2024-08-15", "text": "Original " + i} for i in "ABCDE"]
    evidence = {
        "origin": "2024Q3",
        "cutoff": cutoff,
        "companies": [{**row, "status": "complete", "period_end": "2024-06-30", "slots": slots}],
    }
    qs = [
        {
            "end": end,
            "sales": sales,
            "latest_filed": filed,
            "year_ago_sales": 100,
            "private_dummy": "must not appear",
        }
        for end, sales, filed in (
            ("2023-12-31", 112, "2024-02-15"),
            ("2024-03-31", 103, "2024-04-25"),
            ("2024-06-30", 99, "2024-08-15"),
        )
    ]
    trends = {
        "origin": "2024Q3",
        "cutoff": cutoff,
        "issuers": [{**row, "anchor": "2024-06-30", "quarters": qs}],
    }
    return [row], evidence, trends


def test_joint_changes_only_history_and_has_same_two_observations_as_trend():
    rows, evidence, trends = fixture()
    packets = joint.packets(evidence, trends, rows)
    richer = deepcopy(packets["joint"])
    numeric = richer["companies"][0].pop("historical_sales")
    assert richer == packets["text"]
    assert numeric["status"] == "complete"
    assert [q["yoy_percent"] for q in numeric["quarters"]] == ["3.0000", "-1.0000"]
    assert all(
        set(q)
        == {"quarter_end", "filed", "reported_sales_usd", "year_ago_reported_sales_usd", "yoy_percent"}
        for q in numeric["quarters"]
    )


def test_newer_filing_rejected_and_nonconsecutive_periods_explicit():
    rows, evidence, trends = fixture()
    q = trends["issuers"][0]["quarters"]
    del q[1]
    result = joint.packets(evidence, trends, rows)["joint"]["companies"][0]["historical_sales"]
    assert result["status"] == "incomplete" and len(result["quarters"]) == 1
    q[-1]["latest_filed"] = "2024-10-01"
    with pytest.raises(ValueError, match="later"):
        joint.packets(evidence, trends, rows)
