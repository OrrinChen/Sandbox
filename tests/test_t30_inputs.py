import csv
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_t30_inputs as builder


def source(end, filed, accession):
    return {"reportDate": end, "filingDate": filed, "accessionNumber": accession}


def test_calendar_uses_filings_known_before_the_planning_date():
    records = [
        source("2020-03-31", "2020-05-05", "a"),
        source("2020-06-30", "2020-08-07", "b"),
        source("2020-09-30", "2020-11-06", "c"),
        source("2020-12-31", "2021-02-17", "d"),
    ]
    planned = builder.project(date(2022, 1, 1), records)
    assert planned["calendar_status"] == "scheduled"
    assert planned["cutoff"] == "2021-12-02"
    assert planned["projected_target_start"] == "2022-01-01"
    later = [*records, source("2020-12-31", "2021-11-06", "changed")]
    assert builder.project(date(2022, 1, 1), later) == planned
    assert not builder.project(date(2022, 1, 1), records[1:])["cutoff"]


def test_weekly_calendar_is_explicitly_projected():
    records = [
        source("2020-05-30", "2020-07-01", "a"),
        source("2020-08-29", "2020-10-01", "b"),
        source("2020-11-28", "2021-01-04", "c"),
        source("2021-02-27", "2021-04-02", "d"),
    ]
    projected = builder.project(date(2022, 1, 1), records)
    assert projected["calendar_method"] == "comparable_weekday"
    assert projected["projected_target_start"] == "2022-02-27"
    assert projected["cutoff"] == "2022-01-28"


def test_locked_inputs_cover_all_rows_and_disjoint_cohorts():
    data = builder.DATA
    builder.verify_inputs(data / "development")
    with (data / "development/schedule.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 288
    records = [
        json.loads(
            (data / f"development/packets/{r['wave']}/{r['cik']}.json").read_bytes()
        )
        for r in rows
    ]
    for r, p in zip(rows, records):
        if r["cutoff"]:
            assert (
                date.fromisoformat(r["projected_target_start"])
                - date.fromisoformat(r["cutoff"])
            ).days == 30
            assert (
                r["calendar_source_latest_filed"] <= r["calendar_asof"] <= r["cutoff"]
            )
        if p["status"] == "complete":
            assert [v["id"] for v in p["text"]["records"]] == list("ABCDE")
            assert all(v["date"] <= r["cutoff"] for v in p["text"]["records"])
            assert len(p["historical_sales"]["quarters"]) == 2
            assert all(
                v["filed"] <= r["cutoff"] for v in p["historical_sales"]["quarters"]
            )
    assert len(builder.table(data / "formal/companies.csv")) == 108
    previous = {
        r["cik"]
        for panel in (builder.OLD, builder.JOINT)
        for r in builder.table(panel / "companies.csv")
    }
    formal = {r["cik"] for r in builder.table(data / "formal/companies.csv")}
    assert formal.isdisjoint(previous)
    assert len(builder.table(data / "formal/schedule.csv")) == 2160


def test_existing_seals_refuse_different_bytes(tmp_path):
    path = tmp_path / "lock.json"
    builder.seal(path, b"one")
    builder.seal(path, b"one")
    with pytest.raises(ValueError, match="Locked content changed"):
        builder.seal(path, b"two")
    assert sha256(path.read_bytes()).hexdigest() == sha256(b"one").hexdigest()


def test_statement_fallback_requires_matching_quarter_and_two_comparables():
    pytest.importorskip("lxml")
    from audit_t30_public_inputs import face_line

    statement = b"""<table><tr><td>For the three months ended June 30, 2020 2019</td></tr>
    <tr><td>Revenue</td><td> $30,037,227 </td><td> $16,121,929 </td></tr></table>"""
    amounts = [30037227, 16121929]
    assert face_line(statement, "2020-06-30", amounts)
    assert (
        face_line(
            statement.replace(b"three months", b"six months"), "2020-06-30", amounts
        )
        is None
    )
    assert face_line(statement, "2020-06-30", amounts[::-1]) is None


def test_snapshot_cik_range_uses_string_order_and_both_representations(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    from prepare_t30_metadata import METADATA, select_shard

    cik = "0000021344"
    values = {key: ["a", "b"] for key in METADATA}
    values.update(cik=[cik, str(int(cik))], form=["10-K", "10-Q"])
    batch = pa.table(values)
    folder = tmp_path / "submissions-part-00001.parquet"
    pq.write_table(batch, folder)
    data = folder.read_bytes()
    (tmp_path / "submissions-part-00001.footer").write_bytes(data)
    item = {"size": len(data), "path": "sec/submissions/filings/part-00001.parquet"}
    result = select_shard(item, METADATA, {cik, str(int(cik))}, tmp_path, "submissions")
    assert [r["cik"] for r in result] == [cik, str(int(cik))]


def test_boundary_audit_rejects_added_symbol_in_real_model_input(tmp_path):
    from audit_t30_boundaries import audit_days
    from run_t30_watch import case_key, schedule

    data = builder.DATA / "development"
    first = sorted(schedule(data), key=lambda r: (r["wave"], r["cutoff"]))
    row = next(r for r in first if r["cutoff"])
    wave, cutoff = row["wave"], row["cutoff"]
    same_day = [r for r in first if (r["wave"], r["cutoff"]) == (wave, cutoff)]
    scheduled = [
        (r, json.loads((data / "packets" / (case_key(r) + ".json")).read_bytes()))
        for r in same_day
    ]
    src = data / "forecasts/days" / wave / cutoff
    dest = tmp_path / "forecasts/days" / wave / cutoff
    dest.mkdir(parents=True)
    for file in src.iterdir():
        if file.suffix == ".json":
            (dest / file.name).write_bytes(file.read_bytes())
    live = json.loads((dest / "text_input.json").read_bytes())
    entry = next(iter(live["sectors"].values()))["companies"][0]
    entry["outcome"] = "leak"
    (dest / "text_input.json").write_text(json.dumps(live))
    receipt = {"days": {f"{wave}/{cutoff}": builder.digest(src / "lock.json")}}
    (tmp_path / "forecasts/prediction_lock.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Public data boundary failed"):
        audit_days(tmp_path, {(wave, cutoff): scheduled})


def test_private_metadata_keeps_asof_partition_when_recent_coverage_is_missing(
    tmp_path,
):
    from prepare_t30_scorer_metadata import FIELDS, add_recent

    cik = "0000000001"
    p = {key: ["", "", ""] for key in FIELDS if key != "cik"}
    p.update(
        accessionNumber=["too_early", "new_quarter", "too_late"],
        filingDate=["2026-10-26", "2026-10-27", "2026-11-25"],
        form=["8-K", "10-Q", "8-K/A"],
        items=["2.02", "", "2.02"],
    )
    (tmp_path / f"CIK{cik}.json").write_text(json.dumps({"filings": {"recent": p}}))
    records = {}
    result = add_recent(cik, None, tmp_path, "cached", records, "2026-11-24")
    assert records.keys() == {"new_quarter"}
    assert result["records_in_requested_tail"] == 1
    assert result["last_filing_in_issuer_source"] == "2026-11-25"
