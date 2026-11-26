"""Build the second 32-question financial self-audit development fixture."""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from random import Random

from build_financial_self_audit_pilot import AMOUNT_RE, LETTERS, SCALE, _text


ISSUERS = (
    "Ashmarsh Systems", "Briarbank Transit", "Cindervale Motion", "Dalecrest Foods",
    "Ebbfen Medical", "Foxweir Controls", "Garnetreach Pumps", "Hailbank Storage",
    "Ivorwick Fabrication", "Jackpine Optics", "Kelpstone Energy", "Lanternfell Shipping",
    "Mosscreek Process", "Northwold Networks", "Ospreyward Materials", "Pineberth Utility",
    "Quarrybank Marine", "Rushford Services", "Saltfen Components", "Tarnheath Packaging",
    "Ulverpoint Machinery", "Vetch Harbor Works", "Wickerburn Assembly", "Yarrowbay Water",
    "Zincshore Logistics", "Aukridge Devices", "Bluefern Thermal", "Crownmire Mobility",
    "Driftacre Software", "Embermill Supply", "Fairloch Fixtures", "Gladeford Textiles",
)
USD, K, M = "usd", "usd_thousands", "usd_millions"


def amount(cents: int, unit: str) -> str:
    return _text(str(Decimal(cents).scaleb(-2)), unit)


def compliance(rng, i):
    """Effectiveness is determined by filing lineage and active certification."""
    values = (rng.randrange(760_000_000, 980_000_000), rng.randrange(390_000_000, 510_000_000),
              rng.randrange(3_300_000_000, 4_500_000_000), rng.randrange(28_000_000, 48_000_000),
              rng.randrange(11_000_000, 19_000_000), rng.randrange(9_000_000, 17_000_000))
    units = K, K, USD, USD, USD, USD
    a, b, c, d, e, f = [amount(value, unit) for value, unit in zip(values, units)]
    year = 2022 + i
    active, pending = (("J2", "J3") if i % 2 else ("J3", "J2"))
    texts = [
        f"Capital policy index. The operative reporting cycle is the last quarter-end with an active compliance "
        f"certificate. The liquidity headroom worksheet is consolidated gross eligible cash less client escrow, "
        f"less posted collateral, plus collateral release settled by close, less transfer reserves, plus the "
        f"overlap already counted in collateral and transfer reserves. Each signed balance is used as recorded.",
        f"Capital certification register. 29 January {year}: {pending} pending, {active} active. "
        f"30 April {year}: K7 signed for disclosure only, effectiveness deferred. The {active} January "
        f"certificate applies to Treasury tables with the suffix B and reserve schedules filed under close code 61.",
        f"Treasury tables, 29 January {year}, eligible cash / client escrow / posted collateral. Table B: "
        f"{a} | {b} | {c}. The draft table A shows 8,445,006.93 USD thousands "
        f"| 4,900,031.17 USD thousands | 41,068,205.57 USD. Table A is retained in the filing to show the draft.",
        f"Collateral settlement log. 27 January {year}, release to eligible accounts: {d}. A further 316,773.62 USD "
        f"was authorized on 28 January and settled on 31 January. The April release of 471,206.94 USD cleared on 29 April.",
        f"Reserve schedule, close code 61, January {year}. Transfer reserves: {e}. Posted collateral already included "
        f"in those reserves: {f}. Code 64 carries a planning reserve of 166,486.37 USD, including 91,355.17 USD of overlap.",
    ]
    return "compliance_certificate", "liquidity headroom", K, texts, values, units, (2, 2, 2, 3, 4, 4), (1,-1,-1,1,-1,1), (0, 1)


