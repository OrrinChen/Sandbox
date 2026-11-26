"""Select the registered issuers from a versioned, publicly distributed SEC snapshot.

The normal input builder also accepts the original EDGAR submissions/companyfacts
JSONs. This optional acquisition route requires PyArrow; the reader and scorer
never use PyArrow or the network to verify a frozen run.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import struct
import time
from urllib.request import Request, urlopen

import build_t30_inputs as study

REVISION = "10990903244941e14a354db9882057f32968a2a7"
REPO = "syncster-data/economic-data"
API = f"https://huggingface.co/api/datasets/{REPO}/tree/{REVISION}/sec"
FILES = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}"
METADATA = [
    "cik",
    "accessionNumber",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
    "form",
    "primaryDocument",
    "primaryDocDescription",
]
AMOUNTS = ["cik", "tag", "unit", "start", "end", "val", "accn", "filed", "taxonomy"]


def fetch(request):
    for attempt in range(4):
        try:
            with urlopen(request, timeout=40) as response:
                return response.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def select_shard(item, columns, identifiers, temp, category):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    size, name = item["size"], item["path"]
    shard = Path(name).stem
    footer_path = temp / f"{category}-{shard}.footer"
    source = f"{FILES}/{name}"
    if not footer_path.exists():
        n = min(size, 32768)
        tail = fetch(
            Request(source, headers={"Range": f"bytes={size - n}-{size - 1}"})
        )[-n:]
        if tail[-4:] != b"PAR1" or len(tail) != n:
            raise ValueError(f"Invalid parquet footer for {name}")
        footer_path.write_bytes(tail)
    tail = footer_path.read_bytes()
    footer_size = struct.unpack("<I", tail[-8:-4])[0]
    if footer_size + 8 > len(tail):
        raise ValueError(f"Truncated parquet metadata for {name}")
    meta = pq.ParquetFile(BytesIO(b"PAR1" + tail[-(footer_size + 8) :])).metadata
    # This snapshot uses both padded and unpadded strings for CIKs. Row-group
    # statistics use byte/string ordering, including at digit-width boundaries.
    for i in range(meta.num_row_groups):
        stats = meta.row_group(i).column(0).statistics
        if any(stats.min <= key <= stats.max for key in identifiers):
            break
    else:
        return []
    path = temp / f"{category}-{shard}.parquet"
    if not path.exists():
        content = fetch(Request(source))
        if len(content) != size:
            raise ValueError(f"Incomplete data shard {name}")
        path.write_bytes(content)
    rows = pq.read_table(path, columns=columns)
    match = pc.is_in(rows["cik"], value_set=pa.array(sorted(identifiers)))
    if category == "companyfacts":
        match = pc.and_(
            match, pc.is_in(rows["tag"], value_set=pa.array(list(study.revenue.TAGS)))
        )
    else:
        match = pc.and_(
            match,
            pc.is_in(rows["form"], value_set=pa.array(sorted(study.revenue.FORMS))),
        )
    return rows.filter(match).to_pylist()


def acquire(root, split, category, cache, temp):
    study.verify(root, "registration_lock.json")
    if category == "companyfacts":
        study.verify(root, f"{split}/schedule_lock.json")
    companies = [r["cik"] for r in study.table(root / split / "companies.csv")]
    identifiers = {form for c in companies for form in (c, str(int(c)))}
    suffix = (
        "companyfacts/facts" if category == "companyfacts" else "submissions/filings"
    )
    columns = AMOUNTS if category == "companyfacts" else METADATA
    pieces = json.loads(fetch(Request(f"{API}/{suffix}")))
    rows_by_issuer = {c: [] for c in companies}
    cache.mkdir(exist_ok=True, parents=True)
    temp.mkdir(exist_ok=True, parents=True)
    with ThreadPoolExecutor(8) as pool:
        for selected in pool.map(
            lambda piece: select_shard(piece, columns, identifiers, temp, category),
            pieces,
        ):
            for row in selected:
                rows_by_issuer[str(row.pop("cik")).zfill(10)].append(row)
    digests = {}
    for c, rows in rows_by_issuer.items():
        if category == "submissions":
            recent = {k: [r[k] or "" for r in rows] for k in METADATA if k != "cik"}
            envelope = {"cik": c, "filings": {"recent": recent, "files": []}}
        else:
            values = {}
            for row in rows:
                if row["taxonomy"] != "us-gaap" or row["unit"] != "USD":
                    continue
                amount = Decimal(str(row["val"]))
                value = (
                    int(amount)
                    if amount == amount.to_integral_value()
                    else float(amount)
                )
                fact = {
                    k: row[k]
                    for k in ("start", "end", "accn", "filed")
                    if row[k] is not None
                }
                fact["val"] = value
                values.setdefault(row["tag"], {"units": {"USD": []}})["units"][
                    "USD"
                ].append(fact)
            envelope = {"cik": c, "facts": {"us-gaap": values}}
        destination = cache / f"{c}-{category}.json"
        # Public vintages can be regenerated repeatedly from these pinned shards.
        destination.write_text(
            json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        )
        digests[destination.name] = study.digest(destination)
    receipt = {
        "distribution": REPO,
        "revision": REVISION,
        "dataset": suffix,
        "public_source": "U.S. SEC EDGAR submissions/companyfacts",
        "companies_sha256": study.digest(root / split / "companies.csv"),
        "companies": len(companies),
        "fields": columns,
        "outputs_sha256": digests,
    }
    study.lock_json(root / split / f"{category}_sources.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", choices=["submissions", "companyfacts"])
    parser.add_argument("--root", type=Path, default=study.DATA)
    parser.add_argument("--split", choices=study.SPLITS, default="formal")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--shard-cache", type=Path, required=True)
    args = parser.parse_args()
    acquire(args.root, args.split, args.category, args.cache, args.shard_cache)
