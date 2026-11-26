"""Build 32 synthetic development questions with complete, fixed five-excerpt evidence."""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from random import Random
import re


SCALE = {"usd": 1, "usd_thousands": 1_000, "usd_millions": 1_000_000}
LETTERS = "ABCDE"
AMOUNT_RE = re.compile(r"(?P<amount>\(?-?\d[\d,]*(?:\.\d+)?\)?) USD(?P<unit> thousands| million)?\b")
ISSUERS = (
    "Alderwake Navigation", "Brae Hollow Optics", "Cairnforge Assembly", "Dunemist Logistics",
    "Elmfen Medical", "Frostmere Controls", "Gullstrand Storage", "Hazelrift Services",
    "Ironbay Materials", "Junipercliff Systems", "Kestrelvale Supply", "Larkfen Instruments",
    "Marlbrook Industries", "Norhaven Fixtures", "Oakspire Platforms", "Plovermere Foods",
    "Quillstone Works", "Ravenquay Manufacturing", "Sablewick Networks", "Thistlebridge Transit",
    "Umberport Energy", "Violetdune Utilities", "Wrenhollow Water", "Yewstrand Components",
    "Zephyrmoor Software", "Ambercrest Fabrics", "Brindlefen Machinery", "Copperglen Packaging",
    "Dovemere Pumps", "Eiderglen Mobility", "Flintwater Process", "Graniterill Thermal",
)


def _text(value, unit):
    suffix = {"usd": "USD", "usd_thousands": "USD thousands", "usd_millions": "USD million"}[unit]
    n = Decimal(value)
    shown = f"({abs(n):,})" if n < 0 else f"{n:,}"
    return f"{shown} {suffix}"


def _direct(i, year):
    item, other = [
        ("equipment sale proceeds", "equipment purchase payments"),
        ("maintenance fees collected", "maintenance reimbursements paid"),
        ("service receivables", "service refunds payable"),
        ("rebates received", "rebates disbursed"),
        ("insurance recoveries", "insurance deductibles paid"),
        ("license collections", "license administration fees paid"),
        ("warranty recoveries", "warranty repair payments"),
        ("port concessions received", "port access charges paid"),
    ][i]
    a, b = str(370_511 + i * 11_427), f"{152 + i * 2}.{127 + i}"
    question = (
        f"For FY{year}, subtract the {other} in the annual filing from the {item} in the annual filing. "
        "Give the signed result in thousands of US dollars."
    )
    texts = [
        f"Annual filing, FY{year}. {item.capitalize()}: {_text(a, 'usd')}.",
        f"Annual filing, FY{year}. {other.capitalize()}: {_text(b, 'usd_thousands')}.",
        f"Annual filing, FY{year - 1}. {item.capitalize()}: {_text('359.713', 'usd_thousands')}.",
        f"Investor presentation, FY{year}. {other.capitalize()}: {_text('163.887', 'usd_thousands')}.",
        f"Annual filing, FY{year}. Staff travel and training: {_text('9.5', 'usd_thousands')}.",
    ]
    return "direct", question, texts, [(0, a, "usd", 1), (1, b, "usd_thousands", -1)], "usd_thousands"


def _restatement(i, year):
    gross = f"{21 + i}.{146 + 7 * i}"
    prior = f"{19 + i}.{924 - 11 * i}"
    credits = str(1_827_603 + i * 29_619)
    adjustment = str(87_927 + i * 17_173)
    question = (
        f"On the amended annual-filing basis for FY{year}, how much larger were net service proceeds than "
        f"the comparable restated FY{year - 1} net figure? Build the bridge from FY{year} gross service proceeds, "
        f"then deduct FY{year} credits and FY{year} levy, then deduct the restated FY{year - 1} net figure. "
        "Give the signed difference in US dollars."
    )
    texts = [
        f"Annual filing amendment, note 2. Service proceeds, gross. Current FY{year}: "
        f"{_text(gross, 'usd_millions')}; comparative FY{year - 1}: {_text('20.159', 'usd_millions')}. "
        "Use separate credits and levy for the current net figure.",
        f"Annual filing amendment, note 7. Customer credits reducing FY{year} proceeds: "
        f"{_text(credits, 'usd')}. An estimate in the original release was {_text('1.71', 'usd_millions')}.",
        f"Annual filing amendment, note 8. Levy FY{year}: {_text(adjustment, 'usd')}. "
        f"The levy is reported as a positive expense. FY{year - 1} levy is already in the amended net comparative.",
        f"Annual filing amendment, note 14. Net service proceeds, comparative FY{year - 1}, restated: "
        f"{_text(prior, 'usd_millions')}; net before restatement {_text('18.411', 'usd_millions')}.",
        f"Original annual filing, superseded by amendment. Net service proceeds FY{year}: "
        f"{_text('20.185', 'usd_millions')}; comparative FY{year - 1}: {_text('18.411', 'usd_millions')}.",
    ]
    ops = [(0, gross, "usd_millions", 1), (1, credits, "usd", -1),
           (2, adjustment, "usd", -1), (3, prior, "usd_millions", -1)]
    return "restatement", question, texts, ops, "usd"


