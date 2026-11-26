"""Build held-out credit-loss and fund-valuation questions from new synthetic documents."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
import json
from random import Random

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer


REFS = "ABCDE"
ISSUERS = (
    "Moonbass Hallow Credit",
    "Moonbass Keelstone Finance",
    "Moonbass Tarnmill Receivables",
    "Moonbass Wychfen Lending",
    "Moonbass Quayshore Credit",
    "Moonbass Briar Bank",
    "Moonbass Heathbar Lending",
    "Moonbass Arrowstone Finance",
    "Moonbass Chalkmere Credit",
    "Moonbass Hartling Bank",
    "Moonbass Ternacre Fund",
    "Moonbass Highwater Trust",
    "Moonbass Maple Weir Capital",
    "Moonbass Torstead Strategies",
    "Moonbass Deepfen Partners",
    "Moonbass Whitemill Fund",
    "Moonbass Baythorpe Capital",
    "Moonbass Sandrow Strategies",
    "Moonbass Copperfold Partners",
    "Moonbass Clearcut Fund",
)


def _rounded(value: Fraction) -> int:
    """Round a rational cent amount to cents, with ties away from zero."""
    if value < 0:
        return -_rounded(-value)
    return int(value + Fraction(1, 2))


def _dollars(cents: int) -> str:
    return f"{Decimal(cents).scaleb(-2):.2f}"


def _decimal_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _table(columns: str, rows: list[tuple]) -> str:
    return "\n" + columns + "\n" + "\n".join(" | ".join(map(str, row)) for row in rows)


def _credit_loss(variant: int, rng: Random) -> tuple[str, list[tuple[str, str]], int, set[int]]:
    easy = variant < 4
    has_amendment = variant >= 8
    periods = (2, 3, 3, 3, 4, 4, 4, 5, 7, 8)[variant]
    discount_percent = (100, 99, 100, 98, 99, 98, 97, 96, 98, 97)[variant]
    hazard_shift = (0, 0, 0, 0, 25, -20, 45, -15, 35, -29)[variant]
    shift_start = (1, 1, 1, 1, 2, 3, 2, 3, 3, 4)[variant]
    year = 2028 + variant % 3
    rows = []
    for period in range(1, periods + 1):
        if easy:
            base = rng.choice((100, 200, 250, 300, 400))
            exposure = rng.randrange(125, 800) * 10_000
            severity = rng.choice((20, 25, 40, 50, 60))
            coverage = rng.randrange(3, 33) * 1_000
        else:
            base = rng.randrange(95, 607)
            exposure = rng.randrange(15_000_193, 119_000_083) if has_amendment else rng.randrange(1210, 6500) * 1000
            severity = rng.randrange(23, 58)
            coverage = rng.randrange(110_317, 390_731)
        rows.append((period, base, exposure, severity, coverage))
    amendment_period = periods - 2
    amendment = (amendment_period, 214 + variant, 27_689_173 + 281_733 * variant, 48, 97_213 + 3_091 * variant)
    effective_rows = [amendment if has_amendment and row[0] == amendment_period else row for row in rows]

    surviving = Fraction(1)
    discounted_loss = Fraction(0)
    discount = Fraction(discount_percent, 100)
    for period, base, exposure, severity, coverage in effective_rows:
        hazard = Fraction(base + (hazard_shift if period >= shift_start else 0), 10_000)
        exposure_loss = max(Fraction(0), exposure * Fraction(severity, 100) - coverage)
        discounted_loss += surviving * hazard * exposure_loss * discount**period
        surviving *= 1 - hazard
    expected = _rounded(discounted_loss)

    # Independently value the same event stream by rolling the conditional expectation backward.
    with localcontext() as ctx:
        ctx.prec = 80
        conditional_loss = Decimal(0)
        for period, base, exposure, severity, coverage in reversed(effective_rows):
            current_hazard = Decimal(base) / 10_000
            if period >= shift_start:
                current_hazard += Decimal(hazard_shift) / 10_000
            recovery_net = max(Decimal(0), Decimal(exposure) * severity / 100 - coverage)
            conditional_loss = (current_hazard * recovery_net + (1 - current_hazard) * conditional_loss) * discount_percent / 100
        assert _decimal_cents(conditional_loss) == expected

    opening_note = (
        f"Approved FY{year} lifetime allowance worksheet for pool C. Initial survival is 100%. "
        f"The booked valuation covers periods 1 through {periods}, inclusive. The signed period table pages are the full horizon."
    )
    method_note = (
        "For each period, multiply opening survival by the adjusted conditional PD to get that period's default probability. "
        "Survival carried to the next period is opening survival less this default probability. "
        "If default occurs, loss equals the positive part of exposure times LGD less the listed guarantee recovery. "
        "Apply the recovery only in computing loss given default. Sum the probability-weighted discounted losses. "
        "Keep full precision and round the total once to USD cents, half up."
    )
    assumptions = (
        f"Use discount factor ({discount_percent}/100) to the power of the period number. "
        f"Conditional PD is stated in basis points. From period {shift_start}, inclusive, apply a signed adjustment of "
        f"{hazard_shift:+d} basis points to each period's listed conditional PD. LGD is a percent."
    )
    docs = [
        ("allowance-close", opening_note + (" " + method_note + " " + assumptions if easy else " " + method_note)),
    ]
    mid = (periods + 1) // 2

    def page(start: int, end: int) -> str:
        return _table(
            "Period | Base conditional PD (bp) | Exposure (USD) | LGD (%) | Guarantee recovery (USD)",
            [(i, base, _dollars(x), severity, _dollars(g)) for i, base, x, severity, g in rows[start:end]],
        )

    docs.extend([
        ("pool-c-table-1", f"Signed FY{year} pool C period table, first page. Values are measured at period end." + page(0, mid)),
        ("pool-c-table-2", f"Signed FY{year} pool C period table, continuation. The period numbers continue from page 1." + page(mid, periods)),
    ])
    required = {0, 1, 2}
    if easy:
        docs.append(("workshop-summary", "Internal workshop attendance record. The topics were travel booking and expense approval."))
    else:
        docs.append(("signed-scenario-rider", f"Approved FY{year} pool C measurement rider. {assumptions}"))
        required.add(3)
    if has_amendment:
        p, base, exposure, severity, coverage = amendment
        docs.append((
            "posted-replacement",
            f"Posted correction for FY{year} pool C. Replace every data field of period {p} in the signed period table. "
            f"The corrected base conditional PD is {base} bp, exposure USD {_dollars(exposure)}, LGD {severity}%, "
            f"and guarantee recovery USD {_dollars(coverage)}. The rider still determines the PD adjustment.",
        ))
        required.add(4)
    else:
        docs.append(("unbooked-pool-k", "Unsigned acquisition memo for proposed pool K in the next fiscal year. "
                     "The preliminary guarantee proposal never entered the active pool C worksheet."))
    return f"What is the booked FY{year} lifetime credit loss for pool C, in US dollars?", docs, expected, required


def _fund_nav(variant: int, rng: Random) -> tuple[str, list[tuple[str, str]], int, set[int]]:
    easy = variant < 4
    has_amendment = variant >= 8
    periods = (2, 2, 3, 3, 4, 4, 4, 5, 6, 7)[variant]
    year = 2029 + variant % 3
    units = 20_000 + (variant % 4) * 5000 if easy else rng.randrange(40_111, 90_891)
    start_price = 100 + variant * 3
    start_assets = start_price * 100 * units if easy else rng.randrange(97_088_777, 868_063_599)
    start_mark = Fraction(start_assets, units)
    expense_credit = 0 if easy else 31 + 13 * variant
    credit_start = 2 + (variant % 3)
    rows = []
    for period in range(1, periods + 1):
        if easy:
            change = (-1 if period == 1 and variant in (1, 3) else 1) * rng.randrange(12, 87) * units
            expense = rng.randrange(2, 11) * units
            dealing = rng.choice((-5000, 0, 5000, 10_000))
            bps = rng.choice((750, 1250, 1500, 2000))
        else:
            change = rng.randrange(-21_013_319, 38_983_129) if has_amendment else rng.randrange(-117, 302) * units
            expense = rng.randrange(103_113, 1_880_391) if has_amendment else rng.randrange(2, 19) * units
            dealing = rng.randrange(-3091, 5123)
            bps = rng.randrange(533, 1890)
        crystallizes = period in (1, periods) or period % 3 == 0
        rows.append((period, change, expense, dealing, bps, crystallizes))

    replaced_period = periods - 1
    old = rows[replaced_period - 1]
    replacement = (replaced_period, old[1], old[2], old[3] + 713, old[4], old[5])
    effective_rows = [replacement if has_amendment and row[0] == replaced_period else row for row in rows]
    assets = Fraction(start_assets)
    count = units
    mark = start_mark
    for period, change, expense, dealing, bps, crystallizes in effective_rows:
        expense_factor = Fraction(10_000 - (expense_credit if period >= credit_start else 0), 10_000)
        before_fee = assets + change - expense * expense_factor
        gap = max(Fraction(0), before_fee - count * mark)
        price = (before_fee - (gap * Fraction(bps, 10_000) if crystallizes else 0)) / count
        if crystallizes:
            mark = max(mark, price)
        count += dealing
        assert count > 0
        assets = count * price
    expected = _rounded(assets)

    # Calculate amounts and high-water marks in per-unit space, without carrying total assets.
    with localcontext() as ctx:
        ctx.prec = 80
        count = units
        mark = price = Decimal(start_assets) / units
        for period, change, expense, dealing, bps, crystallizes in effective_rows:
            rebate = Decimal(0) if period < credit_start else Decimal(expense) * expense_credit / 10_000
            price += (Decimal(change - expense) + rebate) / count
            if crystallizes and price > mark:
                price -= (price - mark) * bps / 10_000
                mark = price
            count += dealing
        assert _decimal_cents(price * count) == expected

    control_note = (
        f"Signed FY{year} class V close mandate. Begin with USD {_dollars(start_assets)} of net assets and {units:,} "
        f"issued units just before period 1. The signed close is immediately after the dealing event in period {periods}."
    )
    method_note = (
        "The opening high-water mark is opening net assets divided by opening units. On each period, add the signed "
        "fair-value movement and subtract the permitted operating expense. Before dealing, divide those assets by opening "
        "units for the pre-fee price. If the tape shows crystallization, deduct the fee rate times the positive difference "
        "between that price and the high-water mark from the price. Set the mark to the greater of the old mark and this post-fee price. "
        "Otherwise the mark remains unchanged and no performance fee is charged. At this resulting price, process the "
        "signed dealing units and update the unit count. Carry price, count, and mark forward. Closing net assets are "
        "closing units times closing price. Keep full precision and round the final USD total once, half up to cents."
    )
    rebate_note = (
        f"From period {credit_start}, inclusive, the permitted expense is gross expense times "
        f"(10,000 - {expense_credit}) / 10,000. Earlier periods use the full gross expense."
    )
    mid = (periods + 1) // 2

    def page(start: int, end: int) -> str:
        return _table(
            "Period | Fair-value movement (USD) | Gross expense (USD) | Signed dealing units | Fee rate (bp) | Crystallizes",
            [(i, _dollars(a), _dollars(b), u, fee, "yes" if flag else "no") for i, a, b, u, fee, flag in rows[start:end]],
        )

    docs = [
        ("class-v-control", control_note + " " + method_note + (" " + rebate_note if easy else "")),
        ("valuation-tape-1", f"Signed FY{year} class V operations tape, first page." + page(0, mid)),
        ("valuation-tape-2", f"Signed FY{year} class V operations tape, final page." + page(mid, periods)),
    ]
    required = {0, 1, 2}
    if easy:
        docs.append(("trustee-minutes", "Trustees approved the office move and the lease renewal. Fund valuation was outside the agenda."))
    else:
        docs.append(("expense-rider", f"Authorized FY{year} class V operating-expense rider. {rebate_note} "
                     "This rider applies to operating expenses only. The dealing tape supplies the crystallization rate."))
        required.add(3)
    if has_amendment:
        docs.append(("dealing-posted-correction",
                     f"Signed FY{year} transfer-agent correction for class V. At period {replaced_period}, "
                     f"the net signed dealing unit count is {replacement[3]:+d}. "
                     "Replace only the signed dealing units field for that period; all other tape fields carry forward."))
        required.add(4)
    else:
        docs.append(("Class-U-brochure", "Class U marketing brochure for a future currency-hedged sleeve. "
                     "The indicative mark is for class U only."))
    return f"What are FY{year} closing net assets for class V, in US dollars?", docs, expected, required


def build() -> tuple[list[dict], list[dict]]:
    """Return unique held-out row and label pairs with locally numbered IDs."""
    rng = Random(65022117)
    public, labels = [], []
    for variant, issuer in enumerate(ISSUERS):
        family, maker = (
            ("survival_weighted_credit_loss", _credit_loss) if variant < 10 else ("dealing_nav_waterfall", _fund_nav)
        )
        question, docs, amount, required = maker(variant % 10, rng)
        assert len(docs) == len(REFS)
        order = list(range(len(docs)))
        rng.shuffle(order)
        reference = dict(zip(order, REFS))
        row = variant + 1
        evidence = [{
            "ref": reference[index],
            "document_id": f"blind-moonbass/{row:02}/{docs[index][0].lower()}",
            "text": f"{issuer} | {docs[index][1]}",
        } for index in order]
        public.append({"row": row, "issuer": issuer, "question": f"{issuer}. {question}", "evidence": evidence})
        label = {
            "row": row,
            "family": family,
            "verdict": "answer",
            "answer_value": _dollars(amount),
            "unit": "usd",
            "evidence_ids": sorted(reference[i] for i in required),
        }
        answer = {field: label[field] for field in ("verdict", "answer_value", "unit")} | {"citations": label["evidence_ids"]}
        hits = [{"evidence_id": hit["ref"]} for hit in evidence]
        assert score_answer(label, json.dumps(answer), hits, 5).passed
        for missing in label["evidence_ids"]:
            assert not score_answer(label, json.dumps(answer), [h for h in hits if h["evidence_id"] != missing], 5).passed
        labels.append(label)
    return public, labels