def calendar(rng, i):
    year = 2022 + i
    close_day = 27 if year == 2024 else 28
    values = (rng.randrange(50_000, 85_000), rng.randrange(39_000, 68_000),
              rng.randrange(3_000_000, 6_000_000), rng.randrange(470_000, 790_000),
              rng.randrange(70_000_000, 150_000_000), rng.randrange(13_000_000, 29_000_000))
    units = M, M, K, K, USD, USD
    a,b,c,d,e,f = [amount(value, unit) for value, unit in zip(values, units)]
    texts = [
        f"Reporting handbook. For the organic increase in deferred contract receipts, subtract opening total from "
        f"closing total over the latest complete 13-week cycle; remove acquisition-related increases (the balances "
        f"assumed plus their post-close billings); remove the FX movement and add currency effect already included "
        f"in the removed acquisition movements. The reconciliation follows that line order.",
        f"Fiscal calendar and close notice. Cycle 38 runs 28 January to {close_day} April {year}, inclusive, but 28 January is "
        f"the first operating day and opening balances are struck the previous evening. Cycle 39 is marked partial "
        f"in this release. The Gregorian March snapshot is not an approved cycle close.",
        f"Approved receipts ledger. Dates across are {close_day} April {year}, 28 January {year} end of day, "
        f"27 January {year} end of day, 31 March {year}; deferred contract receipt balances: {a} | "
        f"433.71 USD million | {b} | 720.19 USD million.",
        f"Acquisition note, Cycle 38. On closing 3 February {year}, assumed deferred receipts were {c}. Post-close "
        f"billings were {d}. Purchase price adjustment of 47,433.41 USD thousands is unrelated to deferred receipts.",
        f"Exchange bridge, Cycle 38. Change in the closing balance caused by FX: {e}. Included in both FX and "
        f"acquisition adjustments: {f}. An early draft used a 998,427.78 USD currency adjustment for Cycle 39.",
    ]
    return "noncalendar_close", "organic increase in deferred contract receipts", M, texts, values, units, (2,2,3,3,4,4), (1,-1,-1,-1,-1,1), (0,1)


def revisions(rng, i):
    year = 2022 + i
    values = (rng.randrange(50_000, 87_000), rng.randrange(7_100, 14_000),
              rng.randrange(41_000_000, 66_000_000), rng.randrange(440, 830),
              rng.randrange(35_000_000, 67_000_000), rng.randrange(7_000_000, 15_000_000))
    units = M, M, K, M, USD, USD
    a,b,c,d,e,f = [amount(value, unit) for value, unit in zip(values, units)]
    released, draft = (("R4", "R5") if i % 2 else ("R5", "R4"))
    texts = [
        "Margin reporting manual. Retained fulfillment margin uses the last board-accepted joint schedule. "
        "Begin with billed goods and billed services. Take out direct fulfillment cost and signed net returns. "
        "Deduct the gross freight holdback, then put back overlap with direct cost. Worksheet retains full precision.",
        f"Board records. {released} accepted for FY{year}; {draft} was transmitted afterwards but remained a reconciliation "
        f"draft. The accepted billing columns are named West, the direct-cost column named Maple, and accepted "
        f"returns/freight data are in binder F. Other captions have not been used in the approved margin.",
        f"Billing schedule FY{year}, column order East, West. Goods: 734.81 USD million | {a}. Services: "
        f"113.77 USD million | {b}. In the returns sheet, freight is disclosed gross to reconcile accounting classification.",
        f"Direct fulfillment cost schedule. Column order is Maple, Cedar. Fulfillment cost FY{year}: "
        f"{c} | 478,461.83 USD thousands. Standard-cost note of 413,792.87 USD thousands is for pricing simulations.",
        f"Binder F FY{year}, returns and freight. Signed net returns {d}; gross freight holdback {e}; portion of "
        f"freight holdback already in direct cost {f}. Binder H replaced estimated returns with 8.59 USD million but remains draft.",
    ]
    return "approved_version_join", "retained fulfillment margin", USD, texts, values, units, (2,2,3,4,4,4), (1,1,-1,-1,-1,1), (0,1)