def _calendar(i, year):
    exit_balance = str(920_317 + i * 23_145)
    opening = f"{841 + i * 13}.{331 + i}"
    transfer = f"{36 + i}.{371 + 7 * i}"
    question = (
        f"For the first 13 weeks of FY{year + 1}, what was the organic increase in deferred service revenue "
        "in millions of US dollars? Use the quarter's closing balance first, subtract the opening balance, "
        "then subtract the acquired balance added during that quarter. Use closing dates in the company's fiscal calendar."
    )
    texts = [
        f"Fiscal calendar in annual filing. FY{year} closed 2 February {year + 1}. "
        f"The first 13 weeks of FY{year + 1} closed 4 May {year + 1}.",
        f"Quarterly filing, revenue contract schedule. 4 May {year + 1} closing deferred service revenue: "
        f"{_text(exit_balance, 'usd_thousands')}. Closing comparative 5 May {year}: {_text('903617', 'usd_thousands')}.",
        f"Annual filing, audited contract schedules at 2 February {year + 1}. Opening balance for the next quarter: "
        f"{_text(opening, 'usd_millions')} deferred service revenue. This equals the closing balance of FY{year}.",
        f"Quarterly filing, business combinations. Acquired deferred service revenue entered the ledger during the 13 weeks "
        f"through 4 May {year + 1}: {_text(transfer, 'usd_millions')}. Acquisition contract assets are separate.",
        f"Investor presentation dated 31 March {year + 1}, calendar-Q1 update. Deferred service revenue: "
        f"{_text('907291', 'usd_thousands')}; acquisition contract assets {_text('38.261', 'usd_millions')}.",
    ]
    ops = [(1, exit_balance, "usd_thousands", 1), (2, opening, "usd_millions", -1),
           (3, transfer, "usd_millions", -1)]
    # Include the fiscal calendar in the citations because the question makes it evidence for the dates.
    return "fiscal_calendar", question, texts, ops, "usd_millions"


def _cash_bridge(i, year):
    gross = f"{42 + 3 * i}.{437 + 7 * i}"
    refund = f"-{5 + i}.{627 + 9 * i}"
    in_kind = str(3_791_273 + 819_461 * i)
    reserve = f"-{1589 + 281 * i}.{475 + 7 * i}"
    question = (
        f"Compute FY{year} net cash from the settlement in thousands of US dollars. Start with the cash receipt line. "
        "Add the signed bank-refund line, subtract the goods received in kind that the bank schedule included "
        "in the receipt line, then subtract the signed noncash reserve release included in the bank-refund line. "
        "Use the posted settlement ledger."
    )
    texts = [
        f"Posted settlement ledger FY{year}, treasury cash receipt line: {_text(gross, 'usd_millions')}. "
        "The bank schedule used a gross basis and includes the goods received in kind.",
        f"Posted settlement ledger FY{year}, signed bank-refund line: {_text(refund, 'usd_millions')}. "
        "Parentheses show a negative contribution. The posting includes the noncash reserve release.",
        f"Posted settlement ledger FY{year}, footnote: goods received in kind included in the receipt line: "
        f"{_text(in_kind, 'usd')}.",
        f"Posted settlement ledger FY{year}, footnote to the refund posting: signed noncash reserve release "
        f"included in the refund line: {_text(reserve, 'usd_thousands')}.",
        f"Posted settlement ledger FY{year}, book view. Receipts before reserve movements: "
        f"{_text('41.961', 'usd_millions')}. Goods purchased in kind outside the settlement: {_text('3.673', 'usd_millions')}.",
    ]
    ops = [(0, gross, "usd_millions", 1), (1, refund, "usd_millions", 1),
           (2, in_kind, "usd", -1), (3, reserve, "usd_thousands", -1)]
    return "signed_cash_bridge", question, texts, ops, "usd_thousands"


