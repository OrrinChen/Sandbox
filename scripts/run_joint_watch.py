"""Run and replay the independent development comparison of text and historical sales."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import run_industry_watch as watch

DATA = Path(__file__).with_name("joint_watch_dev")
ROOT = DATA / "run"


def historical_sales(issuer: dict, anchor: str | None, cutoff: str) -> dict:
    if not anchor:
        return {"quarters": [], "status": "no_fresh_anchor"}
    if issuer["anchor"] != anchor:
        raise ValueError("Text and numeric inputs have different fiscal anchors")
    rows = sorted(issuer["quarters"], key=lambda r: r["end"])
    if any(r["end"] > anchor or not r["latest_filed"] or r["latest_filed"] > cutoff for r in rows):
        raise ValueError("Historical trend includes a later quarter or filing")
    if not rows or rows[-1]["end"] != anchor:
        return {"quarters": [], "status": "missing_anchor_quarter"}
    latest = rows[-2:]
    if len(latest) == 2:
        interval = (date.fromisoformat(latest[1]["end"]) - date.fromisoformat(latest[0]["end"])).days
        if not 70 <= interval <= 112:
            latest = latest[-1:]
    quarters = []
    for row in latest:
        sales, prior = row["sales"], row["year_ago_sales"]
        rate = None
        if sales is not None and prior is not None and Decimal(str(prior)) > 0:
            rate = format((Decimal(str(sales)) / Decimal(str(prior)) - 1) * 100, ".4f")
        quarters.append(
            {
                "quarter_end": row["end"],
                "filed": row["latest_filed"],
                "reported_sales_usd": sales,
                "year_ago_reported_sales_usd": prior,
                "yoy_percent": rate,
            }
        )
    complete = len(quarters) == 2 and all(q["yoy_percent"] is not None for q in quarters)
    return {"quarters": quarters, "status": "complete" if complete else "incomplete"}


def packets(evidence: dict, trends: dict, registered: list[dict]) -> dict:
    text = watch.projections(evidence, registered)["text"]
    issuers = {r["cik"]: r for r in trends["issuers"]}
    evidence_by_cik = {r["cik"]: r for r in evidence["companies"]}
    if issuers.keys() != evidence_by_cik.keys() or len(issuers) != len(trends["issuers"]):
        raise ValueError("Trend roster mismatch")
    companies = []
    for company in text["companies"]:
        cik = company["cik"]
        source = evidence_by_cik[cik]
        anchor = None if source["status"] in ("stale", "missing_anchor") else source["period_end"]
        if not anchor and issuers[cik]["anchor"]:
            raise ValueError("Freshness differs between arms")
        companies.append(
            {**company, "historical_sales": historical_sales(issuers[cik], anchor, text["cutoff"])}
        )
    return {"text": text, "joint": {**text, "companies": companies}}


def verify_lock(root: Path = ROOT) -> None:
    watch.verify_lock(root, DATA)


def run_one(root: Path, origin: str, replay: bool = False) -> None:
    spec = watch.load(DATA / "protocol.json")
    if sha256(watch.PROMPT.encode()).hexdigest() != spec["baseline_prompt_sha256"]:
        raise ValueError("Prompt differs from the preregistered common prompt")
    watch.run_one(root, origin, replay, data=DATA, reader_packets=packets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["read", "replay", "verify"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--origin")
    args = parser.parse_args()
    if args.action == "verify":
        verify_lock(args.root)
    else:
        origins = (
            [args.origin]
            if args.origin
            else list(dict.fromkeys(r["origin"] for r in watch.schedule(DATA)))
        )
        for origin in origins:
            run_one(args.root, origin, args.action == "replay")
            print(f"{origin} sealed", flush=True)
