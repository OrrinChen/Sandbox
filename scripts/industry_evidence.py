"""Build point-in-time evidence packets from SEC submissions and original EDGAR filings.

Source acquisition can use the stdlib. Extracting original HTML additionally uses lxml.
A separate downstream scorer handles subsequent financial outcomes.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Lock
import time
from urllib.request import Request, urlopen

BASE = Path(__file__).parent / "cross_industry_watch"
DEMAND = {
    "retail": r"comparable (?:store )?sales|same.store sales|transactions|customer traffic|unit sales|comparable sales",
    "food_manufacturing": r"volume|product mix|sales mix|unit sales|units sold|pounds sold",
    "industrial_machinery": r"orders|backlog|bookings|order intake",
    "semiconductors": r"demand|shipments|units sold|unit sales|order rates",
    "prepackaged_software": r"subscription|bookings|retention|recurring revenue|customer renewals",
    "transportation": r"volume|load factor|traffic|tonnage|shipments|revenue passenger miles|freight|containers carried",
}
ASSETS = {
    "retail": r"inventor",
    "food_manufacturing": r"inventor",
    "industrial_machinery": r"backlog|supply chain|supply.chain|lead times|materials availability",
    "semiconductors": r"inventor",
    "prepackaged_software": r"deferred revenue|performance obligation|contract liabilit|unearned revenue",
    "transportation": r"capacity|utilization|available seat miles|fleet size|operating ratio",
}
SALES = r"\b(?:(?:net|total|consolidated) (?:sales|revenues?)|(?:sales|revenues?) (?:were|was|grew|increased|decreased|declined|rose|fell))\b"
MARGINS = r"\bpric(?:es?|ing)|cost of|input costs|freight costs|operating costs|margins?|expenses?"
OPERATING = r"operating (?:income|loss|profit|earnings)|income (?:from|before) operations|cash flows?|cash (?:provided|used|generated)"
FINANCIAL = re.compile(
    SALES
    + "|"
    + MARGINS
    + "|"
    + OPERATING
    + "|sales|revenue|inventor|orders|customer|shipments|volume|demand|turnover|capacity|bookings|subscription|backlog|performance obligation|traffic|load factor|gross profit|net (?:income|loss)",
    re.I,
)
HISTORICAL = re.compile(
    r"\b(?:was|were|had|have|has|increased|decreased|totaled|totalled|compared|declined|grew|rose|fell|continued|remained|resulted|experienced|impacted|affected|represented|contributed|attributable|incurred|generated|reported|reflects|driven|drove|improved|reduced|offset|higher|lower|unchanged|flat|realized)\b",
    re.I,
)
FORWARD = re.compile(
    r"\b(?:potential|guidance|forward.looking|outlook|expect(?:s|ed|ations?)?|will|anticipat\w*|forecast\w*|likely|could|would|may(?! [0-9])|might|intend\w*|projected|safe harbor)\b",
    re.I,
)
BOILER = re.compile(
    r"table of contents|incorporated by reference|refer to (?:note|item)|see (?:item|note|part) \d|should be read|accounting (?:standard|polic)|(?:recogniz|recognis)ed (?:when|upon|as)|revenue recognition|performance obligation is|consists? (?:primarily )?of|included in .* financial statements|reclassif|non.gaap measure|currency.neutral|law or regulation|financial statements (?:and|included)|management.s discussion and analysis|net operating loss carry|income tax benefit|at the lower of cost|net realizable value|as follows|calculated as|believes? that|we believe|the ability to|in addition to providing|non.gaap financial measures|historically been derived|this measurement reflects|rules? (?:allow|permit)|allows? for|is critical (?:for|to)|prior period amounts|tax effect|mathematical|presentation (?:of|is)|we define|is defined|included in the calculation|we calculate|we consider|are responsible|are permitted|method of accounting|as a percentage of|for purposes of|ri[sk]{2}s? associated|our sources of|principal sources of|performance obligations? (?:are|is) satisfied|difference between revenue|subject to (?:change|risk)|principally driven|is comprised|significant accounting",
    re.I,
)
MDA = re.compile(r"management.s discussion (?:and|&) analysis", re.I)
NEXT = re.compile(
    r"^(?:(?:item|part)\s*(?:3|4|7a|8)\s*[:.\-]?\s*)?(?:quantitative and qualitative disclosures about market risk|controls and procedures|financial statements and supplementary data)\b",
    re.I,
)
SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[$])")
SPACE = re.compile(r"\s+")
RATE_LOCK = Lock()
PREVIOUS = 0.0


def read(path):
    return json.loads(path.read_bytes())


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def download(url, path, identity, compress=False):
    global PREVIOUS
    if path.exists():
        return
    for attempt in range(4):
        try:
            with RATE_LOCK:
                time.sleep(max(0.0, 0.24 - (time.monotonic() - PREVIOUS)))
                PREVIOUS = time.monotonic()
            with urlopen(
                Request(url, headers={"User-Agent": identity}), timeout=40
            ) as response:
                raw = response.read()
                if response.headers.get("Content-Range") and not response.headers[
                    "Content-Range"
                ].endswith("/" + str(len(raw))):
                    raise ValueError("Partial SEC content")
                if len(raw) < 250 or b"Your Request Originates" in raw[:3000]:
                    raise ValueError("Invalid SEC document")
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(gzip.compress(raw) if compress else raw)
            tmp.replace(path)
            return
        except (ValueError, OSError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)


def filings(cache, cik, identity, through="2023-12-31"):
    path = cache / (cik + ".json")
    download("https://data.sec.gov/submissions/CIK" + cik + ".json", path, identity)
    index = read(path)["filings"]
    lists = [index["recent"]]
    for description in index["files"]:
        if (
            description["filingFrom"] <= through
            and description["filingTo"] >= "2020-01-01"
        ):
            name = description["name"]
            download("https://data.sec.gov/submissions/" + name, cache / name, identity)
            lists.append(read(cache / name))
    result = []
    for group in lists:
        for idx, filed in enumerate(group["filingDate"]):
            if "2020-01-01" <= filed <= through and group["form"][idx] in {
                "10-K",
                "10-Q",
            }:
                filing = {
                    key: group[key][idx]
                    for key in (
                        "filingDate",
                        "reportDate",
                        "acceptanceDateTime",
                        "form",
                        "primaryDocument",
                        "primaryDocDescription",
                        "accessionNumber",
                    )
                }
                acc = filing["accessionNumber"].replace("-", "")
                filing["url"] = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{filing['primaryDocument']}"
                )
                result.append(filing)
    write(cache / (cik + "-filings.json"), result)
    return result


def anchor(records, cutoff):
    return max(
        (
            r
            for r in records
            if r["filingDate"] <= cutoff
            and r["reportDate"]
            and r["reportDate"] <= cutoff
        ),
        key=lambda r: (
            r["reportDate"],
            r["filingDate"],
            r["acceptanceDateTime"],
            r["accessionNumber"],
        ),
        default=None,
    )


def clean(value):
    return SPACE.sub(" ", value).strip()


def sentences(value):
    start = 0
    for boundary in SENT_END.finditer(value):
        if re.search(
            r"(?:\b[A-Z]|\bU\.S|\bInc|\bCorp|\bNo|\be\.g|\bi\.e)\.$",
            value[start : boundary.start()],
        ):
            continue
        yield value[start : boundary.start()]
        start = boundary.end()
    if start < len(value):
        yield value[start:]


def spans(source):
    from lxml import html

    body = html.fromstring(
        source, parser=html.HTMLParser(encoding="utf-8", huge_tree=True)
    )
    tree = body.getroottree()
    for el in body.xpath("//script|//style|//noscript|//*[local-name()='ix:header']"):
        el.drop_tree()
    # Filers use both div/span typography and ordinary block elements. Use leaf
    # blocks exactly once; a table row remains one locatable original span.
    positioned = body.xpath(
        "//div[starts-with(@style,'position:absolute;') and contains(@style,'left:') and contains(@style,'top:')]"
    )
    if len(positioned) > 100:
        # Some filers use absolutely positioned lines per page, containing inline divs.
        # Join only successive text lines on one page and expose both locator endpoints.
        run = []
        last_page = last_top = None
        result = []

        def flush():
            if run:
                first, last = run[0][1], run[-1][1]
                locator = first if first == last else first + " through " + last
                result.append((" ".join(v for v, _ in run), locator, "div"))
                run.clear()

        for el in positioned:
            value = clean("".join(el.itertext()))
            style = el.get("style")
            coord = re.search(r"top:([0-9.]+)px", style)
            if not coord or any(
                child is not el
                and child.tag == "div"
                and "position:absolute" in child.get("style", "")
                for child in el.iterdescendants()
            ):
                continue
            top = float(coord.group(1))
            parent = tree.getpath(el.getparent())
            if (
                not value
                or parent != last_page
                or last_top is None
                or not 5 < top - last_top < 25
                or (run and (len(run[-1][0]) < 50 or re.search(r"[.!?:]$", run[-1][0])))
            ):
                flush()
            if value:
                run.append((value, tree.getpath(el)))
            last_top = top
            last_page = parent
        flush()
        return clean(body.findtext(".//title", default="") or ""), result
    blocks = body.xpath(
        "//p[not(descendant::table) and not(ancestor::tr)] | //div[not(descendant::div or descendant::p or descendant::table or ancestor::p or ancestor::tr)] | //li[not(descendant::div or descendant::p or descendant::table or ancestor::tr)] | //h1|//h2|//h3|//h4|//h5|//h6|//tr[not(descendant::tr)]"
    )
    values = []
    title = clean(body.findtext(".//title", default="") or "")
    for el in blocks:
        if el.tag == "tr":
            cells = [clean("".join(td.itertext())) for td in el.xpath("./td|./th")]
            value = " ".join(c for c in cells if c)
        else:
            value = clean("".join(el.itertext()))
        if not value:
            continue
        values.append((value, tree.getpath(el), el.tag))
    return title, values


def eligible_sentence(sentence):
    if (
        not 8 <= len(sentence.split()) <= 100
        or len(sentence) > 665
        or sentence.rstrip().endswith(":")
    ):
        return False
    return bool(
        FINANCIAL.search(sentence)
        and HISTORICAL.search(sentence)
        and re.search(
            r"\d|\b(?:increased|decreased|experienced|growth|gained|improved|impacted|affected|reduced|resulted|declined|higher|lower|grew|stronger|weaker|recovered|disruptions?|shortages?|slower|decline|reduction|continued|deferrals?)\b",
            sentence,
            re.I,
        )
        and not FORWARD.search(sentence)
        and not BOILER.search(sentence)
    )


def extract(raw, sector):
    title, blocks = spans(raw)
    # Pick the occurrence without TOC page numbers when a real heading is present.
    candidates = [
        i for i, (v, _, _) in enumerate(blocks) if len(v) <= 175 and MDA.search(v)
    ]
    headings = [
        i
        for i in candidates
        if not re.search(r"\s\d{1,3}\s*$", blocks[i][0])
        and not re.search("see item|under item|refer to", blocks[i][0], re.I)
    ]
    start = (headings or candidates or [None])[-1]
    end = (
        next(
            (
                i
                for i in range(start + 1, len(blocks))
                if len(blocks[i][0]) < 175 and NEXT.search(blocks[i][0])
            ),
            len(blocks),
        )
        if start is not None
        else 0
    )
    regions = [[], []]
    tables = []
    for i, (value, path, tag) in enumerate(blocks):
        is_mda = start is not None and start < i < end
        for sent in sentences(value):
            if eligible_sentence(sent):
                regions[0 if is_mda else 1].append((sent, path))
        if (
            tag == "tr"
            and FINANCIAL.search(value)
            and re.search(r"\d", value)
            and 3 <= len(value.split()) <= 45
        ):
            # Preserve original neutral headings when they belong to this table.
            # Multi-line representations are assembled only from contiguous table elements.
            prev = [
                b
                for b in blocks[max(i - 6, 0) : i]
                if b[1].rsplit("/tr", 1)[0] == path.rsplit("/tr", 1)[0]
            ]
            headers = [
                b[0]
                for b in prev
                if re.search(
                    r"\b20\d{2}\b|(?:three|six|nine|twelve) months ended", b[0], re.I
                )
            ]
            if headers:
                tables.append((value, path, headers))
    predicates = [SALES, DEMAND[sector], ASSETS[sector], MARGINS, OPERATING]
    available = {}
    used = set()
    for slot, pattern in zip("ABCDE", predicates):
        selected = next(
            (
                (s, p, "slot_match", [])
                for s, p in regions[0]
                if s not in used
                and re.search(pattern, s, re.I)
                and not (
                    slot == "A"
                    and re.search(
                        r"revenues? per|sales per|segment (?:net )?(?:revenue|sales)",
                        s,
                        re.I,
                    )
                )
            ),
            None,
        )
        if selected:
            used.add(selected[0])
            available[slot] = selected
    for slot in "ABCDE":
        if slot in available:
            continue
        selected = next(
            (
                (s, p, "operating_fallback", [])
                for region in regions
                for s, p in region
                if s not in used
            ),
            None,
        )
        if not selected:
            selected = next(
                ((s, p, "table_fallback", h) for s, p, h in tables if s not in used),
                None,
            )
        if selected:
            used.add(selected[0])
            available[slot] = selected
    return title, available


def build_origin(origin, rows, cache, evidence, known_extractions):
    cutoff = rows[0]["cutoff_us_eastern"]
    co = []
    for r in rows:
        result = {key: r[key] for key in ("cik", "issuer", "sector")}
        result.update(
            period_end=None,
            filing_date=None,
            accession=None,
            form=None,
            source_url=None,
            title=None,
            slots=[],
        )
        records = read(cache / (r["cik"] + "-filings.json"))
        document = anchor(records, cutoff)
        if not document:
            result.update(
                status="missing_anchor",
                reason="No qualifying original filing in submission metadata.",
            )
            co.append(result)
            continue
        f = document
        accession = f["accessionNumber"]
        result.update(
            period_end=f["reportDate"],
            filing_date=f["filingDate"],
            accession=accession,
            form=f["form"],
            source_url=f["url"],
            title=f["primaryDocDescription"] or f["form"],
        )
        today = date.fromisoformat(cutoff)
        if (today - date.fromisoformat(f["reportDate"])).days > 185 or (
            today - date.fromisoformat(f["filingDate"])
        ).days > 135:
            result.update(
                status="stale",
                reason="Latest available filing exceeds the preregistered age bound.",
            )
        else:
            path = cache / (accession + ".html.gz")
            if not path.is_file():
                result.update(
                    status="incomplete",
                    reason="Original SEC primary document unavailable in cache.",
                )
            else:
                if accession not in known_extractions:
                    raw = gzip.decompress(path.read_bytes())
                    html_title, snippets = extract(raw, r["sector"])
                    known_extractions[accession] = (
                        sha256(raw).hexdigest(),
                        html_title,
                        snippets,
                    )
                digest, html_title, snippets = known_extractions[accession]
                result["document_sha256"] = digest
                result["title"] = f["primaryDocDescription"] or html_title or f["form"]
                for slot, (text, locator, selection, headings) in sorted(
                    snippets.items()
                ):
                    result["slots"].append(
                        dict(
                            id=slot,
                            text=text,
                            locator=locator,
                            selection=selection,
                            headings=headings,
                            title=result["title"],
                            date=f["filingDate"],
                            url=f["url"],
                        )
                    )
                if len(snippets) == 5:
                    result.update(status="complete", reason="")
                else:
                    result.update(
                        status="incomplete",
                        reason=f"Only {len(snippets)} eligible original excerpts found.",
                    )
        co.append(result)
    write(
        evidence / (origin + ".json"), dict(origin=origin, cutoff=cutoff, companies=co)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["acquire", "build"])
    parser.add_argument("cache", type=Path)
    parser.add_argument("--panel", type=Path, default=BASE, help="registered panel directory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--origin")
    parser.add_argument(
        "--identity", help="Your contact-bearing User-Agent for SEC access"
    )
    args = parser.parse_args()
    args.cache.mkdir(exist_ok=True, parents=True)
    if not (args.panel / "protocol_lock.json").exists():
        parser.error("Lock the protocol before collecting evidence.")
    output = args.output or args.panel / "run/evidence"
    with (args.panel / "company_quarters.csv").open() as file:
        rows = list(csv.DictReader(file))
    if args.origin:
        rows = [r for r in rows if r["origin"] == args.origin]
        if not rows:
            parser.error("Unknown origin")
    if args.action == "acquire":
        if not args.identity:
            parser.error("Supply --identity for SEC acquisition.")
        grouped = {}
        for row in rows:
            grouped.setdefault(row["cik"], []).append(row["cutoff_us_eastern"])
        tasks = {}
        for cik, cutoffs in grouped.items():
            records = filings(args.cache, cik, args.identity, max(cutoffs))
            for cutoff in cutoffs:
                f = anchor(records, cutoff)
                if f:
                    tasks[f["accessionNumber"]] = f

        def fetch(pair):
            accession, f = pair
            download(
                f["url"], args.cache / (accession + ".html.gz"), args.identity, True
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, tasks.items()))
    else:
        processed = {}
        for origin in sorted({r["origin"] for r in rows}):
            build_origin(
                origin,
                [r for r in rows if r["origin"] == origin],
                args.cache,
                output,
                processed,
            )


if __name__ == "__main__":
    main()