def _segment(i, year):
    close = f"{67 + i * 4}.{437 + 7 * i}"
    opening = str(61_682 + i * 4_291)
    movement = f"{3 + i}.{813 + i * 7}"
    consolidation = f"-{1704 + 511 * i}.{703 + i * 13}"
    question = (
        f"For the North segment on the new boundary, give FY{year} year-over-year organic movement "
        "in US dollars. Start with current reported North on the new boundary, deduct the prior-year old-boundary "
        "North, deduct the prior-year amount moved into North in the recast, and remove the signed current-year consolidation adjustment."
    )
    texts = [
        f"Annual report FY{year}, current segment table. In columns North new boundary / North legacy view, "
        f"reported operating income is {_text(close, 'usd_millions')} / {_text('68.911', 'usd_millions')}.",
        f"Annual report FY{year}, unaudited old-boundary comparative. FY{year - 1} North operating income: "
        f"{_text(opening, 'usd_thousands')}. North as shown here excludes the transferred depots.",
        f"Annual report FY{year}, recast footnote. To convert FY{year - 1} North from the old to the new boundary, "
        f"add {_text(movement, 'usd_millions')} for the transferred depots.",
        f"Annual report FY{year}, consolidation bridge. Current North new-boundary reported operating income includes "
        f"the signed consolidation adjustment {_text(consolidation, 'usd_thousands')}.",
        f"Annual report FY{year}, corporate segment table. South operating income under the new boundary: "
        f"{_text('61.633', 'usd_millions')}; company-wide adjustment {_text('-2.117', 'usd_millions')}.",
    ]
    ops = [(0, close, "usd_millions", 1), (1, opening, "usd_thousands", -1),
           (2, movement, "usd_millions", -1), (3, consolidation, "usd_thousands", -1)]
    return "boundary_recast", question, texts, ops, "usd"


def _revision(i, year):
    goods = str(4_576_137 + i * 433_541)
    cost = f"{3 + i}.{473 + i * 37}"
    rebate = f"{104 + i * 17}.{319 + i * 11}"
    question = (
        f"Calculate the FY{year} retained margin on the two amended vendor ledgers in millions of US dollars. "
        "Take booked recovery under revision 4, deduct the fulfillment cost restated under revision 3, "
        "then add the cash rebate under revision 4. When a table includes both versions, use its version caption."
    )
    texts = [
        f"Vendor ledger, FY{year}. Booked recovery, row R10. The first column is revision 4 and the second "
        f"is revision 3. R10: {_text(goods, 'usd')} | {_text('4481220', 'usd')}.",
        f"Vendor ledger, FY{year}. Fulfillment cost, row F12. Columns left to right are revision 2 then revision 3. "
        f"F12: {_text('3.099', 'usd_millions')} | {_text(cost, 'usd_millions')}.",
        f"Vendor ledger, FY{year}. Cash rebate, row B10. Columns left to right are revision 3 then revision 4. "
        f"B10: {_text('190.841', 'usd_thousands')} | {_text(rebate, 'usd_thousands')}.",
        f"Vendor ledger, FY{year}. Booked recovery R10 under revision 3: {_text('4481220', 'usd')}; "
        f"estimated rebates for FY{year + 1}: {_text('151.27', 'usd_thousands')}.",
        f"Vendor ledger, FY{year}. Fulfillment cost F12 under revision 4: {_text('3.207', 'usd_millions')}. "
        "This revision changes the cost basis and is not comparable to the specified bridge.",
    ]
    ops = [(0, goods, "usd", 1), (1, cost, "usd_millions", -1), (2, rebate, "usd_thousands", 1)]
    return "versioned_tables", question, texts, ops, "usd_millions"


def _near_cancel(i, year):
    sales = f"{98_037 + i * 192}.{391 + 11 * i}"
    cost = str(97_845_613 + i * 192_771)
    clawback = f"{31 + i}.{849 + 7 * i}"
    rebate = f"-{3 + i}.{751 + 9 * i}"
    question = (
        f"For FY{year}, what is the signed incremental margin in thousands of US dollars on the posted basis? "
        "Begin with sale proceeds posted, subtract posted charge, subtract the cash clawback, then subtract "
        "the signed rebate reversal (remove that reversal from the margin). Carry the full precision of the source amounts."
    )
    texts = [
        f"Annual filing FY{year} adjustment register. Sale proceeds posted: {_text(sales, 'usd_thousands')}. "
        f"The rounded management KPI shows {_text('98.0', 'usd_millions')}.",
        f"Annual filing FY{year} adjustment register. Posted charge: {_text(cost, 'usd')}. "
        f"The comparator without incentives is {_text('97951437', 'usd')}.",
        f"Annual filing FY{year} adjustment register. Cash clawback: {_text(clawback, 'usd_thousands')}. "
        "The provision is a different measure.",
        f"Annual filing FY{year} adjustment register. Signed rebate reversal: {_text(rebate, 'usd_thousands')}. "
        "Parentheses indicate a negative balance.",
        f"Annual filing FY{year} adjustment register, presentation-only bridge. Cash clawback provision: "
        f"{_text('46.713', 'usd_thousands')}. Prior cash clawback: {_text('39.501', 'usd_thousands')}.",
    ]
    ops = [(0, sales, "usd_thousands", 1), (1, cost, "usd", -1),
           (2, clawback, "usd_thousands", -1), (3, rebate, "usd_thousands", -1)]
    return "near_cancellation", question, texts, ops, "usd_thousands"