def reversal(rng, i):
    year = 2022 + i
    values = (rng.randrange(1_080_000_000, 1_350_000_000), rng.randrange(440_000_000, 810_000_000),
              -rng.randrange(21_000_000, 41_000_000), rng.randrange(48_000_000, 82_000_000),
              -rng.randrange(33_000_000, 58_000_000), rng.randrange(6_000_000, 19_000_000))
    units = K, K, K, USD, USD, USD
    a,b,c,d,e,f = [amount(value, unit) for value, unit in zip(values, units)]
    texts = [
        "Treasury instructions. Net cash from the settlement uses the finalized general-ledger close; take receipt "
        "and disbursement lines in that order (subtract disbursements). Remove the signed refund accrual sitting "
        "inside the receipt line; deduct property received in kind; add the signed settled refund replacing the accrual; "
        "add the intragroup outgoing amount already reflected in the disbursement line. Parentheses denote negative.",
        f"Close control register. October {year} was finalized under batch 46. The bank's batch 47 was produced after "
        "finalization as a sensitivity, and was never posted. November is still open. The affected settlement's code is 831.",
        f"Batch 46 settlement ledger, code 831. Gross receipt line {a}; gross disbursement line {b}. "
        "The lines include the noncash accrual and the internal transfer respectively. For comparison, batch 47 receipt "
        "line 11,840,631.94 USD thousands was constructed using forecast proceeds.",
        f"Batch 46 close amendments, code 831. Signed refund accrual included in receipt {c}. "
        f"Property received in kind and booked in the receipt {d}. Property purchased separately: 904,431.53 USD.",
        f"Settlement reconciliation, batch 46, code 831. Signed refund clearing {e} (paid by close), "
        f"intragroup amount inside disbursements {f}. Additional 80,162.94 USD refund remained unapproved.",
    ]
    return "signed_reversals", "net cash from the settlement", K, texts, values, units, (2,2,3,3,4,4), (1,-1,-1,-1,1,1), (0,1)


def carveout(rng, i):
    year = 2022 + i
    values = (rng.randrange(43_000, 83_000), rng.randrange(33_000, 61_000),
              rng.randrange(3_700_000, 7_300_000), rng.randrange(2_300_000, 5_100_000),
              -rng.randrange(35_000_000, 59_000_000), rng.randrange(700, 970))
    units = M, M, K, K, USD, M
    a,b,c,d,e,f = [amount(value, unit) for value, unit in zip(values, units)]
    texts = [
        "Segment policy. Organic operating profit movement is current reported profit minus comparative reported profit, "
        "minus current transferred-in profit plus comparative transferred-in profit, less the signed current overlay, "
        "then less the current signed gain on facilities closed during the current reporting year. Use the mapping adopted "
        "for reporting and show only adjustments absent from the stated starting balances.",
        f"Segment filing calendar. The operating review describes the year ended 25 November {year} and maps the "
        f"comparative year ended 26 November {year-1}. The calendar December dashboard is administrative. "
        "The operating review kept mapping S3; mapping S4 was proposed for the next period.",
        f"Segment schedule S3. Current reported profit {a}; comparative reported profit {b}. Both are before "
        "exclusion of the facility disposal and include the overlay on the applicable lines. The current report "
        "also contains an earlier chart showing 721.90 USD million for calendar December.",
        f"Boundary note S3, transferred depots. Current profit {c}; comparative profit {d}. "
        "The wholly disposed East warehouse was never a transferred depot.",
        f"Operating profit notes S3. Signed overlay for the current period {e}. Gain on facilities closed during "
        f"the current reporting year {f}; facilities closed in the comparative year contributed 7.41 USD million.",
    ]
    return "carveout_comparative", "organic operating profit movement", USD, texts, values, units, (2,2,3,3,4,4), (1,-1,-1,1,-1,-1), (0,1)


def rate_basis(rng, i):
    year = 2022 + i
    values = (rng.randrange(7_700, 9_500), rng.randrange(7_600_000_000, 9_100_000_000),
              rng.randrange(2_600, 5_800), rng.randrange(3_100, 5_800),
              rng.randrange(1_300, 2_900), rng.randrange(880_000_000, 940_000_000),
              rng.randrange(21_000_000, 39_000_000))
    units = M, USD, M, M, M, USD, K
    a,b,c,d,e,f,g = [amount(value, unit) for value, unit in zip(values, units)]
    active, future = (("51", "52") if i % 2 else ("52", "51"))
    texts = [
        "Disclosure method note. Subscription runoff equals opening billed base less closing billed base, "
        "less base disposed during the year, plus acquired base embedded in closing, less the post-acquisition "
        "uplift already part of acquired base, plus the pending transfer in closing that is held for a different "
        "reporting boundary, less the portion of pending transfer already counted in the disposed base. "
        "The regulatory perimeter register determines the reporting pack.",
        f"Regulatory perimeter register. FY{year} perimeter pack {active} was effective at close; pack {future} was "
        "filed the following day for the next cycle. The opening/closing amounts appear in exhibit N and bridge items "
        "in annex P and schedule Y. The exhibit names refer to the effective pack throughout.",
        f"Exhibit N, pack {active}. Opening billed base {a}; closing billed base {b}. The restatement appendix shows "
        "an illustrative opening base of 86.94 USD million under a different perimeter.",
        f"Annex P, pack {active}. Disposed base {c}; acquired base embedded in closing {d}; post-acquisition uplift "
        f"within that acquired base {e}. Run-rate acquisition pipeline of 12.84 USD million never entered the billed base.",
        f"Schedule Y, pack {active}. Pending transfer in closing {f}; pending transfer also inside disposed base {g}. "
        f"The immediate next-period pack {future} has no pending transfer.",
    ]
    return "perimeter_overlap", "subscription runoff", M, texts, values, units, (2,2,3,3,3,4,4), (1,-1,-1,1,-1,1,-1), (0,1)


