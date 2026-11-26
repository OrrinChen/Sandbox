"""Recheck the two historical sales pairs in the first complete packet per issuer."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import gzip
from hashlib import sha256
from pathlib import Path
import re

from audit_joint_quarters import check_pair, parse_document
import build_t30_inputs as study


def face_line(raw, quarter, amounts):
    from lxml import html

    end = date.fromisoformat(quarter)
    numbers = [f"{v:,}" for v in amounts]
    date_label = f"{end:%B} {end.day}"
    for elem in html.fromstring(raw).xpath("//tr"):
        text = " ".join(elem.text_content().split())
        if not re.match(r"^(?:Total |Net )?(?:revenues?|sales)\b", text, re.I):
            continue
        if not re.search(
            rf"\$?{re.escape(numbers[0])}\s+\$?{re.escape(numbers[1])}(?!\d)", text
        ):
            continue
        parent = elem.xpath("ancestor::table[1]")
        if not parent:
            continue
        header = " ".join(parent[0].text_content().split()).split(text, 1)[0]
        if (
            "three months ended" in header.lower()
            and date_label in header
            and str(end.year) in header
            and str(end.year - 1) in header
        ):
            return text[:220]
    return None


def inspect_issuer(data, cache, extra, mirror, identity, r):
    cik = r["cik"]
    cases = sorted((data / "packets").glob(f"*/{cik}.json"))
    first = next(
        (q for p in cases if (q := study.evidence.read(p))["status"] == "complete"),
        None,
    )
    if first is None:
        return {"cik": cik, "status": "no_complete_packet", "checks": []}
    metadata = study.filing_metadata(cache, cik, None, first["cutoff"])
    by_acc = {v["accessionNumber"]: v for v in metadata}
    reported = [
        {
            "end": v["reportDate"],
            "filed": v["filingDate"],
            "form": v["form"],
            "accn": v["accessionNumber"],
        }
        for v in metadata
    ]
    facts = study.revenue.revenue_facts(cache, cik, set(by_acc))
    quarters = {
        (q["end"], q["latest_filed"]): q
        for q in study.revenue.as_reported(reported, facts)
    }
    parsed, originals, hashes, checks = {}, {}, {}, []
    for pair in first["historical_sales"]["quarters"]:
        key = pair["quarter_end"], pair["filed"]
        source = quarters[key]
        expected = [pair["reported_sales_usd"], pair["year_ago_reported_sales_usd"]]
        for acc in source["source_accessions"]:
            if acc in parsed:
                continue
            f = cache / (acc + ".html.gz")
            if not f.is_file():
                f = extra / (acc + ".html.gz")
                url = by_acc[acc]["url"]
                if mirror:
                    url = (
                        mirror.rstrip("/")
                        + "/"
                        + url.split("/Archives/edgar/data/", 1)[1]
                    )
                study.fetch(url, f, identity, True)
            raw = gzip.decompress(f.read_bytes())
            originals[acc] = raw
            hashes[acc] = sha256(raw).hexdigest()
            parsed[acc] = parse_document(raw, set(study.revenue.TAGS))
        method = "original_inline_xbrl"
        try:
            values, labels = check_pair(source, parsed)
        except ValueError:
            if source["calculation"] != "reported_quarter":
                raise
            line = face_line(
                originals[source["source_accessions"][0]], key[0], expected
            )
            if not line:
                raise
            method, values, labels = "original_statement_table", expected, [line]
        if (
            values != expected
            or max(by_acc[k]["filingDate"] for k in source["source_accessions"])
            > first["cutoff"]
        ):
            raise ValueError(
                f"Historical primary-source comparison differs for {cik} {key}"
            )
        checks.append(
            {
                "quarter_end": key[0],
                "filed": key[1],
                "method": method,
                "amounts_usd": values,
                "statement_row_labels": labels,
                "source_accessions": source["source_accessions"],
            }
        )
    return {
        "cik": cik,
        "status": "verified",
        "wave": first["wave"],
        "cutoff": first["cutoff"],
        "checks": checks,
        "original_sha256": hashes,
    }


def run(data, cache, extra, mirror, identity):
    study.verify_inputs(data)
    extra.mkdir(exist_ok=True, parents=True)
    companies = study.table(data / "companies.csv")
    with ThreadPoolExecutor(4) as pool:
        items = list(
            pool.map(
                lambda r: inspect_issuer(data, cache, extra, mirror, identity, r),
                companies,
            )
        )
    counts = Counter(x["method"] for r in items for x in r["checks"])
    study.lock_json(
        data / "historical_sample_audit.json",
        {
            "input_lock_sha256": study.digest(data / "input_lock.json"),
            "selection": "Earliest fully available packet per issuer, no future labels or model decisions consulted.",
            "verified_pairs": sum(counts.values()),
            "by_source_method": dict(counts),
            "issuers": items,
        },
    )
    print(dict(counts))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--split", choices=study.SPLITS, default="formal")
    cli.add_argument("--root", type=Path, default=study.DATA)
    cli.add_argument("--cache", type=Path, required=True)
    cli.add_argument("--additional-cache", type=Path, required=True)
    cli.add_argument("--mirror-base")
    cli.add_argument("--identity")
    args = cli.parse_args()
    run(
        args.root / args.split,
        args.cache,
        args.additional_cache,
        args.mirror_base,
        args.identity,
    )
