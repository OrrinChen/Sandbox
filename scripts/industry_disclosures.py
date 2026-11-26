"""After the global prediction lock, assemble private primary-source crossing investigations."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urljoin

from industry_score import DATA, below_threshold, fiscal_window, quarter_index, read


def cases(root: Path):
    from run_industry_watch import verify_lock

    verify_lock(root)
    facts = read(root / "scorer/quarters.json")
    indices = {c: quarter_index(qs) for c, qs in facts.items()}
    found = {}
    with (DATA / "company_quarters.csv").open(encoding="utf-8", newline="") as stream:
        origins = sorted({r["origin"] for r in csv.DictReader(stream)})
    for origin in origins:
        packet = read(root / "evidence" / f"{origin}.json")
        for c in packet["companies"]:
            if c["status"] in {"stale", "missing_anchor"} or not c["period_end"]:
                continue
            cik = c["cik"]
            window = fiscal_window(c["period_end"], *indices[cik])
            for previous, current in zip(window, window[1:]):
                if below_threshold(previous) is not False or below_threshold(current) is not True:
                    continue
                key = cik, current["end"]
                found[key] = dict(cik=cik, issuer=c["issuer"], sector=c["sector"], **current)
    return list(found.values())


def index_documents(html: bytes, index_url: str):
    from lxml import html as lh

    docs = []
    for tr in lh.fromstring(html).xpath("//tr"):
        cells = tr.xpath("./td")
        if len(cells) < 4:
            continue
        kind = cells[3].text_content().strip().upper()
        if not (kind.startswith("EX-99") or kind in {"8-K", "8-K/A"}):
            continue
        href = cells[2].xpath(".//a/@href")
        if href:
            url = urljoin(index_url, href[0].split("doc=")[-1])
            docs.append(dict(kind=kind, url=url, description=" ".join(cells[1].text_content().split())))
    return docs


def window_filings(case, cache: Path):
    cik = case["cik"]
    # Start one year before the quarter itself, including the preceding annual outlook.
    start = (date.fromisoformat(case["start"]) - timedelta(days=366)).isoformat()
    stop = case["latest_filed"]
    base = read(cache / f"{cik}-submissions.json")["filings"]
    tables = [base["recent"]] + [
        read(cache / item["name"])
        for item in base["files"]
        if item["filingFrom"] <= stop and item["filingTo"] >= start
    ]
    records = {}
    for t in tables:
        for i, (form, day) in enumerate(zip(t["form"], t["filingDate"])):
            if form not in {"8-K", "8-K/A"} or not start <= day <= stop:
                continue
            accn = t["accessionNumber"][i]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"
            records[accn] = dict(filed=day, items=t["items"][i], index_url=url, accession=accn)
    return sorted(records.values(), key=lambda r: (r["filed"], r["accession"]))


def excerpts(raw: bytes):
    from lxml import html as lh

    tree = lh.fromstring(raw)
    for e in tree.xpath("//*[local-name()='script' or local-name()='style' or local-name()='hidden']"):
        e.drop_tree()
    blocks = []
    for b in tree.xpath(
        "//p[not(.//p)]|//div[not(.//div or .//p or .//tr)]|//tr[not(.//tr)]|//li[not(.//p)]"
    ):
        txt = " ".join(" ".join(b.itertext()).split())
        if txt and (not blocks or txt != blocks[-1]):
            blocks.append(txt)
    if not blocks:
        blocks = [" ".join(tree.text_content().split())]
    lines = []
    for i, block in enumerate(blocks):
        if len(block) > 3000:
            segments = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", block)
        else:
            segments = [block]
        for text in segments:
            if re.search(
                r"outlook|guidance|preliminar|preannounc|quarter.{0,80}(?:sales|revenue)|(?:sales|revenue).{0,80}(?:quarter|expect|range|will|anticipat)|(?:net sales|total revenue)",
                text,
                re.I,
            ):
                lines.append((i, text[:1200]))
    return lines, blocks


def filing_record(record: dict, cache: Path, identity: str, fetch=None):
    from industry_evidence import download

    fetch = fetch or download

    target = cache / f"{record['accession']}-digest.json"
    if target.exists():
        return read(target)
    result = dict(record, documents=[], issues=[])
    index = cache / f"{record['accession']}-index.htm"
    try:
        fetch(record["index_url"], index, identity)
        docs = index_documents(index.read_bytes(), record["index_url"])
        if not docs:
            raise ValueError("no readable document rows")
    except (ValueError, OSError) as exc:
        return {**result, "issues": [str(exc)]}
    for d in docs:
        path = cache / sha256(d["url"].encode()).hexdigest()
        if not d["url"].lower().endswith((".htm", ".html", ".txt")):
            result["issues"].append(f"Non-HTML exhibit: {d['url']}")
            continue
        try:
            fetch(d["url"], path, identity)
            lines, blocks = excerpts(path.read_bytes())
            if not lines and (not blocks or sum(map(len, blocks)) < 150):
                result["issues"].append("No substantive extracted text: " + d["url"])
            result["documents"].append(
                {
                    **d,
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                    "blocks": len(blocks),
                    "matches": lines,
                }
            )
        except (ValueError, OSError) as exc:
            result["issues"].append(f"{d['url']}: {exc}")
    target.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def capture(chosen, cache, destination, identity, fetch=None, on_ready=None, max_workers=6):
    destination.mkdir(parents=True, exist_ok=True)
    queues = [(c, window_filings(c, cache)) for c in chosen]
    records = {r["accession"]: r for _, rows in queues for r in rows}
    reviewed = {}
    for c, listing in queues:
        path = destination / f"{c['cik']}_{c['end']}.index.json"
        path.write_text(json.dumps(dict(case=c, filings=listing)) + "\n", encoding="utf-8")
        if not listing:
            target = destination / f"{c['cik']}_{c['end']}.json"
            target.write_text(json.dumps(dict(case=c, filings=[])) + "\n", encoding="utf-8")
            if on_ready:
                on_ready(c)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for record, result in zip(
            records.values(),
            pool.map(lambda r: filing_record(r, destination, identity, fetch), records.values()),
        ):
            reviewed[record["accession"]] = result
            for c, listing in queues:
                if not any(r["accession"] == record["accession"] for r in listing) or not all(
                    r["accession"] in reviewed for r in listing
                ):
                    continue
                target = destination / f"{c['cik']}_{c['end']}.json"
                contents = [reviewed[r["accession"]] for r in listing]
                target.write_text(
                    json.dumps(dict(case=c, filings=contents), ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                if on_ready:
                    on_ready(c)


def direct_source_url(quarter, cik):
    accession = quarter["source_accessions"][0]
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"


PROMPT = """You are the scorer, auditing a past quarterly sales onset. You do not have the predictions.
Use live web search. Find the earliest dated official issuer communication that unambiguously established this specific fiscal quarter's consolidated reported GAAP sales/revenue were/would be <=95% of the prior-year quarter, including a numeric outlook with its entire high end at/below the threshold. Examine the previous quarterly earnings release and its quarterly guidance, the period between that release and the eventual actual results (preliminary/updated management guidance, 8-K exhibits, investor presentations, dated public management remarks/calls), and the release of actual results. Check the preceding earnings cycle too for earlier quarter-specific guidance. Prefer an issuer-IR or SEC EX-99 primary document. A later 10-Q date is not the reaction date if release or unambiguous guidance came earlier. Use the date the source became public, not the quarter end, later filing date, or republication on a news site. Do not use annual, organic, segment, recurring, adjusted, constant-currency, pro forma, per-unit or open-ended indications as consolidated GAAP revenue. Numeric forecasts comparing to another year (e.g. 2019) must be converted to this prior-year base. An annual outlook minus already reported nine-month actuals is still an annual outlook and cannot qualify for the primary date. Record a mathematical implication as a secondary observation and continue searching for an explicitly quarter-specific source. Deals and discontinued operations may change the revenue base; reconcile the same perimeter. Check the quarter naming carefully.
Provide actual web-accessible supporting primary links and the short precise evidence for every candidate. If the primary link cannot be read or the URLs, historical disclosure coverage, date, quarter or GAAP basis are uncertain, respond date=null and state precisely what was verified and what was missing. You may only assert a date if actuals and earlier disclosure search are verified. A model guess is inadmissible. Give JSON: {date:ISO or null,url:string,basis:string,coverage:[{url:string,detail:string}],comparison_type:'usd'|'yoy_percent'|null,upper_bound:string|null,publication_date_evidence:string}. Use US dollars for 'usd' (decimal, unrounded if available, no currency symbols). upper_bound is the upper point of revenue or % growth in the chosen source, use negative percent growth for a decline. If actual rounded numbers, use the more precise GAAP table. No code fences. Max 1300 words.
"""


def short_archive(record):
    """Bound interview input while preserving the complete list of filings and exhibit URLs."""
    lines = []
    end = date.fromisoformat(record["case"]["end"])
    for f in record["filings"]:
        lines.append(f"{f['filed']} {f['items']} {f['index_url']}")
        age = (end - date.fromisoformat(f["filed"])).days
        for d in f["documents"]:
            if not d["kind"].startswith("EX-99"):
                continue
            lines.append(f"{d['kind']} {d['description']} {d['url']}")
            if -60 <= age <= 190:
                forward = [
                    text
                    for _, text in d["matches"]
                    if re.search(r"guidance|outlook|expect|anticipat|range", text, re.I)
                ]
                lines.extend(t[:550] for t in forward[:5])
        if f["issues"]:
            lines.append("Incomplete archive: " + str(f["issues"]))
    return "\n".join(lines)


def research_schema():
    text = {"type": "string"}
    optional = {"type": ["string", "null"]}
    coverage = {
        "type": "object",
        "properties": {"url": text, "detail": text},
        "required": ["url", "detail"],
        "additionalProperties": False,
    }
    fields = {
        "date": optional,
        "url": text,
        "basis": text,
        "coverage": {"type": "array", "items": coverage},
        "comparison_type": {"enum": ["usd", "yoy_percent", None]},
        "upper_bound": optional,
        "publication_date_evidence": text,
    }
    return {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


def research(c, directory: Path, archives: Path | None, previous: dict | None = None):
    from run_industry_watch import MODEL

    key = f"{c['cik']}_{c['end']}"
    path = directory / f"{key}.json"
    if path.is_file() and path.stat().st_size:
        read(path)
        return key
    target = str(Decimal(str(c["year_ago_sales"])) * Decimal("0.95"))
    prompt = (
        PROMPT
        + "\n"
        + json.dumps(
            {**c, "maximum_revenue_usd": target, "actual_filing_index": direct_source_url(c, c["cik"])}
        )
    )
    archive = archives / f"{key}.json" if archives else None
    if archive and archive.exists():
        prompt += (
            "\nFiling inventory and candidate excerpts. Verify sources and search outside EDGAR.\n"
            + short_archive(read(archive))
        )
        for kind in ("pdf", "image"):
            supplement = archives / f"{key}.{kind}.json"
            if supplement.is_file():
                prompt += (
                    "\nPrimary exhibit supplements, with dates, page numbers and indicative excerpts. "
                    "Open any relevant original.\n" + json.dumps(read(supplement))[:24000]
                )
    prompt += "\nA dated verdict must cite an explicit numeric upper bound in this source. Do not assign an endpoint to phrases such as mid-teens. If dated disclosure cannot be verified under this rule, return a null date and describe the evidence."
    if previous:
        prompt += (
            "\nA previous source review could verify the actual result but left the earliest date open. "
            "Find the SPECIFIC missing issuer events, archived call, full deck or accessible official event-hosted audio/transcripts. "
            "Check the conference host, issuer site and SEC exhibits. Document each rescue attempt, including exact URL/outcome. "
            "Summarize new and prior search coverage. Only replace the null date with verified documentary support covering the actual gap. "
            "Do not infer that an unavailable source was silent. No guessed numeric guidance.\n"
            + json.dumps(previous)
        )
    with tempfile.TemporaryDirectory() as temp:
        schema_file = Path(temp) / "schema.json"
        schema_file.write_text(json.dumps(research_schema()), encoding="utf-8")
        cmd = [
            "codex",
            "--search",
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "-C",
            temp,
            "-s",
            "read-only",
            "-m",
            MODEL,
            "-c",
            'model_reasoning_effort="medium"',
            "--json",
            "--output-schema",
            str(schema_file),
            "-o",
            str(path.resolve()),
            "-",
        ]
        with (directory / f"{key}.log").open("w") as log:
            completed = subprocess.run(
                cmd, input=prompt, text=True, stdout=log, stderr=subprocess.STDOUT, timeout=1000
            )
    if completed.returncode or not path.exists():
        raise RuntimeError(f"Research failed for {key}")
    return key


def archive_manifest(chosen, directory, out):
    """Keep the inspected filing/exhibit inventory and public links in the scoring archive."""
    registry, cases = {}, {}
    for c in chosen:
        key = f"{c['cik']}_{c['end']}"
        rows = read(directory / f"{key}.json")["filings"]
        cases[key] = [row["accession"] for row in rows]
        for row in rows:
            entry = {k: row[k] for k in ("filed", "items", "index_url", "issues")}
            entry["documents"] = [
                {k: d[k] for k in ("url", "description", "kind", "sha256", "blocks")}
                for d in row["documents"]
            ]
            registry[row["accession"]] = entry
    out.write_text(
        json.dumps(
            {
                "scope": "All indexed 8-K and 8-K/A filings from one year before the quarter start through the original 10-Q/K, including main documents and EX-99 attachments. Archive issues record unreadable documents. Separate case records cover issuer releases, calls and public presentations.",
                "filings": registry,
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def validate_source(c: dict, d: dict, key: str) -> None:
    if d.get("date"):
        try:
            iso = date.fromisoformat(d["date"])
            upper = Decimal(d["upper_bound"])
        except (TypeError, ValueError, KeyError, InvalidOperation) as exc:
            raise ValueError(f"Invalid verified disclosure for {key}: invalid date or numeric upper bound") from exc
        cutoff = (
            Decimal("0.95") * Decimal(str(c["year_ago_sales"]))
            if d.get("comparison_type") == "usd"
            else Decimal("-5")
        )
        if not (
            d["comparison_type"] in {"usd", "yoy_percent"}
            and upper.is_finite()
            and upper <= cutoff
            and iso <= date.fromisoformat(c["latest_filed"])
            and d["url"].startswith("https://")
            and d["basis"]
            and d["publication_date_evidence"]
            and d["coverage"]
            and all(x["url"].startswith("https://") and x["detail"] for x in d["coverage"])
        ):
            raise ValueError(f"Invalid verified disclosure for {key}")


def checked_review(c, directory: Path, archives: Path | None, previous: dict | None = None):
    """Retain the raw response and require a supported numeric endpoint for dated labels."""
    key = research(c, directory, archives, previous)
    path = directory / f"{key}.json"
    record = read(path)
    try:
        validate_source(c, record, key)
    except ValueError as exc:
        if not record.get("basis") or not record.get("coverage"):
            raise
        record = {
            **record,
            "raw_review": record,
            "date": None,
            "comparison_type": None,
            "upper_bound": None,
            "basis": f"Date withheld by deterministic source validation ({exc}). Original assessment: {record['basis']}",
        }
    return record


def import_sources(chosen, reviews, out, rescues=None):
    records = {}
    for c in chosen:
        k = f"{c['cik']}_{c['end']}"
        p = reviews / f"{k}.json"
        d = read(p)
        if rescues and not d.get("date"):
            rescue = read(rescues / f"{k}.json")
            original = d
            d = {
                **rescue,
                "initial_review": original["basis"],
                "initial_review_coverage": original["coverage"],
            }
        validate_source(c, d, k)
        records.setdefault(c["cik"], {})[c["end"]] = d
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "capture", "archive", "research", "rescue", "import"])
    parser.add_argument("--run", type=Path, default=DATA / "run")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--rescues", type=Path)
    parser.add_argument("--identity")
    parser.add_argument("--workers", type=int, default=4)
    opts = parser.parse_args()
    required = {
        "capture": ["cache", "archives", "identity"],
        "archive": ["archives"],
        "research": ["reviews"],
        "rescue": ["reviews", "rescues"],
        "import": ["reviews"],
    }
    for field in required.get(opts.action, []):
        if not getattr(opts, field):
            parser.error(f"{opts.action} requires --{field}")
    selected = cases(opts.run)
    if opts.action == "list":
        print(json.dumps(selected))
    elif opts.action == "capture":
        capture(selected, opts.cache, opts.archives, opts.identity)
    elif opts.action == "archive":
        archive_manifest(selected, opts.archives, opts.run / "scorer/filing_inventory.json")
    elif opts.action == "research":
        opts.reviews.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=opts.workers) as pool:
            tasks = [pool.submit(research, c, opts.reviews, opts.archives) for c in selected]
            for task in tasks:
                print(task.result(), flush=True)
    elif opts.action == "rescue":
        opts.rescues.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=opts.workers) as pool:
            tasks = []
            for c in selected:
                raw = opts.reviews / f"{c['cik']}_{c['end']}.json"
                if raw.exists() and raw.stat().st_size:
                    previous = read(raw)
                    if not previous.get("date"):
                        tasks.append(pool.submit(research, c, opts.rescues, opts.archives, previous))
            for task in tasks:
                print(task.result(), flush=True)
    elif opts.action == "import":
        # Research drafts precede independent quarter/amount/date adjudication.
        # Re-running retrieval must preserve the reviewed scoring fixture.
        import_sources(selected, opts.reviews, opts.run / "scorer/research_draft.json", opts.rescues)