def build():
    layout = [(_direct, i) for i in range(8)]
    layout.extend((template, i) for template in (
        _restatement, _calendar, _cash_bridge, _segment, _revision, _near_cancel,
    ) for i in range(4))
    rng = Random(173204)
    rng.shuffle(layout)
    public, private = [], []
    for row, (issuer, (template, index)) in enumerate(zip(ISSUERS, layout), 1):
        year = 2021 + row % 5
        family, question, texts, ops, unit = template(index, year)
        order = rng.sample(range(5), k=5)
        ref = {index: letter for letter, index in zip(LETTERS, order)}
        evidence = [{"ref": letter, "text": f"{issuer}. {texts[source]}"} for letter, source in zip(LETTERS, order)]
        operands = [{"ref": ref[source], "value": value, "unit": source_unit, "sign": sign}
                    for source, value, source_unit, sign in ops]
        answer = sum(Decimal(value) * SCALE[source_unit] * sign for _, value, source_unit, sign in ops) / SCALE[unit]
        public.append({"row": row, "question": f"{issuer}. {question}", "evidence": evidence})
        citations = [operand["ref"] for operand in operands]
        if family == "fiscal_calendar":
            citations.append(ref[0])
        private.append({"row": row, "family": family, "issuer": issuer, "verdict": "answer",
                        "answer_value": format(answer, "f"), "unit": unit,
                        "evidence_ids": sorted(citations), "operands": operands, "operation": "net"})
    return public, private


def verify(public, private):
    from fractions import Fraction

    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer

    assert len(public) == len(private) == len(ISSUERS) == 32
    assert len(set(ISSUERS)) == 32
    assert Counter(label["family"] for label in private) == {
        "direct": 8, "restatement": 4, "fiscal_calendar": 4, "signed_cash_bridge": 4,
        "boundary_recast": 4, "versioned_tables": 4, "near_cancellation": 4,
    }
    for case, label in zip(public, private):
        assert case["row"] == label["row"]
        assert set(case) == {"row", "question", "evidence"}
        excerpts = {part["ref"]: part["text"] for part in case["evidence"]}
        assert list(excerpts) == list(LETTERS) and len(set(excerpts.values())) == 5
        assert all(text.startswith(label["issuer"] + ". ") for text in excerpts.values())
        terms = []
        for operand in label["operands"]:
            candidates = []
            for match in AMOUNT_RE.finditer(excerpts[operand["ref"]]):
                amount = match["amount"].replace(",", "")
                value = -Fraction(amount[1:-1]) if amount.startswith("(") else Fraction(amount)
                unit = {None: "usd", " thousands": "usd_thousands", " million": "usd_millions"}[match["unit"]]
                if value == Fraction(operand["value"]) and unit == operand["unit"]:
                    candidates.append(value * SCALE[unit] * operand["sign"])
            (term,) = candidates
            terms.append(term)
        assert sum(terms) / SCALE[label["unit"]] == Fraction(label["answer_value"])
        answer = json.dumps({"verdict": "answer", "answer_value": label["answer_value"],
                             "unit": label["unit"], "citations": label["evidence_ids"]})
        hits = [{"evidence_id": ref} for ref in excerpts]
        assert score_answer(label, answer, hits, 5).passed
        for citation in label["evidence_ids"]:
            assert not score_answer(label, answer, [hit for hit in hits if hit["evidence_id"] != citation], 5).passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/financial-self-audit-dev"))
    args = parser.parse_args()
    public, private = build()
    verify(public, private)
    hashes = {}
    for name, data in (("public/questions.json", public), ("private/labels.json", private)):
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        path.write_bytes(payload)
        hashes[name] = sha256(payload).hexdigest()
    (args.output / "fixture_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(public)} complete top-five development cases at {args.output}")


if __name__ == "__main__":
    main()
