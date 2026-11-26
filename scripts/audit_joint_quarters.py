"""Check the 2024 development scorer's revenue pairs against original filings after the forecasts are sealed."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

from industry_evidence import download
from industry_score import fiscal_window, quarter_index
from run_joint_watch import ROOT, verify_lock


def filing_metadata(cache, cik):
    head = json.loads((cache / f"{cik}-submissions.json").read_bytes())["filings"]
    tables = [head["recent"]]
    for record in head["files"]:
        if record["filingTo"] >= "2022-01-01" and record["filingFrom"] <= "2025-12-31":
            tables.append(json.loads((cache / record["name"]).read_bytes()))
    return {
        accession: (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{table['primaryDocument'][i]}",
            table["filingDate"][i],
        )
        for table in tables
        for i, accession in enumerate(table["accessionNumber"])
    }


def parse_document(raw, tags):
    from lxml import html

    doc = html.fromstring(raw)
    usd_units = {
        u.get("id")
        for u in doc.iter("xbrli:unit")
        if [m.text for m in u.iter("xbrli:measure")] == ["iso4217:USD"]
    }
    periods = {}
    for el in doc.iter():
        if el.tag != "xbrli:context":
            continue
        fields = {x.tag.split(":")[-1]: x.text for x in el.iterdescendants() if isinstance(x.tag, str)}
        if {"segment", "scenario", "explicitmember", "typedmember"}.intersection(fields):
            continue
        if fields.get("startdate") and fields.get("enddate"):
            periods[el.get("id")] = fields["startdate"], fields["enddate"]
    values, precisions = {}, {}
    for elem in doc.xpath("//*[@contextref and @name]"):
        name = elem.get("name").split(":")[-1]
        period = periods.get(elem.get("contextref"))
        if (
            name not in tags
            or not period
            or elem.get("unitref") not in usd_units
            or (elem.get("format") or "").endswith("numdash")
        ):
            continue
        rendered = "".join(elem.itertext()).strip().replace(",", "")
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", rendered):
            continue
        amount = Decimal(rendered).scaleb(int(elem.get("scale", "0")))
        if elem.get("sign") == "-":
            amount = -amount
        # Original textual row label, if the fact is rendered in a table.
        tables = elem.xpath("ancestor::tr[1]")
        label = ""
        if tables:
            cells = tables[0].xpath("./td|./th")
            if cells:
                label = " ".join(cells[0].text_content().split())[:150]
        key = (name, *period)
        values.setdefault(key, {}).setdefault(int(amount), set()).add(label)
        decimals = elem.get("decimals", "INF")
        precision = float("inf") if decimals.upper() == "INF" else int(decimals)
        weights = precisions.setdefault(key, {})
        weights[int(amount)] = max(precision, weights.get(int(amount), precision))
    for key, amounts in values.items():
        if len(amounts) == 1:
            continue
        # EDGAR also tags approximations in the narrative (e.g. $2.2bn alongside
        # the statement's $2,170,230,000). Drop only compatible coarser values.
        best = max(precisions[key].values())
        precise = [amount for amount in amounts if precisions[key][amount] == best]
        for amount, precision in precisions[key].items():
            if precision < best and all(
                abs(amount - exact) <= Decimal(5).scaleb(-precision - 1) for exact in precise
            ):
                del amounts[amount]
    return values


def fiscal_amount(values, tag, end, age, duration):
    rows = [
        (start, last, amount, labels)
        for (name, start, last), amounts in values.items()
        if name == tag
        and age[0] <= (date.fromisoformat(end) - date.fromisoformat(last)).days <= age[1]
        and duration[0] <= (date.fromisoformat(last) - date.fromisoformat(start)).days + 1 <= duration[1]
        for amount, labels in amounts.items()
    ]
    if len(rows) != 1:
        raise ValueError(
            f"Expected one original consolidated amount for {(tag, end, age, duration)}, got {rows}"
        )
    return rows[0]


def check_pair(row, documents):
    current, prior = (0, 0), (350, 379)
    docs = [documents[k] for k in row["source_accessions"]]
    tag = row["tag"]
    if row["calculation"] == "reported_quarter":
        now, year_ago = [
            fiscal_amount(docs[0], tag, row["end"], age, (70, 119)) for age in (current, prior)
        ]
        if now[0] != row["start"]:
            raise ValueError("Original quarter start differs")
        return [now[2], year_ago[2]], sorted(now[3] | year_ago[3])
    if row["calculation"] != "fiscal_year_less_first_nine_months":
        raise ValueError(f"Unsupported recorded source type {row['calculation']}")
    q3_end = (date.fromisoformat(row["start"]) - timedelta(days=1)).isoformat()
    sums, labels = [], set()
    for age in (current, prior):
        year = fiscal_amount(docs[0], tag, row["end"], age, (350, 379))
        ytd = fiscal_amount(docs[1], row["first_nine_months_tag"], q3_end, age, (245, 295))
        if year[0] != ytd[0]:
            raise ValueError("Annual and cumulative periods have different fiscal starts")
        sums.append(year[2] - ytd[2])
        labels.update(year[3])
        labels.update(ytd[3])
    return sums, sorted(labels)


def public_history(root, filings):
    rows, origins = {}, {}
    for path in sorted((root / "trend_inputs").glob("*.json")):
        history = json.loads(path.read_bytes())
        issuers = {c["cik"]: c for c in history["issuers"]}
        packet = json.loads((root / path.stem / "joint_input.json").read_bytes())
        for c in packet["companies"]:
            cik = c["cik"]
            quarters = {q["end"]: q for q in issuers[cik]["quarters"]}
            for actual in c["historical_sales"]["quarters"]:
                key = cik, actual["quarter_end"]
                row = quarters[key[1]]
                dates = [filings[a][1] for a in row["source_accessions"]]
                if not (max(dates) == row["latest_filed"] == actual["filed"] <= history["cutoff"]):
                    raise ValueError(f"Cutoff/filing date mismatch: {key} on {path.stem}")
                yoy = (Decimal(row["sales"]) / Decimal(row["year_ago_sales"]) - 1) * 100
                if (row["sales"], row["year_ago_sales"], format(yoy, ".4f")) != (
                    actual["reported_sales_usd"],
                    actual["year_ago_reported_sales_usd"],
                    actual["yoy_percent"],
                ):
                    raise ValueError(f"Public rate/source mismatch: {key} on {path.stem}")
                if key in rows and rows[key] != row:
                    raise ValueError(f"Different original quarter across packets: {key}")
                rows[key] = row
                origins.setdefault(key, []).append(path.stem)
    return rows, origins


def audit(root, statements, metadata, identity=None):
    verify_lock(root)
    facts = json.loads((root / "scorer/quarters.json").read_bytes())
    selected = {}
    for path in sorted((root / "evidence").glob("*.json")):
        for c in json.loads(path.read_bytes())["companies"]:
            if c["status"] != "complete":
                continue
            for q in fiscal_window(c["period_end"], *quarter_index(facts[c["cik"]])):
                selected[c["cik"], q["end"]] = q
    urls, tags = {}, {}
    for cik in sorted({k[0] for k in selected}):
        urls.update(filing_metadata(metadata, cik))
    public, origins = public_history(root, urls)
    score_accessions = {a for q in selected.values() for a in q["source_accessions"]}
    all_rows = dict(selected)
    for key, row in public.items():
        if key in all_rows and all_rows[key] != row:
            raise ValueError(f"Fiscal-quarter vintage differs between projection and scoring: {key}")
        all_rows[key] = row
    for row in all_rows.values():
        for accession in row["source_accessions"]:
            tags.setdefault(accession, set()).update(
                (row["tag"], row.get("first_nine_months_tag", row["tag"]))
            )

    def fetch(url, path):
        if not path.exists() and identity:
            download(url, path, identity, compress=True)
        return gzip.decompress(path.read_bytes())

    def inspect(acc):
        from lxml import html

        url = urls[acc][0]
        path = statements / (acc + ".html.gz")
        raw = fetch(url, path)
        values = parse_document(raw, tags[acc])
        if not values:
            # Some 10-Ks incorporate the entire financial statement from Exhibit 13.
            base = url.rsplit("/", 1)[0]
            index = fetch(f"{base}/{acc}-index.htm", statements / (acc + "-index.htm.gz"))
            for tr in html.fromstring(index).xpath("//tr[td]"):
                cells = tr.xpath("./td")
                if len(cells) < 4 or not cells[3].text_content().strip().startswith("EX-13"):
                    continue
                name = cells[2].text_content().split()[0]
                if not re.fullmatch(r"[\w.-]+\.html?", name, re.I):
                    continue
                url = f"{base}/{name}"
                raw = fetch(url, statements / f"{acc}-{name}.gz")
                values = parse_document(raw, tags[acc])
                if values:
                    break
        if not values:
            raise ValueError(f"No original consolidated revenue facts in accession {acc}")
        return values, sha256(raw).hexdigest(), url

    with ThreadPoolExecutor(4) as workers:
        parsed = dict(zip(tags, workers.map(inspect, tags)))
    documents = {k: v[0] for k, v in parsed.items()}
    checks, public_checks, issues = [], [], []
    for key, row in sorted(all_rows.items()):
        cik, end = key
        try:
            amounts, labels = check_pair(row, documents)
        except ValueError as error:
            issues.append(f"{cik}/{end} {row['source_accessions']}: {error}")
            continue
        if amounts != [row["sales"], row["year_ago_sales"]]:
            raise ValueError(f"Original statement differs for {cik}/{end}: {amounts}")
        checked = dict(
            cik=cik,
            end=end,
            sales=amounts[0],
            year_ago_sales=amounts[1],
            tag=row["tag"],
            method=row["calculation"],
            source_accessions=row["source_accessions"],
            source_row_labels=labels,
        )
        if key in selected:
            checks.append(checked)
        if key in origins:
            public_checks.append(dict(**checked, origins=origins[key]))
    if issues:
        raise ValueError("\n".join(issues))
    release_checks = root / "scorer/quarter_release_checks.json"
    for check in json.loads(release_checks.read_bytes()):
        quarter = selected[check["cik"], check["end"]]
        if any(quarter[k] != check[k] for k in ("sales", "year_ago_sales")):
            raise ValueError(f"Release check differs for {check['cik']}/{check['end']}")
    result = {
        "prediction_lock_sha256": sha256((root / "prediction_lock.json").read_bytes()).hexdigest(),
        "quarters_sha256": sha256((root / "scorer/quarters.json").read_bytes()).hexdigest(),
        "method": "Read original EDGAR Inline XBRL entity-wide USD revenue facts, excluding dimensional contexts, and reconstruct annual-minus-YTD pairs where needed. Include every quarter used in a resolvable fiscal horizon and independently compare each model-visible current and prior-year amount, rate, and source accession date to its origin cutoff.",
        "quarter_release_checks_sha256": sha256(release_checks.read_bytes()).hexdigest(),
        "documents": {
            k: {"url": v[2], "sha256": v[1]} for k, v in sorted(parsed.items()) if k in score_accessions
        },
        "additional_public_documents": {
            k: {"url": v[2], "sha256": v[1]}
            for k, v in sorted(parsed.items())
            if k not in score_accessions
        },
        "historical_input_quarters": public_checks,
        "quarters": checks,
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filings", type=Path)
    parser.add_argument("submissions", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--identity", help="SEC User-Agent to download missing original filings")
    parser.add_argument("--output", type=Path)
    a = parser.parse_args()
    result = audit(a.root, a.filings, a.submissions, a.identity)
    out = a.output or a.root / "scorer/quarter_audit.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    seen_rates = sum(len(q["origins"]) for q in result["historical_input_quarters"])
    print(
        f"{len(result['quarters'])} scoring quarters verified from {len(result['documents'])} filings; "
        f"{seen_rates} historical rates verified with {len(result['additional_public_documents'])} additional filings"
    )
