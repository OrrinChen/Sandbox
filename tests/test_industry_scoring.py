from datetime import date, timedelta

import pytest


@pytest.fixture
def scoring(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import industry_score

    return industry_score


def quarter(start, end, sales):
    return dict(
        start=start,
        end=end,
        sales=sales,
        year_ago_sales="100",
        source_accessions=["fake-accession"],
        latest_filed=(date.fromisoformat(end) + timedelta(days=45)).isoformat(),
    )


def sample():
    return [
        quarter("2020-07-01", "2020-09-30", "105"),
        quarter("2020-10-01", "2020-12-31", "98"),
        quarter("2021-01-01", "2021-03-31", "95.00001"),
        quarter("2021-04-01", "2021-06-30", "95.00000"),
        quarter("2021-07-01", "2021-09-30", "93"),
        quarter("2021-10-01", "2021-12-31", "102"),
    ]


def disclosure(day):
    return dict(
        date=day,
        basis="explicit numeric guidance",
        url="https://example.test/issuer",
        coverage=["releases and presentations"],
    )


def test_exact_threshold_overlap_and_discordant_alarms(scoring):
    periods = [("2021Q1", "2021-03-31", "2020-12-31"), ("2021Q2", "2021-06-30", "2021-03-31")]
    facts = {"1": sample(), "2": [dict(q, sales="100") for q in sample()]}
    origins, anchors, decisions = [], {}, {}
    for o, cutoff, anchor in periods:
        for cik in facts:
            origins.append(dict(cik=cik, issuer=cik, origin=o, cutoff_us_eastern=cutoff, sector="test"))
            anchors[o, cik] = {
                "period_end": anchor,
                "status": "complete",
                "trend_available": o == "2021Q2",
            }
        for arm in scoring.ARMS:
            decisions[o, "test", arm] = []
    decisions["2021Q1", "test", "text"] = [{"cik": c, "reason": "primary source clue"} for c in facts]
    decisions["2021Q2", "test", "text"] = [dict(cik="1", reason="same episode")]
    decisions["2021Q2", "test", "trend"] = [dict(cik="2", reason="revenue trend")]
    result = scoring.score_panel(
        origins, decisions, anchors, facts, {"1": {"2021-06-30": disclosure("2021-07-12")}}
    )
    all_ = result["groups"]["all"]
    assert len(result["eligible_distinct_events"]) == 1
    assert all_["by_arm"]["text"]["hits"] == 2 and all_["by_arm"]["text"]["first_hit_lead_days"] == [103]
    assert all_["by_arm"]["trend"]["distinct_events_missed"] == 1
    assert all_["by_arm"]["metadata"]["misses"] == 2
    pair = all_["paired_text_trend"]
    assert (
        len(pair["text_only_events"])
        == len(pair["text_only_false_alarms"])
        == len(pair["trend_only_false_alarms"])
        == 1
    )
    assert (
        pair["net_additional_text_false_alarms"] == 0 and pair["matched_resolved_company_quarters"] == 4
    )
    assert all_["by_arm"]["text"]["first_hit_timing"] == {
        "before_quarter": 1,
        "during_quarter_before_end": 0,
        "on_or_after_quarter_end": 0,
    }
    # The first text hit has no pair of available past growth rates. In the
    # matched complete-input subset the same event's eligible alert is later.
    complete = all_["paired_complete_inputs"]
    assert complete["matched_resolved_company_quarters"] == 2
    assert complete["text_only_events"][0]["text"]["timing"] == "on_or_after_quarter_end"
    assert complete["text_only_events"][0]["text"]["lead_days"] == 12
    assert all_ == result["groups"]["test"]
    with pytest.raises(ValueError, match="Duplicate observation"):
        scoring.score_panel(origins + origins[:1], decisions, anchors, facts, {})


def test_missing_disclosure_known_boundary_and_nonconsecutive_dates(scoring):
    index = scoring.quarter_index(sample())
    a = dict(period_end="2021-03-31", status="complete")

    def resolve(disclosures=None):
        return scoring.resolve("2021-06-30", a, index, disclosures or {})

    assert resolve()["reason"] == "unverified_first_disclosure"
    assert resolve({"2021-06-30": disclosure("2021-06-30")})["status"] == "already_disclosed"
    with pytest.raises(ValueError, match="disclosure"):
        resolve({"2021-06-30": dict(disclosure("2021-06-30"), coverage=[])})
    # Both horizons remain above/continue below threshold when known. No new onset.
    a["period_end"] = "2021-06-30"
    assert resolve()["status"] == "absent"
    a["period_end"] = "2020-12-31"
    index = scoring.quarter_index([q for q in sample() if q["end"] != "2021-03-31"])
    result = resolve()
    assert result["status"] == "unresolved" and result["horizon"] == []
    a["unresolved_reason"] = "stale"
    assert resolve()["reason"] == "stale"


def test_missing_year_ago_does_not_create_crossing(scoring):
    qs = sample()
    anchor = dict(period_end="2020-12-31", status="incomplete")
    qs[2]["year_ago_sales"] = None
    result = scoring.resolve("2021-03-31", anchor, scoring.quarter_index(qs), {})
    assert result["status"] == "unresolved" and result["reason"] == "missing_comparable_revenue"
    # Missing second quarter after a verified first-quarter crossing still proves the target.
    qs = sample()[:4]
    result = scoring.resolve(
        "2021-06-30",
        dict(period_end="2021-03-31"),
        scoring.quarter_index(qs),
        {"2021-06-30": disclosure("2021-07-12")},
    )
    assert result["status"] == "positive" and result["lead_days"] == 12


def test_disclosure_archive_and_numeric_validation(scoring, tmp_path):
    import json
    import industry_disclosures as audit

    pytest.importorskip("lxml.html")
    h = b'<table><tr><td>1</td><td>Release</td><td><a href="/Archives/example.htm">x</a></td><td>EX-99.1</td></tr><tr><td>2</td><td>Archive</td><td><a href="x">xx</a></td><td>ZIP</td></tr></table>'
    assert [d["url"] for d in audit.index_documents(h, "https://www.sec.gov/abc/xyz-index.htm")] == [
        "https://www.sec.gov/Archives/example.htm"
    ]
    lines, _ = audit.excerpts(b"<div><p>Outlook for quarterly sales is $90 to $94.</p></div>")
    assert lines == [(0, "Outlook for quarterly sales is $90 to $94.")]
    c = dict(cik="1", end="2021-06-30", year_ago_sales="100", latest_filed="2021-08-02")
    d = dict(
        date="2021-06-01",
        url="https://example.test/update",
        basis="Quarter sales guidance",
        publication_date_evidence="Dated release",
        coverage=[{"url": "https://example.test/ir", "detail": "all prior releases"}],
        comparison_type="usd",
        upper_bound="95.00001",
    )
    path = tmp_path / "1_2021-06-30.json"
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="Invalid verified disclosure"):
        audit.import_sources([c], tmp_path, tmp_path / "label.json")
    path.write_text(json.dumps(dict(d, upper_bound="95")))
    audit.import_sources([c], tmp_path, tmp_path / "label.json")
    assert json.loads((tmp_path / "label.json").read_bytes())["1"]["2021-06-30"]["date"] == "2021-06-01"
    q = quarter("2020-07-01", "2020-09-30", "0")
    assert scoring.below_threshold(q) is True
    assert scoring.quarter_index([dict(q, start=None)])[1] == {}
