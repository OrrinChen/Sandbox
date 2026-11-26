"""Run a chronologically sealed retail early-warning pilot on primary-source records."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import median

from run_multidim_development import seal
from run_financial_self_audit_pilot import digest, read, write
from run_financial_self_audit_blind import hashes, verify_hashes


DATA = Path(__file__).resolve().parent / "retail_watch"
DEFAULT_RUN = DATA.parents[1] / "artifacts/retail-watch-development"
QUARTERS = ("2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q1", "2023Q2")
ARMS = ("text", "metadata")
PROMPT = """You are assessing a retail portfolio at the end of the given cutoff date. Consider only
the six companies listed. Give alerts for at most two companies, possibly none. Use only this
packet and your own unaided judgment. Do not browse, open links, calculate with tools, inspect
other files, or use anything you know happened later. Use one response, at most 600 output tokens.
Target: within the NEXT TWO issuer fiscal quarters, reported consolidated quarterly net sales (or
total revenue if no net sales) fall by at least 5.00 percent versus the same quarter a year earlier,
after the immediately preceding quarter was above the -5.00 percent threshold. Staying below the
threshold is not a new event; recovery followed by a fresh crossing is. An already explicitly
disclosed crossing is not an early warning. Use reported numbers without calendar or acquisition
adjustments. No reward for filling empty slots. Only mark a company you would actually monitor for
this particular outcome. Cite facts only when they appear in your packet; distinguish judgment from
observation. Output a JSON object with origin and alerts, a list of {ticker, reason}, in priority
order, with one short concrete reason per alert. An empty alerts list is a valid decision.
"""


def protocol(root: Path) -> dict:
    lock = read(root / "protocol_lock.json")
    path = DATA / "protocol.json"
    if lock != {"protocol": read(path), "sha256": digest(path)}:
        raise ValueError("Protocol differs from preregistration")
    return lock["protocol"]


def register(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = DATA / "protocol.json"
    seal(root / "protocol_lock.json", {"protocol": read(path), "sha256": digest(path)})


def prepare(root: Path, origin: str) -> None:
    spec = protocol(root)
    index = QUARTERS[:4].index(origin)
    cutoff = spec["origins"][index]["cutoff"]
    if index:
        verify_hashes(root, read(root / QUARTERS[index - 1] / "alerts_lock.json"))
    packets = {arm: [] for arm in ARMS}
    source_files = []
    for ticker, company in spec["companies"].items():
        path = DATA / "evidence" / origin / (ticker + ".json")
        cell = read(path)
        source_files.append(path)
        if (
            cell["ticker"] != ticker
            or cell["origin"] != origin
            or cell["quarter_end"] >= cutoff
            or [s["ref"] for s in cell["slots"]] != list("ABCDE")
        ):
            raise ValueError(f"Wrong origin or slots for {ticker}")
        months = spec["origins"][index]["period_end_month"].split("/")
        if cell["quarter_end"][:7] not in (months[0], months[0][:5] + months[1]):
            raise ValueError(f"Quarter end outside registered fiscal period: {ticker}")
        for s in cell["slots"]:
            if (
                not cell["quarter_end"] <= s["published"] <= cutoff
                or not s["url"].startswith("https://")
                or any(
                    not isinstance(s[k], str) or not s[k].strip() for k in ("title", "locator", "text")
                )
            ):
                raise ValueError(f"Invalid dated source for {ticker} {s['ref']}")
        for arm in ARMS:
            fields = (
                ("title", "published", "locator", "text") if arm == "text" else ("title", "published")
            )
            packets[arm].append(
                {
                    "ticker": ticker,
                    "company": company,
                    "records": [{k: s[k] for k in fields} for s in cell["slots"]],
                }
            )
    files = [root / "protocol_lock.json"]
    if index:
        files.append(root / QUARTERS[index - 1] / "alerts_lock.json")
    for arm, companies in packets.items():
        folder = root / origin / arm
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "input.json"
        seal(path, {"prompt": PROMPT, "origin": origin, "cutoff": cutoff, "companies": companies})
        files.append(path)
    seal(
        root / origin / "input_lock.json",
        {
            "files": hashes(root, files),
            "sources": hashes(DATA, source_files),
            "prompt_sha256": sha256(PROMPT.encode()).hexdigest(),
        },
    )


def alerts(response: dict, spec: dict, origin: str) -> list[str]:
    choices = response["alerts"]
    if response.get("origin") != origin or not isinstance(choices, list):
        raise ValueError("Malformed alert response")
    names = []
    for a in choices:
        if (
            a["ticker"] not in spec["companies"]
            or not isinstance(a["reason"], str)
            or not a["reason"].strip()
        ):
            raise ValueError("Invalid company or empty reason")
        names.append(a["ticker"])
    if len(names) > spec["slots_per_origin"] or len(names) != len(set(names)):
        raise ValueError("Duplicate alert or exceeded budget")
    return names


def seal_alerts(root: Path, origin: str) -> None:
    spec = protocol(root)
    folder = root / origin
    lock = read(folder / "input_lock.json")
    verify_hashes(root, lock["files"])
    verify_hashes(DATA, lock["sources"])
    files = [folder / "input_lock.json"]
    for arm in ARMS:
        path = folder / arm / "response.json"
        alerts(read(path), spec, origin)
        files.append(path)
    seal(folder / "alerts_lock.json", hashes(root, files))
    if origin == QUARTERS[3]:
        seal(
            root / "prediction_lock.json",
            hashes(root, [root / q / "alerts_lock.json" for q in QUARTERS[:4]]),
        )


def evaluate_company(data: dict, ticker: str, origins: list[dict]) -> tuple[list[dict], dict]:
    quarters = data["quarters"]
    if data["ticker"] != ticker or [q["id"] for q in quarters] != list(QUARTERS):
        raise ValueError(f"Missing quarter in {ticker}")
    crossed, verified = {}, {}
    last_below = False
    for i, q in enumerate(quarters):
        sales, prior = Decimal(q["sales"]), Decimal(q["prior_year_sales"])
        if (
            min(sales, prior) <= 0
            or date.fromisoformat(q["quarter_end"]) > date.fromisoformat(q["report_date"])
            or not q["url"].startswith("https://")
            or not q["locator"]
        ):
            raise ValueError(f"Invalid resolution data for {ticker}")
        below = sales * 100 <= prior * 95
        if i and below and not last_below:
            crossed[q["id"]] = q
        last_below = below
    for d in data["disclosures"]:
        key = d["id"]
        if key in verified or key not in crossed:
            raise ValueError(f"Spurious or duplicate disclosure for {ticker} {key}")
        if d.get("date") is not None:
            day = date.fromisoformat(d["date"])
            if (
                day > date.fromisoformat(crossed[key]["report_date"])
                or not d["url"].startswith("https://")
                or not d["basis"]
                or not d["coverage"]
            ):
                raise ValueError(f"Incomplete first disclosure for {ticker} {key}")
        verified[key] = d
    if set(verified) != set(crossed):
        raise ValueError(f"Missing crossing disclosure or unresolved disclosure record for {ticker}")
    rows = []
    for i, o in enumerate(origins):
        horizon = QUARTERS[i + 1 : i + 3]
        event = next((verified[k] for k in horizon if k in verified), None)
        status, days = "absent", None
        if event:
            if event.get("date") is None:
                status = "unresolved"
            else:
                days = (date.fromisoformat(event["date"]) - date.fromisoformat(o["cutoff"])).days
                status = "positive" if days > 0 else "already_disclosed"
        rows.append(
            {
                "origin": o["id"],
                "cutoff": o["cutoff"],
                "ticker": ticker,
                "horizon": list(horizon),
                "status": status,
                "event": event["id"] if event else None,
                "first_disclosure": event.get("date") if event else None,
                "days_to_disclosure": days if status == "positive" else None,
            }
        )
    return rows, verified


def summarize(rows: list[dict], arm: str) -> dict:
    counts = Counter(r[arm]["result"] for r in rows)
    hit, false, miss, neg = (counts[k] for k in ("hit", "false_alarm", "miss", "correct_negative"))
    leads = [r["days_to_disclosure"] for r in rows if r[arm]["result"] == "hit"]
    return {
        "opportunities": len(rows),
        "alerts": sum(r[arm]["alert"] for r in rows),
        "hits": hit,
        "false_alarms": false,
        "misses": miss,
        "correct_negatives": neg,
        "unresolved": counts["unresolved"],
        "precision": hit / (hit + false) if hit + false else None,
        "recall": hit / (hit + miss) if hit + miss else None,
        "lead_days": leads,
        "median_lead_days": median(leads) if leads else None,
    }


def score(root: Path) -> None:
    spec = protocol(root)
    verify_hashes(root, read(root / "prediction_lock.json"))
    warnings = {}
    for origin in QUARTERS[:4]:
        path = root / origin
        verify_hashes(root, read(path / "alerts_lock.json"))
        lock = read(path / "input_lock.json")
        verify_hashes(DATA, lock["sources"])
        verify_hashes(root, lock["files"])
        warnings[origin] = {
            arm: alerts(read(path / arm / "response.json"), spec, origin) for arm in ARMS
        }
    rows, events = [], []
    labels = [DATA / "scorer" / (t + ".json") for t in spec["companies"]]
    outcome_hashes = hashes(DATA, labels)
    for path in labels:
        window_rows, disclosures = evaluate_company(read(path), path.stem, spec["origins"])
        for row in window_rows:
            for arm in ARMS:
                alert = row["ticker"] in warnings[row["origin"]][arm]
                positive = row["status"] == "positive"
                outcome = (
                    ("hit" if alert else "miss")
                    if positive
                    else ("false_alarm" if alert else "correct_negative")
                )
                row[arm] = {
                    "alert": alert,
                    "result": "unresolved" if row["status"] == "unresolved" else outcome,
                }
        rows.extend(window_rows)
        for key, disclosure in disclosures.items():
            eligible = [r for r in window_rows if r["event"] == key and r["status"] == "positive"]
            record = {
                "ticker": path.stem,
                "event": key,
                "disclosure": disclosure,
                "eligible_origins": [r["origin"] for r in eligible],
            }
            for arm in ARMS:
                first = next((r for r in eligible if r[arm]["alert"]), None)
                record[arm] = (
                    {"first_alert": first["cutoff"], "lead_days": first["days_to_disclosure"]}
                    if first
                    else None
                )
            events.append(record)
    rows.sort(key=lambda r: (r["origin"], r["ticker"]))
    report = {
        "protocol_sha256": digest(DATA / "protocol.json"),
        "prediction_lock_sha256": digest(root / "prediction_lock.json"),
        "outcome_sha256": outcome_hashes,
        "budget_per_arm_per_origin": spec["slots_per_origin"],
        "by_arm": {a: summarize(rows, a) for a in ARMS},
        "alerts": warnings,
        "distinct_crossings": events,
        "rows": rows,
    }
    seal(
        root / "resolution_lock.json",
        {
            "prediction_sha256": digest(root / "prediction_lock.json"),
            "outcomes": outcome_hashes,
            "scorer_sha256": digest(Path(__file__)),
        },
    )
    write(root / "report.json", report)
    with (root / "company_quarters.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "origin",
            "cutoff",
            "ticker",
            "status",
            "event",
            "first_disclosure",
            "days_to_disclosure",
            *ARMS,
        ]
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **{a: row[a]["result"] for a in ARMS}})


def replay(root: Path) -> None:
    """Regenerate all locks and regrade the original response bytes in a new directory."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("Replay requires an empty destination")
    archive = read(DATA / "recorded_alerts.json")
    register(root)
    for origin in QUARTERS[:4]:
        prepare(root, origin)
        for arm in ARMS:
            key = f"{origin}/{arm}/response.json"
            with (root / key).open("xb") as stream:
                stream.write(archive["responses"][key].encode("utf-8"))
        seal_alerts(root, origin)
    if digest(root / "prediction_lock.json") != archive["prediction_lock_sha256"]:
        raise ValueError("Rebuilt prediction lock differs from original recordings")
    score(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("register", "prepare", "seal-alerts", "score", "replay"))
    parser.add_argument("--root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--origin", choices=QUARTERS[:4])
    args = parser.parse_args()
    if args.action in ("prepare", "seal-alerts"):
        if not args.origin:
            parser.error("--origin is required")
        (prepare if args.action == "prepare" else seal_alerts)(args.root, args.origin)
    else:
        {"register": register, "score": score, "replay": replay}[args.action](args.root)
