from pathlib import Path

import pytest


@pytest.fixture
def pilot(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_retail_watch

    return run_retail_watch


def test_known_episode_and_overlapping_forecast_windows(pilot):
    dates = ["2022-04-30", "2022-07-30", "2022-10-29", "2023-01-28", "2023-04-29", "2023-07-29"]
    reports = ["2022-05-10", "2022-08-10", "2022-11-10", "2023-02-10", "2023-05-10", "2023-08-10"]
    # Already under threshold at Q1, continued at Q2, then recovers before a new exact -5% crossing.
    values = ["94", "90", "97", "95", "94", "98"]
    data = {
        "ticker": "TEST",
        "quarters": [
            {
                "id": k,
                "quarter_end": d,
                "report_date": r,
                "sales": v,
                "prior_year_sales": "100",
                "url": "https://example.test/source",
                "locator": "table",
            }
            for k, d, r, v in zip(pilot.QUARTERS, dates, reports, values)
        ],
        "disclosures": [
            {
                "id": "2022Q4",
                "date": "2022-11-23",
                "basis": "specific quarter guidance",
                "url": "https://example.test/guidance",
                "coverage": ["updates"],
            }
        ],
    }
    origins = pilot.read(pilot.DATA / "protocol.json")["origins"]
    rows, _ = pilot.evaluate_company(data, "TEST", origins)
    assert [r["status"] for r in rows] == ["absent", "positive", "already_disclosed", "absent"]
    assert rows[1]["days_to_disclosure"] == 84
    data["disclosures"][0]["date"] = None
    rows, _ = pilot.evaluate_company(data, "TEST", origins)
    assert [r["status"] for r in rows] == ["absent", "unresolved", "unresolved", "absent"]


def test_metadata_projection_and_prior_lock(pilot, tmp_path):
    pilot.register(tmp_path)
    pilot.prepare(tmp_path, "2022Q1")
    folder = tmp_path / "2022Q1"
    full = pilot.read(folder / "text/input.json")
    meta = pilot.read(folder / "metadata/input.json")
    assert full["prompt"] == meta["prompt"]
    assert len(full["companies"]) == len(meta["companies"]) == 6
    for a, b in zip(full["companies"], meta["companies"]):
        assert a["ticker"] == b["ticker"]
        assert len(a["records"]) == len(b["records"]) == 5
        assert b["records"] == [{k: s[k] for k in ("title", "published")} for s in a["records"]]
    with pytest.raises(FileNotFoundError):
        pilot.prepare(tmp_path, "2022Q2")
    for arm in pilot.ARMS:
        pilot.write(folder / arm / "response.json", {"origin": "2022Q1", "alerts": []})
    pilot.seal_alerts(tmp_path, "2022Q1")
    # Later data/labels are not needed to accept abstention and seal the earlier alerts.
    pilot.verify_hashes(tmp_path, pilot.read(folder / "alerts_lock.json"))
    path = folder / "metadata/response.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError):
        pilot.verify_hashes(tmp_path, pilot.read(folder / "alerts_lock.json"))


def test_budget_and_replay_units(pilot):
    spec = pilot.read(pilot.DATA / "protocol.json")

    def response(names):
        return {"origin": "2022Q1", "alerts": [{"ticker": t, "reason": "reason"} for t in names]}

    for names in (["HD", "HD"], ["HD", "LOW", "TGT"]):
        with pytest.raises(ValueError):
            pilot.alerts(response(names), spec, "2022Q1")
    assert pilot.alerts(response([]), spec, "2022Q1") == []
    rows = [
        {"text": {"result": s, "alert": a}, "days_to_disclosure": lead}
        for s, a, lead in (
            ("hit", True, 84),
            ("false_alarm", True, None),
            ("miss", False, 40),
            ("correct_negative", False, None),
        )
    ]
    result = pilot.summarize(rows, "text")
    assert result["precision"] == result["recall"] == 0.5 and result["lead_days"] == [84]


def test_original_recording_replays_into_a_clean_directory(pilot, tmp_path):
    run = tmp_path / "fresh"
    pilot.replay(run)
    saved = pilot.read(pilot.DATA / "recorded_alerts.json")
    assert pilot.digest(run / "prediction_lock.json") == saved["prediction_lock_sha256"]
    report = pilot.read(run / "report.json")
    assert len({(r["ticker"], r["origin"]) for r in report["rows"]}) == 24
    for arm in pilot.ARMS:
        totals = report["by_arm"][arm]
        assert (
            sum(totals[k] for k in ("hits", "false_alarms", "misses", "correct_negatives", "unresolved"))
            == 24
        )
    original = (run / "report.json").read_bytes()
    pilot.score(run)
    assert (run / "report.json").read_bytes() == original
    with pytest.raises(ValueError, match="empty destination"):
        pilot.replay(run)
