"""Select a development roster from four SEC submissions tables without reading financial values."""

from __future__ import annotations

import argparse
import calendar
import csv
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

SEED = "sector-watch-dev-v1"
PER_SECTOR = 6
PILOT_CIKS = {str(cik).zfill(10) for cik in (764478, 354950, 885639, 60667, 794367, 27419)}
SECTORS = {
    "retail": [(5200, 5999)],
    "food_manufacturing": [(2000, 2099)],
    "industrial_machinery": [(3500, 3569), (3580, 3599)],
    "semiconductors": [(3674, 3674)],
    "prepackaged_software": [(7372, 7372)],
    "transportation": [(4000, 4599)],
}
ROSTER_FIELDS = ["sector", "rank", "cik", "issuer", "sic", "filing_date", "accession", "filing_url"]


def sector_for(sic: str) -> str | None:
    if not sic.isdecimal():
        return None
    code = int(sic)
    return next(
        (
            sector
            for sector, ranges in SECTORS.items()
            if any(low <= code <= high for low, high in ranges)
        ),
        None,
    )


def sampling_key(cik: str) -> str:
    return sha256(f"{SEED}|{cik}".encode()).hexdigest()


def select(records: list[dict], skip_per_sector: int = 0) -> tuple[list[dict], dict[str, int]]:
    latest = {}
    for filing in records:
        if filing["form"] != "10-K" or not "20200101" <= filing["filed"] <= "20201231":
            continue
        cik = filing["cik"].zfill(10)
        if cik in PILOT_CIKS:
            continue
        key = (filing["filed"], filing["accepted"], filing["adsh"])
        if cik not in latest or key > latest[cik][0]:
            latest[cik] = (key, filing)
    eligible = {sector: [] for sector in SECTORS}
    for cik, (_, f) in latest.items():
        sector = sector_for(f["sic"])
        if (
            not sector
            or f["countryba"] != "US"
            or f["countryinc"] != "US"
            or f["afs"] not in {"1-LAF", "2-ACC"}
        ):
            continue
        accession = f["adsh"]
        filed = f["filed"]
        eligible[sector].append(
            {
                "sector": sector,
                "cik": cik,
                "issuer": f["name"],
                "sic": f["sic"],
                "filing_date": f"{filed[:4]}-{filed[4:6]}-{filed[6:]}",
                "accession": accession,
                "filing_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm",
            }
        )
    roster = []
    for sector, pool in eligible.items():
        stop = skip_per_sector + PER_SECTOR
        if len(pool) < stop:
            raise ValueError(f"Only {len(pool)} eligible issuers in {sector}")
        ordered = sorted(pool, key=lambda row: (sampling_key(row["cik"]), row["cik"]))
        roster.extend(
            {"rank": rank, **row}
            for rank, row in enumerate(ordered[skip_per_sector:stop], skip_per_sector + 1)
        )
    return roster, {key: len(pool) for key, pool in eligible.items()}


def observations(roster: list[dict], years: tuple[int, ...] = (2021, 2022, 2023)) -> list[dict]:
    rows = []
    for year in years:
        for quarter in range(1, 5):
            month = 3 * quarter
            cutoff = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
            for r in roster:
                rows.append(
                    {
                        "origin": f"{year}Q{quarter}",
                        "cutoff_us_eastern": cutoff,
                        "sector": r["sector"],
                        "cik": r["cik"],
                        "issuer": r["issuer"],
                    }
                )
    return rows


def write_table(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(source: Path, output: Path, joint_dev: bool = False) -> None:
    inputs, records = [], []
    for q in range(1, 5):
        name = f"2020q{q}"
        path = source / f"{name}-sub.txt"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            records.extend(csv.DictReader(stream, delimiter="\t"))
        inputs.append(
            {
                "archive": f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{name}.zip",
                "member": "sub.txt",
                "sha256": sha256(path.read_bytes()).hexdigest(),
            }
        )
    roster, pools = select(records, PER_SECTOR if joint_dev else 0)
    panel = observations(roster, (2024,)) if joint_dev else observations(roster)
    output.mkdir(parents=True, exist_ok=True)
    write_table(output / "companies.csv", ROSTER_FIELDS, roster)
    write_table(output / "company_quarters.csv", list(panel[0]), panel)
    manifest = {
        "stage": "development sampling frame only",
        "selection_as_of": "2020-12-31",
        "inputs": inputs,
        "industry_sic_ranges": SECTORS,
        "seed": SEED,
        "selection": "Most recent original 2020 10-K per CIK. US address and incorporation; large accelerated or accelerated filer. Select the six smallest SHA-256(seed|10-digit CIK) per sector.",
        "excluded_pilot_ciks": sorted(PILOT_CIKS),
        "eligible_issuers_by_sector": pools,
        "selected_by_sector": dict(Counter(r["sector"] for r in roster)),
        "company_count": len(roster),
        "cutoff_count": len({r["origin"] for r in panel}),
        "scheduled_company_cutoffs": len(panel),
        "scope": "Original roster at all 12 calendar-quarter ends; no later survivor filter or replacement. Future data collection must mark unavailable reports, exits, duplicate information vintages and unresolvable horizons explicitly.",
        "outputs_sha256": {
            p: sha256((output / p).read_bytes()).hexdigest()
            for p in ("companies.csv", "company_quarters.csv")
        },
    }
    if joint_dev:
        prior_path = Path(__file__).with_name("cross_industry_watch")
        prior = json.loads((prior_path / "selection.json").read_text())
        if prior["inputs"] != inputs or prior["seed"] != SEED:
            raise ValueError("Original roster inputs or seed differ from the recorded selection")
        with (prior_path / "companies.csv").open() as stream:
            prior_ciks = [r["cik"] for r in csv.DictReader(stream)]
        if prior_ciks != [r["cik"] for r in select(records)[0]]:
            raise ValueError("Original sector ranks 1 through 6 differ from the recorded cohort")
        manifest.update(
            selection="Same 2020 eligibility frame and seeded ranking as the first panel. Select ranks 7 through 12 per sector.",
            original_roster_sha256=prior["outputs_sha256"]["companies.csv"],
            scope="All selected companies at four consecutive 2024 calendar quarter ends. No survival filter or replacements.",
        )
    (output / "selection.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "submissions_directory",
        type=Path,
        help="directory containing 2020q1-sub.txt through 2020q4-sub.txt",
    )
    parser.add_argument("output_directory", type=Path)
    parser.add_argument(
        "--joint-dev",
        action="store_true",
        help="select ranks 7–12 for the 2024 independent development panel",
    )
    args = parser.parse_args()
    build(args.submissions_directory, args.output_directory, args.joint_dev)
