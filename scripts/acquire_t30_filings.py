"""Fetch only original filing bodies referenced by the locked issuer-relative schedule."""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import gzip
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import build_t30_inputs as inputs


def required_docs(root, split, cache):
    inputs.verify(root, "registration_lock.json")
    inputs.verify(root, f"{split}/schedule_lock.json")
    dates = defaultdict(list)
    for row in inputs.table(root / split / "schedule.csv"):
        if row["cutoff"]:
            dates[row["cik"]].append(row["cutoff"])
    docs = {}
    for cik, cutoffs in dates.items():
        filings = inputs.filing_metadata(cache, cik, None, max(cutoffs))
        for day in cutoffs:
            f = inputs.evidence.anchor(filings, day)
            if (
                f
                and inputs.revenue.gap(day, f["reportDate"]) <= 185
                and inputs.revenue.gap(day, f["filingDate"]) <= 135
            ):
                docs[f["accessionNumber"]] = f
    return docs


def acquire(root, split, cache, mirror_base, identity, workers):
    docs = required_docs(root, split, cache)
    receipt_dir = cache / "filing-receipts"
    receipt_dir.mkdir(exist_ok=True)

    def one(doc):
        accession = doc["accessionNumber"]
        target = cache / (accession + ".html.gz")
        item = receipt_dir / (accession + ".json")
        if target.exists() and item.exists():
            receipt = inputs.evidence.read(item)
            if (
                sha256(gzip.decompress(target.read_bytes())).hexdigest()
                != receipt["source_sha256"]
            ):
                raise ValueError(
                    f"Cached original differs from its acquisition receipt: {target}"
                )
            return receipt
        url = doc["url"]
        if mirror_base:
            url = (
                mirror_base.rstrip("/") + "/" + url.split("/Archives/edgar/data/", 1)[1]
            )
        if target.exists():
            # Recover an interrupted acquisition without attributing unknown bytes to a URL.
            with TemporaryDirectory(dir=cache) as temp:
                confirmed = Path(temp) / target.name
                inputs.evidence.download(url, confirmed, identity, True)
                raw = gzip.decompress(target.read_bytes())
                if gzip.decompress(confirmed.read_bytes()) != raw:
                    raise ValueError(
                        f"Unreceipted source differs from retrieved original: {target}"
                    )
        else:
            inputs.evidence.download(url, target, identity, True)
            raw = gzip.decompress(target.read_bytes())
        if b"<html" not in raw[:10000].lower():
            raise ValueError(f"Response lacks an HTML filing: {accession}")
        row = {
            "accession": accession,
            "canonical_url": doc["url"],
            "retrieved_url": url,
            "source_sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
        inputs.lock_json(item, row)
        return row

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(one, docs.values()))
    out = root / split / "filing_sources.json"
    inputs.lock_json(out, sorted(results, key=lambda x: x["accession"]))
    print(f"Acquired {len(results)} distinct named filing bodies")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=inputs.DATA)
    cli.add_argument("--split", choices=inputs.SPLITS, default="formal")
    cli.add_argument("--cache", type=Path, required=True)
    cli.add_argument("--identity", required=True)
    cli.add_argument(
        "--mirror-base",
        help="Optional documented original-filing mirror, e.g. https://edgar-mirror.sec-api.io",
    )
    cli.add_argument("--workers", type=int, default=8)
    opts = cli.parse_args()
    if opts.mirror_base and urlparse(opts.mirror_base).scheme != "https":
        cli.error("mirror base must be an HTTPS URL")
    acquire(
        opts.root, opts.split, opts.cache, opts.mirror_base, opts.identity, opts.workers
    )
