"""Paired fiscal-start diagnostics on a synthetic, overlapping two-origin panel."""

from datetime import date, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def scorer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import joint_watch_score

    return joint_watch_score


def test_earlier_detection_pair_and_raw_fp_gate(scorer):
    quarters = []
    for start, end, amount in [
        ("2023-07-01", "2023-09-30", 100),
        ("2023-10-01", "2023-12-31", 100),
        ("2024-01-01", "2024-03-31", 100),
        ("2024-04-01", "2024-06-30", 95),
        ("2024-07-01", "2024-09-30", 92),
    ]:
        quarters.append(
            dict(
                start=start,
                end=end,
                sales=amount,
                year_ago_sales=100,
                latest_filed=(date.fromisoformat(end) + timedelta(days=40)).isoformat(),
                source_accessions=["synthetic-source"],
            )
        )
    schedule, decisions, anchors = [], {}, {}
    for origin, cutoff, end in [
        ("A", "2024-03-31", "2023-12-31"),
        ("B", "2024-04-01", "2024-03-31"),
    ]:
        for cik in ("win", "stable"):
            schedule.append(
                dict(
                    origin=origin,
                    cik=cik,
                    issuer=cik,
                    sector="s",
                    cutoff_us_eastern=cutoff,
                )
            )
            anchors[origin, cik] = {"period_end": end, "status": "complete"}
        for arm in scorer.ARMS:
            decisions[origin, "s", arm] = []

    def alarm(cik):
        return {"cik": cik, "reason": "filing clue"}

    decisions["A", "s", "joint"] = [alarm("win")]
    decisions["B", "s", "joint"] = [alarm("win")]
    decisions["B", "s", "text"] = [alarm("win"), alarm("stable")]
    facts = {"win": quarters, "stable": [dict(q, sales=100) for q in quarters]}
    labels = {
        "win": {
            "2024-06-30": dict(
                date="2024-05-02",
                url="https://issuer.invalid",
                basis="Q2 point guidance",
                coverage=[dict(url="https://issuer.invalid/prior", detail="simulated")],
                publication_date_evidence="simulated dateline",
                upper_bound="95",
                comparison_type="usd",
            )
        }
    }
    report = scorer.score_data(schedule, anchors, decisions, facts, labels)
    group = report["groups"]["all"]
    assert group["events_with_pre_start_opportunity"] == 1
    assert report["events"][0]["joint"]["days_before_quarter_start"] == 1
    assert report["events"][0]["text"]["days_before_quarter_start"] == 0
    assert group["observed_gate_pass_both"]
    assert group["by_arm"]["joint"]["hits"] == 2
    assert group["by_arm"]["joint"]["distinct_events_hit"] == 1
    assert group["by_arm"]["text"]["first_hit_timing"]["during_quarter_before_end"] == 1
    assert group["paired"]["text"]["net_additional_false_alarms"] == -1
    assert group["paired"]["trend"]["net_additional_false_alarms"] == 0
    decisions["A", "s", "joint"].append(alarm("stable"))
    result = scorer.score_data(schedule, anchors, decisions, facts, labels)["groups"][
        "all"
    ]
    assert not result["observed_gate_pass_both"]
    assert result["paired"]["text"]["observed_gate_pass"]
    assert not result["paired"]["trend"]["observed_gate_pass"]
    labels["win"]["2024-06-30"]["upper_bound"] = "96"
    with pytest.raises(ValueError, match="Invalid verified disclosure"):
        scorer.score_data(schedule, anchors, decisions, facts, labels)
    labels["win"]["2024-06-30"]["date"] = None
    unresolved = scorer.score_data(schedule, anchors, decisions, facts, labels)[
        "groups"
    ]["all"]
    assert unresolved["unresolved_reasons"] == {"unverified_first_disclosure": 2}
    assert unresolved["events_with_pre_start_opportunity"] == 0
    with pytest.raises(ValueError, match="investigation"):
        scorer.score_data(schedule, anchors, decisions, facts, {})
