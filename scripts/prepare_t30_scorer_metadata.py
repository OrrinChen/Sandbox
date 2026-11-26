"""Build the private EDGAR filing inventory from existing snapshot shards after all predictions lock."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from urllib.request import Request, urlopen

import build_t30_inputs as study
from prepare_t30_metadata import FILES, METADATA, REVISION, REPO
from run_t30_watch import verify_predictions

FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"}
FIELDS = [*METADATA, "items"]
SNAPSHOT_THROUGH = "2026-10-26"


def selected_shards(directory, identifiers):
    """Check file presence for every matching row-group using the saved publisher footers."""
    import struct
    import pyarrow.parquet as pq

    sources = []
    for file in sorted(directory.glob("submissions-part-*.footer")):
        raw = file.read_bytes()
        length = struct.unpack("<I", raw[-8:-4])[0]
        metadata = pq.ParquetFile(BytesIO(b"PAR1" + raw[-8 - length :])).metadata
        if any(
            any(s.min <= c <= s.max for c in identifiers)
            for i in range(metadata.num_row_groups)
            if (s := metadata.row_group(i).column(0).statistics)
        ):
            path = file.with_suffix(".parquet")
            if not path.is_file():
                raise ValueError(f"Missing matching pinned source shard: {path.name}")
            sources.append(path)
    if not sources:
        raise ValueError("Missing pinned public metadata shards")
    return sources


def official_index(through, identity, private):
    base = "https://www.sec.gov/Archives/edgar/full-index/2026/QTR4/"
    path = private / "official-2026-Q4-master.idx"
    errors = {}
    for name in ("master.idx", "master.zip"):
        url = base + name
        try:
            if not path.is_file():
                request = Request(
                    url, headers={"User-Agent": identity, "Accept": "*/*"}
                )
                with urlopen(request, timeout=10) as response:
                    contents = response.read()
                if name.endswith(".zip"):
                    with ZipFile(BytesIO(contents)) as archive:
                        contents = archive.read("master.idx")
                if b"CIK|Company Name|Form Type|Date Filed|Filename" not in contents:
                    raise ValueError("Unexpected official EDGAR master index format")
                path.write_bytes(contents)
            rows = []
            for line in path.read_text(encoding="latin-1").splitlines():
                fields = line.split("|")
                if len(fields) == 5 and fields[0].isdigit():
                    rows.append(fields)
            last_day = max(r[3] for r in rows if r[3] <= through)
            return rows, {
                "url": url,
                "last_filing_day": last_day,
                "sha256": study.digest(path),
            }
        except (OSError, ValueError) as exc:
            errors[url] = str(exc)
    return [], {"attempts": errors, "last_filing_day": None}


def add_recent(cik, wanted, directory, identity, records, through):
    """Complete original accession metadata from SEC for filings after the snapshot."""
    import json

    filename = f"CIK{cik}.json"
    local = directory / filename
    if not local.is_file():
        url = "https://data.sec.gov/submissions/" + filename
        import time

        with study.evidence.RATE_LOCK:
            time.sleep(max(0.0, 0.25 - (time.monotonic() - study.evidence.PREVIOUS)))
            study.evidence.PREVIOUS = time.monotonic()
        with urlopen(
            Request(url, headers={"User-Agent": identity}), timeout=8
        ) as response:
            raw = response.read()
        if "filings" not in json.loads(raw):
            raise ValueError("SEC submissions response lacks filings")
        local.write_bytes(raw)
    p = json.loads(local.read_bytes())["filings"]["recent"]
    additions = 0
    for i, accession in enumerate(p["accessionNumber"]):
        if wanted is None:
            wanted_row = (
                SNAPSHOT_THROUGH < p["filingDate"][i] <= through
                and p["form"][i] in FORMS
            )
        else:
            wanted_row = accession in wanted
        if wanted_row:
            records[accession] = {
                field: p[field][i] or "" for field in FIELDS if field != "cik"
            }
            additions += 1
    return {
        "sha256": study.digest(local),
        "records_in_requested_tail": additions,
        "last_filing_in_issuer_source": max(p["filingDate"], default=None),
    }


def publish(data, public, shards, private, through, identity):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    verify_predictions(data, data / "forecasts")
    private.mkdir(parents=True, exist_ok=True)
    issuers = sorted(r["cik"] for r in study.table(data / "companies.csv"))
    identifiers = {k for c in issuers for k in (c, str(int(c)))}
    source_files = selected_shards(shards, identifiers)
    registered = pa.array(sorted(identifiers))
    forms = pa.array(sorted(FORMS))
    histories = defaultdict(dict)
    for path in source_files:
        table = pq.read_table(path, columns=FIELDS)
        wanted = pc.and_(
            pc.is_in(table["cik"], value_set=registered),
            pc.is_in(table["form"], value_set=forms),
        )
        for row in table.filter(wanted).to_pylist():
            if "2017-01-01" <= row["filingDate"] <= through:
                c = str(row.pop("cik")).zfill(10)
                histories[c][row["accessionNumber"]] = {
                    k: v or "" for k, v in row.items()
                }
    delta, official = official_index(through, identity, private)
    expected = defaultdict(set)
    for cik, _, form, filed, path in delta:
        cik = cik.zfill(10)
        if cik in histories and form in FORMS and SNAPSHOT_THROUGH < filed <= through:
            expected[cik].add(Path(path).stem)
    unresolved = {}
    supplemental = {}
    index_through = official.get("last_filing_day") or ""
    refresh = issuers if index_through < through else sorted(expected)

    def fill(c):
        wanted = None if index_through < through else expected[c]
        try:
            info = add_recent(c, wanted, private, identity, histories[c], through)
            return c, info, None
        except (KeyError, OSError, ValueError) as exc:
            return c, None, str(exc)

    with ThreadPoolExecutor(4) as pool:
        for c, info, error in pool.map(fill, refresh):
            if info is not None:
                supplemental[c] = info
            else:
                unresolved[c] = error
            missing = expected[c] - set(histories[c])
            if missing:
                unresolved[c] = {
                    "missing_accessions": sorted(missing),
                    "issue": unresolved.get(c),
                }
    received = Counter()
    digest = {}
    for c in issuers:
        records = sorted(
            histories[c].values(),
            key=lambda r: (r["filingDate"], r["accessionNumber"]),
            reverse=True,
        )
        received.update(r["form"] for r in records)
        recent = {k: [r[k] for r in records] for k in FIELDS if k != "cik"}
        output = private / f"{c}-submissions.json"
        study.lock_json(output, {"cik": c, "filings": {"recent": recent, "files": []}})
        digest[c] = study.digest(output)
        dst = private / f"{c}-companyfacts.json"
        if not dst.exists():
            dst.symlink_to((public / dst.name).resolve())
    originals = list(public.glob("*.html.gz"))
    for src in originals:
        dst = private / src.name
        if not dst.exists():
            dst.symlink_to(src.resolve())
    # Data after the latest confirmed source can never silently extend the measurement window.
    result = {
        "prediction_sha256": study.digest(data / "forecasts/prediction_lock.json"),
        "requested_through": through,
        "pinned_snapshot_through": SNAPSHOT_THROUGH,
        "pinned_registry": REPO,
        "revision": REVISION,
        "snapshot_source": f"{FILES}/sec/submissions/filings/",
        "official_quarter_index": official,
        "known_missing_delta": unresolved,
        "official_issuer_updates": supplemental,
        "registered_issuers": len(issuers),
        "filing_forms": dict(sorted(received.items())),
        "filing_metadata_source_shards": len(source_files),
        "original_files_reused": len(originals),
        "quarterly_amount_source": "Pinned CompanyFacts snapshot. Later available 10-K/Q metadata are retained; unconfirmed updates and any dollars published after the snapshot require separate primary-statement checks.",
        "issuer_metadata_sha256": digest,
    }
    study.lock_json(private / "ready.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("data", "public", "shards", "private"):
        parser.add_argument("--" + k, type=Path, required=True)
    parser.add_argument(
        "--through",
        default="2026-11-24",
        type=lambda d: date.fromisoformat(d).isoformat(),
    )
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    receipt = publish(
        args.data, args.public, args.shards, args.private, args.through, args.identity
    )
    print({k: v for k, v in receipt.items() if k != "issuer_metadata_sha256"})