def offset(rng, i):
    year = 2022 + i
    values = (rng.randrange(13_000_000_000, 16_000_000_000), rng.randrange(12_000, 15_000),
              rng.randrange(85_000_000, 135_000_000), rng.randrange(54_000_000, 89_000_000),
              rng.randrange(34_000_000, 73_000_000), -rng.randrange(1_000_000, 3_200_000))
    units = USD, M, USD, USD, USD, K
    a,b,c,d,e,f = [amount(value, unit) for value, unit in zip(values, units)]
    texts = [
        "Operating expense policy. Reported cash cost relief is comparative posted spend less current posted spend. "
        "Reduce that relief by comparative cost shifted out of the ledger; increase it by current cost shifted in. "
        "Take out the temporary grant included in current spend (reported as a spend reduction), and remove the "
        "signed accounting reclassification included in the relief. Use the cost-committee close.",
        f"Cost committee minute, 31 August {year}. Annual close stamped June R governs the investor measure. "
        "July P is a provisional renewal bridge that ignores two transfer accounts. Although P was added to the "
        "public binder after R, its signoff applies only to internal forecasts.",
        f"Cost ledger, June R. Comparative posted spend {a}; current posted spend {b}. Comparative cost shifted "
        f"out {c}. The alternative headline relief figure published with July P assumed no cost shifted out.",
        f"Transfer account bridge, June R. Current cost shifted in {d}; temporary grant reducing current spend {e}. "
        f"Signed accounting reclassification already in relief {f}; a related vendor prepayment is held off ledger.",
        f"Administrative note, July P. An illustrative cash cost relief of 47,918,660.23 USD was shown before transfer accounts. "
        "This notice contains internal forecasts and does not reopen June R.",
    ]
    return "temporary_offsets", "reported cash cost relief", USD, texts, values, units, (2,2,2,3,3,3), (1,-1,-1,1,-1,-1), (0,1)


def supersession(rng, i):
    year = 2022 + i
    values = (rng.randrange(71_000, 96_000), rng.randrange(3_500, 5_300),
              rng.randrange(12_000_000, 23_000_000), rng.randrange(2_100_000, 5_900_000),
              -rng.randrange(76_000_000, 98_000_000), rng.randrange(56_000_000, 79_000_000),
              rng.randrange(2_300_000, 6_700_000))
    units = M, M, K, K, USD, USD, K
    a,b,c,d,e,f,g = [amount(value, unit) for value, unit in zip(values, units)]
    texts = [
        "Close handbook. Distributable service proceeds means billed proceeds less customer credits, "
        "less deferred revenue carried forward, plus deferred revenue released, less signed tax accrued "
        "on behalf of partners, less one-time fees, plus the fees already embedded in the credits. "
        "Use the latest completed normal reporting year and amendments applicable to the line.",
        f"Filing register. The normal year ended 27 October {year}. The succeeding 3-week transition "
        f"period ended 17 November {year}, and uses a different disclosure basis. Revision L amended "
        "billed amounts and credits for the normal year; revision Q reopened deferrals and tax only. "
        "Revision Q does not repeal the already-closed revision L changes. Fees remain the schedule M balance.",
        f"Normal year, billed proceeds / credits. Revision Q's mirror of original headlines: 814.42 USD million "
        f"| 43.99 USD million. Revision L approved lines: {a} | {b}. The mirrored lines carry no amendment authority.",
        f"Normal year, revision Q. Deferred revenue carried forward {c}; deferred revenue released {d}; "
        f"signed tax accrued on behalf of partners {e}. Revision L's earlier deferral of 1,749,556.14 USD thousands was reopened.",
        f"Normal-year schedule M. One-time fees {f}; fees already included in the L credit line {g}. "
        f"An estimate of 85,697.39 USD thousands pertains to the transition period rather than the normal reporting year.",
    ]
    return "partial_supersession", "distributable service proceeds", K, texts, values, units, (2,2,3,3,3,4,4), (1,-1,-1,1,-1,-1,1), (0,1)


