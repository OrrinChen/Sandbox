from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_t30_watch as run
import score_t30_watch as score
from industry_score import quarter_index


def test_disclosure_without_numeric_upper_bound_keeps_raw_source_and_withholds_date(
    tmp_path, monkeypatch
):
    import industry_disclosures as disclosure

    candidate = {"cik": "01", "end": "2023-03-31", "year_ago_sales": 100}
    key = "01_2023-03-31"
    record = {
        "date": "2023-01-30",
        "comparison_type": "yoy_percent",
        "upper_bound": None,
        "basis": "Expected mid-teens decrease, with no numeric endpoint.",
        "coverage": [
            {"url": "https://issuer.example/outlook", "detail": "Issuer outlook"}
        ],
    }
    run.seal(tmp_path / (key + ".json"), record)
    monkeypatch.setattr(disclosure, "research", lambda *args: key)
    verified = disclosure.checked_review(candidate, tmp_path, None)
    assert verified["date"] is None
    assert verified["raw_review"] == record
    assert verified["coverage"] == record["coverage"]
    assert run.load(tmp_path / (key + ".json")) == record


def test_paired_table_distinguishes_no_remaining_budget_from_abstention():
    from report_t30_pairs import paired_rows

    def row(cik, day, alert):
        r = {
            "cik": cik,
            "issuer": "Issuer " + cik,
            "wave": "2021Q2",
            "cohort": "m-1",
            "sector": "m",
            "cutoff": day,
            "actual_start": "2021-04-01",
            "target_yoy_pct": "1.0000",
            "disclosure_date": None,
            "disclosure_url": None,
            "days_to_start": 30,
            "days_to_disclosure": None,
            "reason": "no_new_crossing",
        }
        for arm in run.ARMS:
            r[arm] = {
                "reason": "warning" if arm == alert else None,
                "result": "false_alarm" if arm == alert else "correct_negative",
            }
        return r

    inputs = [
        row("01", "2021-02-25", "text"),
        row("02", "2021-02-25", "text"),
        row("03", "2021-03-02", "joint"),
    ]
    diffs = [r for r in paired_rows(inputs) if r["comparison"] == "joint_vs_text"]
    assert [
        (r["alerting_arm_slots_at_cutoff"], r["abstaining_arm_slots_at_cutoff"])
        for r in diffs
    ] == [(2, 2), (2, 2), (2, 0)]


def test_cannot_credit_date_based_only_on_unverified_transcript():
    candidate = {"cik": "01", "end": "2024-03-31"}
    credited = {"date": "2024-03-01", "url": "https://transcript.example/call"}
    official = {
        "date": None,
        "primary_source_reason": "Only third-party transcription was available.",
        "coverage": [
            {"url": "https://issuer.example/webcast", "detail": "Offline recording"}
        ],
        "rechecked_sources": [credited["url"]],
    }
    assert (
        score.checked_primary_review(candidate, credited, official, "case")["date"]
        is None
    )
    independent = {**credited, "url": "https://issuer.example/earlier-official-outlook"}
    assert (
        score.checked_primary_review(candidate, independent, official, "case")
        == independent
    )


def issuer(cik="01"):
    row = dict(
        cik=cik,
        issuer="Example",
        sector="food",
        cohort="food-1",
        wave="2024Q3",
        cutoff="2024-06-01",
        projected_target_start="2024-07-01",
        calendar_status="scheduled",
    )
    sales = [
        dict(
            quarter_end=end,
            filed=day,
            reported_sales_usd=s,
            year_ago_reported_sales_usd=100,
            yoy_percent=rate,
        )
        for end, day, s, rate in [
            ("2023-12-31", "2024-02-14", 106, "6.0000"),
            ("2024-03-31", "2024-04-10", 102, "2.0000"),
        ]
    ]
    return row, {
        **row,
        "period_end": "2024-03-31",
        "filing_date": "2024-04-10",
        "status": "complete",
        "text": {
            **{k: row[k] for k in ("cik", "issuer", "sector")},
            "records": [
                dict(
                    id=i,
                    title="Report",
                    date="2024-04-10",
                    text="Operating disclosure",
                    private_marker="private",
                )
                for i in "ABCDE"
            ],
        },
        "historical_sales": {"status": "complete", "quarters": sales},
    }


def test_target_specific_projection_and_private_inputs():
    row, src = issuer()
    assert run.trend_forecast(src)[0] == -6
    # First projection now crosses but the named second quarter is a continuation.
    src["historical_sales"]["quarters"][0]["reported_sales_usd"] = 111
    src["historical_sales"]["quarters"][0]["yoy_percent"] = "11.0000"
    assert run.trend_forecast(src) is None
    projected = run.project(row, src)
    assert (
        "private_marker" not in str(projected) and "historical_sales" not in projected
    )
    src["text"]["records"][0]["date"] = "2024-07-01"
    with pytest.raises(ValueError, match="contemporaneous"):
        run.project(row, src)


