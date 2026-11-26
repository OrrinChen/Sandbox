"""Verify both adjacent reported-sales comparisons for every post-lock numerical onset."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import gzip
from hashlib import sha256
from pathlib import Path
import re

from audit_joint_quarters import check_pair, parse_document
from industry_evidence import download
from run_industry_watch import digest, load, seal
from run_t30_watch import DATA, verify_predictions
from score_t30_watch import all_cases


def source_urls(cache, issuers):
    result = {}
    for cik in issuers:
        head = load(cache / f"{cik}-submissions.json")["filings"]
        pages = [head["recent"]]
        pages += [
            load(cache / x["name"])
            for x in head["files"]
            if (cache / x["name"]).is_file()
        ]
        for p in pages:
            for idx, acc in enumerate(p["accessionNumber"]):
                name = p["primaryDocument"][idx]
                if name:
                    result[acc] = (int(cik), acc.replace("-", ""), name)
    return result


def audit(data, cache, identity=None):
    verify_predictions(data, data / "forecasts")
    archive = data / "scorer"
    facts = load(archive / "quarters.json")
    _, candidates = all_cases(data, facts, {})
    selected, tags = {}, {}
    for (cik, _), target in candidates.items():
        previous = (date.fromisoformat(target["start"]) - timedelta(days=1)).isoformat()
        need = {previous, target["end"]}
        for q in facts[cik]:
            if q["end"] in need:
                selected[cik, q["end"]] = q
                for accession in q["source_accessions"]:
                    tags.setdefault(accession, set()).update(
                        [q["tag"], q.get("first_nine_months_tag", q["tag"])]
                    )
    urls = source_urls(cache, {c for c, _ in selected})

    def fetch(tail, dst):
        canonical = "https://www.sec.gov/Archives/edgar/data/" + tail
        mirror = "https://edgar-mirror.sec-api.io/" + tail
        if not dst.exists() and identity:
            first, second = (
                (mirror, canonical) if data.name == "formal" else (canonical, mirror)
            )
            try:
                download(first, dst, identity, compress=True)
            except (OSError, ValueError):
                download(second, dst, identity, compress=True)
        return canonical, gzip.decompress(dst.read_bytes())

    def inspect(acc):
        from lxml import html

        if acc not in urls:
            return {}, {
                "error": "The accession has no original primary document in the filing catalogue."
            }
        cik, folder, doc = urls[acc]
        tail = f"{cik}/{folder}/{doc}"
        canonical = f"https://www.sec.gov/Archives/edgar/data/{tail}"
        try:
            url, raw = fetch(tail, cache / f"{acc}.html.gz")
            values = parse_document(raw, tags[acc])
            if not values:
                _, index = fetch(
                    f"{cik}/{folder}/{acc}-index.htm", cache / f"{acc}-index.htm.gz"
                )
                for tr in html.fromstring(index).xpath("//tr[td]"):
                    cells = tr.xpath("./td")
                    if len(cells) < 4 or not cells[3].text_content().strip().startswith(
                        "EX-13"
                    ):
                        continue
                    name = cells[2].text_content().split()[0]
                    if re.fullmatch(r"[\w.-]+\.html?", name, re.I):
                        url, raw = fetch(
                            f"{cik}/{folder}/{name}", cache / f"{acc}-{name}.gz"
                        )
                        values = parse_document(raw, tags[acc])
                        if values:
                            break
            return values, {"url": url, "sha256": sha256(raw).hexdigest()}
        except (OSError, ValueError) as exc:
            return {}, {"url": canonical, "error": str(exc)}

    with ThreadPoolExecutor(4) as pool:
        parsed = dict(zip(tags, pool.map(inspect, tags)))
    checks = []
    doc_values = {a: p[0] for a, p in parsed.items()}
    for (cik, end), q in sorted(selected.items()):
        result = {
            "cik": cik,
            "end": end,
            "accessions": q["source_accessions"],
            "stored": [q["sales"], q["year_ago_sales"]],
        }
        try:
            amounts, labels = check_pair(q, doc_values)
            result.update(
                statement_amounts=amounts,
                statement_row_labels=labels,
                matches=amounts == result["stored"],
            )
        except ValueError as exc:
            result.update(matches=False, reason=str(exc))
        checks.append(result)
    result = {
        "prediction_sha256": digest(data / "forecasts/prediction_lock.json"),
        "quarters_sha256": digest(archive / "quarters.json"),
        "candidate_count": len(candidates),
        "compared_quarters": len(checks),
        "agreements": sum(c["matches"] for c in checks),
        "checks": checks,
        "originals": {k: v[1] for k, v in sorted(parsed.items())},
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA / "development")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--identity")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.data, args.cache, args.identity)
    seal(args.out or args.data / "scorer/onset_amount_audit.json", result)
    print(
        result["agreements"],
        "/",
        result["compared_quarters"],
        "original quarter pairs",
        flush=True,
    )