FAMILIES = (compliance, calendar, revisions, reversal, carveout, rate_basis, offset, supersession)


def build() -> tuple[list[dict], list[dict]]:
    rng = Random(860214)
    layout = [(family, index) for family in FAMILIES for index in range(4)]
    rng.shuffle(layout)
    public, private = [], []
    for row, (issuer, (case, index)) in enumerate(zip(ISSUERS, layout), 1):
        family, metric, unit, texts, values, units, sources, signs, context = case(rng, index)
        order = rng.sample(range(5), k=5)
        refs = dict(zip(order, LETTERS))
        operands = [{"ref": refs[source], "value": format(Decimal(value).scaleb(-2), "f"),
                     "unit": operand_unit, "sign": sign}
                    for source, value, operand_unit, sign in zip(sources, values, units, signs)]
        value = sum(Decimal(value).scaleb(-2) * SCALE[operand_unit] * sign
                    for value, operand_unit, sign in zip(values, units, signs)) / SCALE[unit]
        display_unit = {USD: "US dollars", K: "thousands of US dollars", M: "millions of US dollars"}[unit]
        public.append({"row": row, "question": f"{issuer}. What is the {metric} in {display_unit}?",
                       "evidence": [{"ref": refs[source], "text": f"{issuer}. {texts[source]}"} for source in order]})
        private.append({"row": row, "family": family, "issuer": issuer, "verdict": "answer",
                        "answer_value": format(value, "f"),
                        "unit": unit, "evidence_ids": sorted({refs[source] for source in (*sources, *context)}),
                        "operands": operands, "operation": "net"})
    return public, private


def verify(public: list[dict], private: list[dict]) -> None:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer

    assert len(public) == len(private) == len(ISSUERS) == len(set(ISSUERS)) == 32
    assert sorted(Counter(label["family"] for label in private).values()) == [4] * len(FAMILIES)
    for case, label in zip(public, private):
        assert case["row"] == label["row"] and set(case) == {"row", "question", "evidence"}
        excerpts = {entry["ref"]: entry["text"] for entry in case["evidence"]}
        assert list(excerpts) == list(LETTERS) and len(set(excerpts.values())) == 5
        signed_amounts = []
        for operand in label["operands"]:
            excerpt = excerpts[operand["ref"]]
            amounts = []
            for match in AMOUNT_RE.finditer(excerpt):
                raw = match["amount"].replace(",", "")
                value = -Fraction(raw[1:-1]) if raw.startswith("(") else Fraction(raw)
                unit = {None: USD, " thousands": K, " million": M}[match["unit"]]
                if (value, unit) == (Fraction(operand["value"]), operand["unit"]):
                    amounts.append(value * SCALE[unit] * operand["sign"])
            (verified_amount,) = amounts
            signed_amounts.append(verified_amount)
        assert sum(signed_amounts) / SCALE[label["unit"]] == Fraction(label["answer_value"])
        hits = [{"evidence_id": ref} for ref in excerpts]
        answer = {field: label[field] for field in ("verdict", "answer_value", "unit")}
        answer["citations"] = label["evidence_ids"]
        encoded = json.dumps(answer)
        assert score_answer(label, encoded, hits, 5).passed
        for required_ref in label["evidence_ids"]:
            assert not score_answer(label, encoded, [hit for hit in hits if hit["evidence_id"] != required_ref], 5).passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/financial-self-audit-implicit-dev"))
    args = parser.parse_args()
    public, private = build()
    verify(public, private)
    hashes = {}
    for relative, fixture in (("public/questions.json", public), ("private/labels.json", private)):
        payload = (json.dumps(fixture, ensure_ascii=False, indent=2) + "\n").encode()
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        hashes[relative] = sha256(payload).hexdigest()
    (args.output / "fixture_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(public)} implicit questions with complete fixed top-five evidence at {args.output}")


if __name__ == "__main__":
    main()