def quarters(start="2024-07-01", after=90):
    from datetime import date, timedelta

    previous_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    return quarter_index(
        [
            dict(
                start=s,
                end=e,
                sales=a,
                year_ago_sales=100,
                source_accessions=["test"],
                latest_filed=d,
            )
            for s, e, a, d in [
                ("2024-01-01", "2024-03-31", 102, "2024-04-10"),
                ("2024-04-01", previous_end, 104, "2024-07-21"),
                (start, "2024-09-30", after, "2024-11-03"),
            ]
        ]
    )


def test_no_early_warning_credit_for_wrong_quarter_short_lead_or_unknown_disclosure():
    row, src = issuer()
    assert score.label(row, src, quarters(after=97), {})["status"] == "negative"
    gap = score.label(row, src, quarters("2024-06-30"), {})
    assert gap["reason"] == "actual_lead_under_30_days" and gap["days_to_start"] == 29
    assert (
        score.label(row, src, quarters(), {})["reason"] == "unverified_first_disclosure"
    )
    announcement = {
        "date": "2024-11-02",
        "url": "https://issuer.example/results",
        "basis": "Q3 recorded sales 90 against 100",
        "coverage": ["issuer filings"],
    }
    resolved = score.label(row, src, quarters(), {"2024-09-30": announcement})
    assert (resolved["status"], resolved["days_to_start"]) == ("positive", 30)
    announced = score.label(
        row, src, quarters(), {"2024-09-30": {**announcement, "date": "2024-06-01"}}
    )
    assert announced["reason"] == "already_disclosed"
    out = {**src, "period_end": "2023-12-31"}
    assert (
        score.label(row, out, quarters(), {})["reason"]
        == "outside_verified_two_quarter_horizon"
    )


def test_stream_budget_and_replay_fail_on_excess_later_decision(tmp_path, monkeypatch):
    original, src = issuer()
    sources = []
    for c in ("01", "02"):
        row, s = issuer(c)
        run.seal(tmp_path / "packets" / f"{run.case_key(row)}.json", s)
        sources.append(row)

    def read_all(packet, output, registered, available, prompt):
        return {
            "sectors": [
                {
                    "sector": run.bucket(original),
                    "alerts": [{"cik": r["cik"], "reason": "test"} for r in registered],
                }
            ]
        }

    monkeypatch.setattr(run, "read_model", read_all)
    with pytest.raises(ValueError, match="remaining rolling"):
        run.decide_day(
            tmp_path,
            tmp_path / "out",
            original["cutoff"],
            sources,
            {(a, run.bucket(original)): 1 for a in run.ARMS},
            None,
        )
    r = deepcopy(sources[0])
    r["cutoff"] = "2024-05-01"
    with pytest.raises(ValueError, match="Registered case mismatch"):
        run.project(r, src)


def test_scorer_cannot_open_labels_until_replay_valid(monkeypatch, tmp_path):
    def fail_lock(*args):
        raise ValueError("broken prediction lock")

    monkeypatch.setattr(score, "verify_predictions", fail_lock)
    monkeypatch.setattr(
        score, "load", lambda p: pytest.fail(f"premature private read {p}")
    )
    with pytest.raises(ValueError, match="broken prediction lock"):
        score.score(tmp_path, tmp_path, tmp_path, tmp_path)


def test_numeric_candidate_with_unverified_prior_quarter_stays_unresolved():
    rows = [
        dict(
            cik="01",
            actual_start="2024-07-01",
            actual_end="2024-09-30",
            status="positive",
        )
    ]
    audit = {"checks": [{"cik": "01", "end": "2024-09-30", "matches": True}]}
    score.withhold_unverified_onsets(rows, {("01", "2024-09-30"): {}}, audit)
    assert rows[0]["status"] == "unresolved"
    assert rows[0]["reason"] == "unverified_original_sales"


def test_empty_or_overlapping_filing_inventories_launch_one_source_review_each(
    tmp_path, monkeypatch
):
    import industry_disclosures as disclosure
    import json

    cases = [
        {"cik": "1", "end": "2023-01-01"},
        {"cik": "2", "end": "2023-01-02"},
        {"cik": "2", "end": "2023-02-02"},
    ]
    monkeypatch.setattr(
        disclosure,
        "window_filings",
        lambda c, _: (
            [] if c["cik"] == "1" else [{"accession": "b"}, {"accession": "c"}]
        ),
    )
    monkeypatch.setattr(disclosure, "filing_record", lambda record, *_: record)
    started = []

    def ready(c):
        archived = json.loads((tmp_path / f"{c['cik']}_{c['end']}.json").read_bytes())
        assert archived["case"] == c
        started.append((c["cik"], c["end"]))

    disclosure.capture(cases, tmp_path, tmp_path, "fixture", on_ready=ready)
    assert sorted(started) == sorted((c["cik"], c["end"]) for c in cases)
