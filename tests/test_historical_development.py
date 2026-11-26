from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_historical_development
    return run_historical_development


def test_history_panel_dates_and_separation(runner, tmp_path):
    from history_cases_companies import build as companies
    from history_cases_policy import build as policy
    from history_cases_studies import build as studies

    events = companies() + policy() + studies()
    late = deepcopy(events)
    late[0]["questions"][0]["evidence"][0]["published"] = "2100-01-01"
    with pytest.raises(ValueError, match="late source"):
        runner.build_packets(late)
    too_early = deepcopy(events)
    forecast = next(q for e in too_early for q in e["questions"] if q.get("forecast"))
    forecast["forecast"]["resolution_date"] = forecast["cutoff"]
    with pytest.raises(ValueError, match="resolution"):
        runner.build_packets(too_early)
    runner.freeze(tmp_path)
    labels = {x["row"]:x for x in runner.read(tmp_path/"private/labels.json")}
    assert len(labels) == 32
    for batch in runner.BATCHES:
        name = f"inputs-{batch}.json"
        rows = runner.read(tmp_path/"initial"/name)
        controls = runner.read(tmp_path/"memory"/name)
        assert len(rows) == len({r["event"] for r in rows}) == 8
        assert controls == [{**r, "evidence": []} for r in rows if labels[r["row"]]["famous"]]
        for r in rows:
            assert set(r) <= {"row", "event", "cutoff", "question", "evidence", "forecast"}
            assert [e["ref"] for e in r["evidence"]] == list("ABCDE")
            assert all(e["published"] <= r["cutoff"] for e in r["evidence"])
    assert runner.forecast_result({"forecast_pct": 70}, 0)["brier"] == pytest.approx(0.49)


def test_history_replay_content_control_and_audit(runner, tmp_path):
    runner.freeze(tmp_path)
    labels = {x["row"]:x for x in runner.read(tmp_path/"private/labels.json")}
    def answer(r):
        gold = labels[r["row"]]["gold"]
        return {"row":r["row"], "choice":gold["choice"], "value":gold["value"], "citations":gold["citations"][0],
                **({"forecast_pct":50} if "forecast" in r else {})}
    for batch in runner.BATCHES:
        rows = runner.read(tmp_path/"initial"/f"inputs-{batch}.json")
        outputs = [answer(r) for r in rows]
        if batch == 1:
            outputs[0]["citations"] = []
        runner.write(tmp_path/"initial"/f"responses-{batch}.json",outputs)
    # The comparison packets must be produced independently of private scoring labels.
    private = tmp_path/"private/labels.json"
    hidden = private.rename(tmp_path/"held.json")
    runner.lock_initial(tmp_path)
    hidden.rename(private)
    for batch in runner.BATCHES:
        for stage in ("retry", "audit", "memory"):
            rows = runner.read(tmp_path/stage/f"inputs-{batch}.json")
            out = [answer(r) for r in rows]
            for r,a in zip(rows,out):
                if stage == "memory":
                    a["citations"] = []
                if stage == "audit":
                    fix = r["initial_answer"]["citations"] != a["citations"]
                    a.update(decision="revise" if fix else "keep", issues=[
                        {"field":"citations","ref":a["citations"][0],"why":"Missing required support."}
                    ] if fix else [])
            runner.write(tmp_path/stage/f"responses-{batch}.json",out)
    runner.score(tmp_path)
    report = runner.read(tmp_path/"report.json")
    assert report["overall"]["initial_failed"] == report["overall"]["localized_and_repaired"] == 1
    assert report["overall"]["content_correct"]["initial"] == 32
    control = report["no_material"]["comparison"]
    assert control["without_text"] == control["with_text"] == control["questions"]
    assert report["forecasts"]["scores"]["initial"]["mean_brier"] == .25
    tampered = tmp_path/"retry/responses-1.json"
    tampered.write_text(tampered.read_text()+" ")
    with pytest.raises(ValueError):
        runner.score(tmp_path)
