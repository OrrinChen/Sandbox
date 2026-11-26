"""Author held-out synthetic depreciation and FX-indexed financing cases."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
import json
from random import Random

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer


CENT = Decimal("1")
ASSET_NAMES = (
    "Verdigris Causeway Works", "Verdigris Beacon Foundry", "Verdigris Windrow Fabrication",
    "Verdigris Attic Storage", "Verdigris Cairn Logistics", "Verdigris Larch Components",
    "Verdigris Narrows Transit", "Verdigris Ashfold Milling", "Verdigris Dune Facilities",
    "Verdigris Tinleaf Energy",
)
FINANCE_NAMES = (
    "Verdigris Fenway Leasing", "Verdigris Eelwater Funding", "Verdigris Hazel Lending",
    "Verdigris Harbor Fleet", "Verdigris Mallow Equipment", "Verdigris Northbank Credit",
    "Verdigris Pact Tools", "Verdigris Longstep Capital", "Verdigris Saltline Packaging",
    "Verdigris Thicket Infrastructure",
)
REFS = "ABCDE"
ASSET_FAMILY = "asset_measurement_policy"
FX_FAMILY = "fx_indexed_financing"


def _money(cents: int) -> str:
    return f"{Decimal(cents).scaleb(-2):,.2f}"


def _round(cents: Fraction) -> int:
    magnitude = int(abs(cents) + Fraction(1, 2))
    return -magnitude if cents < 0 else magnitude


def _decimal_round(cents: Decimal) -> int:
    return int(cents.quantize(CENT, rounding=ROUND_HALF_UP))


def _table(columns: str, rows: list[tuple]) -> str:
    return columns + "\n" + "\n".join(" | ".join(map(str, row)) for row in rows)


def _simple_asset(rng: Random, variant: int) -> tuple[str, list[tuple[str, str]], tuple[int, ...], int]:
    period_end = (3, 5, 6, 4)[variant]
    assets = [(f"S{serial}", start, rng.randrange(28_000, 170_000) * 100,
               rng.randrange(0, 2_400) * 100, duration)
              for serial, start, duration in ((1, 1, 60), (2, 2, 48), (3, period_end + 1, 36))]
    exact = sum(Fraction(cost - salvage, duration) * max(0, period_end - start + 1)
                for _, start, cost, salvage, duration in assets)
    with localcontext() as context:
        context.prec = 70
        by_month = sum(Decimal(cost - salvage) / duration
                       for month in range(1, period_end + 1)
                       for _, start, cost, salvage, duration in assets if month >= start)
        assert _round(exact) == _decimal_round(by_month)
    excerpts = [
        ("signed-close", f"Controller's year-to-date close certificate. Count fiscal months 1 to {period_end}, "
         "both inclusive. Use the signed production-equipment schedule and the disclosed equipment policy. The next "
         "month's schedule remains open. Report only the expense charged in the certified window."),
        ("posted-equipment", "Production-equipment schedule, signed at close. Costs and residuals are USD. "
         "Month numbers identify when each asset first entered service. All listed equipment remains on the books.\n"
         + _table("Asset | First in service | Cost | Residual | Life in months",
                  [(code, start, _money(cost), _money(salvage), life)
                   for code, start, cost, salvage, life in assets])),
        ("measurement-policy", "Equipment measurement policy. Each active fiscal month charges one monthly "
         "straight-line amount equal to cost less residual, divided by the initial useful life in months. The "
         "first in-service month is active. Retain exact precision in the ledger and round the total once, to USD "
         "cents with half cents up."),
        ("training-copy", "Archived training extract for the packaging division. One worked example starts depreciation "
         "from the order date. The packaging policy ceased being an approved policy before the current close and "
         "does not govern production equipment."),
        ("project-forecast", "Funding presentation appendix. Depreciation on future production fixtures is a separate "
         f"forecast of USD {_money(rng.randrange(90_000, 200_000))}. The purchase itself was never posted."),
    ]
    return "production-equipment depreciation through the certified close", excerpts, (0, 1, 2), _round(exact)


def _moderate_asset(rng: Random, variant: int) -> tuple[str, list[tuple[str, str]], tuple[int, ...], int]:
    close = (7, 8, 6, 9)[variant]
    effective_month = (4, 5, 3, 6)[variant]
    retired_month = close - 1
    base = [rng.randrange(1_530_001, 21_891_193) for _ in range(3)]
    residual = [rng.randrange(53_701, 349_589) for _ in range(3)]
    life = (36, 54, 48)
    dates = ((1, None), (2, retired_month), (effective_month, None))
    adjustment = rng.randrange(112_237, 496_778)
    applied = variant % 2 == 0

    def basis(i: int, month: int) -> int:
        eligible_adjustment = adjustment if i == 0 and applied and month >= effective_month else 0
        return base[i] - residual[i] + eligible_adjustment

    exact = sum(
        Fraction(basis(i, month), life[i]) for i, (start, stop) in enumerate(dates)
        for month in range(start, min(close, (stop if stop else close + 1) - 1) + 1)
    )
    with localcontext() as context:
        context.prec = 70
        # Count active months as blocks, independent of the month-by-month policy evaluation.
        spans = [close, retired_month - 2, close - effective_month + 1]
        computed = sum(Decimal(base[i] - residual[i]) * active / life[i] for i, active in enumerate(spans))
        if applied:
            computed += Decimal(adjustment) * (close - effective_month + 1) / life[0]
        assert _round(exact) == _decimal_round(computed)

    close_doc = (
        f"Final fiscal close: complete through month {close}; the next posting batch is unapproved. "
        f"Adjustment voucher U9 became {'effective' if applied else 'deferred pending approval'} in month {effective_month}. "
        "Posted hardware service events and the approved base register identify the operating assets. "
        "The carrying-basis worksheet includes expense incurred from the first month of the current year."
    )
    movement_doc = (
        f"Posted service-event ledger. H1 entered service in month 1. H2 entered service in month 2 and ceased use in "
        f"month {retired_month}. H3 entered service in month {effective_month}; no H1 or H3 closure was posted. "
        f"Voucher U9 is a USD {_money(adjustment)} increase to H1 eligible basis, governed by the close's approval status. "
        "The movement memo with code U8 belongs to prototype hardware."
    )
    policy_doc = (
        "Posted hardware depreciation policy. For each month of service, charge (cost less residual) / stated life "
        "and carry that charge without rounding. Start in the entry month. The cessation month earns no depreciation. "
        "An effective U9 increases that same numerator beginning in its effective month, without retrospective "
        "adjustments and without resetting the denominator. Report the sum in USD cents, rounding half up only once."
    )
    excerpts = [
        ("fixed-asset-close", close_doc),
        ("asset-control-register", "Approved hardware register. The cost and residual columns are USD.\n"
         + _table("Asset | Cost | Residual | Life in months",
                  [(f"H{i+1}", _money(cost), _money(residual[i]), life[i]) for i, cost in enumerate(base)])),
        ("policy-straight-line", policy_doc),
        ("service-voucher-ledger", movement_doc),
        ("prototype-voucher", "Prototype voucher U8. The next release simulations replace all stated hardware lives "
         "with 45 months. These are training assumptions and the control register is unaffected."),
    ]
    return "hardware depreciation through the final close", excerpts, (0, 1, 2, 3), _round(exact)


def _hard_asset(rng: Random, variant: int) -> tuple[str, list[tuple[str, str]], tuple[int, ...], int]:
    basis = [rng.randrange(361_700_173, 2_463_182_918) for _ in range(4)]
    start = (1, 2, 4, 5)
    exit_month = 8 + variant
    close = 9 + variant
    change = 6 - variant
    classes = ("Dry", "Wet", "Dry", "Wet")
    switched = 0 if variant == 0 else 3
    rates = {
        "Dry": (rng.randrange(33_371, 41_959), rng.randrange(17_153, 28_941)),
        "Wet": (rng.randrange(49_283, 59_931), rng.randrange(62_133, 77_347)),
    }
    divisor = 1_000_000
    charged = Fraction()
    for i, cost in enumerate(basis):
        remaining = Fraction(cost)
        for month in range(start[i], close + 1):
            if i == 1 and month == exit_month:
                break
            version = int(month >= change)
            group = "Wet" if i == switched and version and classes[i] == "Dry" else classes[i]
            if i == switched and version and classes[i] == "Wet":
                group = "Dry"
            remaining *= 1 - Fraction(rates[group][version], divisor)
        charged += cost - remaining
    with localcontext() as context:
        context.prec = 70
        verified = Decimal(0)
        for i, cost in enumerate(basis):
            ending = exit_month - 1 if i == 1 else close
            months_old = min(ending, change - 1) - start[i] + 1
            months_new = ending - max(start[i], change) + 1
            current = classes[i]
            previous = rates[current][0]
            new_class = ({"Dry": "Wet", "Wet": "Dry"}[current] if i == switched else current)
            retained = (1 - Decimal(previous) / divisor) ** max(0, months_old)
            retained *= (1 - Decimal(rates[new_class][1]) / divisor) ** max(0, months_new)
            verified += Decimal(cost) * (1 - retained)
        assert _round(charged) == _decimal_round(verified)
    current_class = {"Dry": "Wet", "Wet": "Dry"}[classes[switched]]
    excerpts = [
        ("period-certification", f"Audited close for regulated plant. Fiscal month {close} is the last included month; "
         "the next month was left in trial status. Measure cumulative current-year depreciation, including charges "
         "earned on any retired item before its retirement month. The schedules show opening net asset balances."),
        ("net-carry-ledger", "Regulated plant measurement register. Opening remaining basis is the basis at each "
         "asset's first active month. No earlier depreciation belongs to the current-year charge.\n"
         + _table("Asset | First active month | Opening remaining basis USD | Initial class",
                  [(f"P{i+1}", start[i], _money(cost), classes[i]) for i, cost in enumerate(basis)])),
        ("procedure-rates", "Plant measurement note. Every active month charges opening remaining basis times the "
         "current monthly rate, reducing the basis by the unrounded charge. Both rate columns are integer parts "
         "per million. Retain full precision. Round only the cumulative charge at the approved close, to cents half up.\n"
         + _table("Class | Original | New", [(kind, *rate) for kind, rate in rates.items()])),
        ("approved-implementation", f"Board's approved implementation minute. New rates start in fiscal month {change}, "
         f"inclusive, for every still-active asset. P{switched+1} changes to class {current_class} on the same date. "
         "The change affects current and future charges only. No previous-month amount is restated."),
        ("posted-retirements", f"Retirement notice. P2 retires at the start of fiscal month {exit_month}, earning "
         "no charge that month or later. P1, P3 and P4 stay active through close. A trial posting would also retire "
         "P4 in the following month. That posting is outside the approved register."),
    ]
    return "regulated-plant depreciation through the audited close", excerpts, (0, 1, 2, 3, 4), _round(charged)


def _simple_fx(rng: Random, variant: int) -> tuple[str, list[tuple[str, str]], tuple[int, ...], int]:
    start = date(2025, 2 + variant, 7)
    days = (28, 30, 36, 24)[variant]
    end = start + timedelta(days=days)
    currency = ("EUR", "GBP", "CAD", "EUR")[variant]
    foreign_principal = rng.randrange(49_839_151, 193_982_072)
    fx = (107_500, 123_000, 73_400, 119_000)[variant]
    apr = (480, 450, 424, 500)[variant]
    exact = Fraction(foreign_principal) * Fraction(fx, 100_000) * Fraction(apr, 10_000) * Fraction(days, 360)
    with localcontext() as context:
        context.prec = 70
        checked = Decimal(foreign_principal) * Decimal(days) * Decimal(apr) * fx / Decimal(360_000_000_000)
        assert _round(exact) == _decimal_round(checked)
    evidence = [
        ("signed-window", f"Approved static-principal facility close. Observation starts on {start}, included, and "
         f"ends on {end}, excluded. Principal throughout the certified window is {currency} "
         f"{_money(foreign_principal)}. No signed movement appears in this window. Report its financing charge alone."),
        ("interest-mandate", "Closed facility note. Noncompounding simple interest is principal in the facility "
         "currency times the fixed annual rate times actual days / 360. Convert the total interest once at the signed "
         "remittance fixing. Round that USD charge once to cents, half up. The principal is not part of the charge."),
        ("signed-pricing", f"Approved pricing confirmation. Nominal annual rate is {apr} basis points, where "
         f"100 basis points is 1%. The remittance rate is {Decimal(fx).scaleb(-5):.5f} USD per {currency}. "
         "Do not use treasury's separate average-month translation."),
        ("indicative-letter", f"Forecast on an unapproved renewal. A new {currency} facility would use actual days / "
         "365 at a higher fixing. It was neither accepted nor used to settle the certified window."),
        ("bank-instruction", "Banking instruction for a different facility. It forwards future monthly currency "
         "principal movements for deposit processing. This facility's pricing and charge are unaffected."),
    ]
    return "financing charge for the certified window", evidence, (0, 1, 2), _round(exact)


def _moderate_fx(rng: Random, variant: int) -> tuple[str, list[tuple[str, str]], tuple[int, ...], int]:
    interval_days = (30, 45, 30)
    posted = [rng.randrange(2_307_170, 10_814_589) * direction for direction in (1, -1, 1)]
    prices = (107_375, 108_125, 110_855)
    opening = rng.randrange(121_453_815, 393_394_253)
    start = date(2025, 5, 4) + timedelta(days=variant * 8)
    rates = (480, 560, 450)
    effective = variant % 2 == 1
    try_fee = 65
    reserve = Fraction(opening)
    for i, (days, move, price, nominal) in enumerate(zip(interval_days, posted, prices, rates)):
        after_posting = reserve + Fraction(move * price, 100_000)
        effective_rate = nominal + (try_fee if effective and i >= 1 else 0)
        reserve = after_posting * (1 + Fraction(effective_rate * days, 3_600_000))
    with localcontext() as context:
        context.prec = 75
        factors = [1 + Decimal((nominal + (try_fee if effective and i >= 1 else 0)) * days) / 3_600_000
                   for i, (nominal, days) in enumerate(zip(rates, interval_days))]
        # Reverse expansion of each cash flow's remaining interest instead of rolling balance.
        verified = Decimal(0)
        multiplier = Decimal(1)
        for i in range(2, -1, -1):
            multiplier *= factors[i]
            verified += Decimal(posted[i] * prices[i]) / 100_000 * multiplier
        verified += Decimal(opening) * multiplier
        assert _decimal_round(verified) == _round(reserve)
    boundaries = [start]
    for days in interval_days:
        boundaries.append(boundaries[-1] + timedelta(days=days))
    moves_text = _table("Opening posting date | Signed movement EUR | USD per EUR",
                        [(boundaries[i], _money(move), Decimal(prices[i]).scaleb(-5)) for i, move in enumerate(posted)])
    rates_text = _table("Interval starts inclusive | Ends exclusive | Nominal annual basis points",
                        [(boundaries[i], boundaries[i+1], rate) for i, rate in enumerate(rates)])
    law = "effective" if effective else "withdrawn before effectiveness"
    evidence = [
        ("approved-period", f"Signed multicurrency facility close. Opening USD principal {_money(opening)} immediately "
         f"before the effective movement on {start}. Closing principal is measured at the boundary {boundaries[-1]}, "
         "including the interest for the final included interval. Do not include the following cycle."),
        ("signed-mechanics", "Facility calculation contract. Translate signed EUR principal movements at their posted "
         "fixings and add them at interval opening. For each interval, add simple interest on the resulting USD principal, "
         "using annual rate times actual days divided by 360. That full accrued interest capitalizes at the interval "
         "end. Keep full precision on movements and interest. Round once at the close, to USD cents half up."),
        ("posting-register", "Signed movements and remittance fixings. Plus indicates a draw and minus indicates "
         "principal reduction. No other movement affects the approved three intervals.\n" + moves_text),
        ("authorized-rate-tape", "Signed pricing record. Each 100 basis points is 1%. Targets in the annual budget "
         "are estimates. Use these actual nominal annual rates before any effective rider.\n" + rates_text),
        ("rider-approval-register", f"Facility rider status: {law}. This rider alone adds {try_fee} basis points to "
         f"each interval whose opening date is on or after {boundaries[1]}. It never changes earlier accruing "
         "interest. Draft spread of 125 basis points was never accepted."),
    ]
    return "closing principal for the approved three-interval window", evidence, (0, 1, 2, 3, 4), _round(reserve)


def _hard_fx(rng: Random, variant: int) -> tuple[str, list[tuple[str, str]], tuple[int, ...], int]:
    count = 7 + variant
    moves = [rng.choice((-1, 1)) * rng.randrange(9_001_971, 81_423_917) for _ in range(count)]
    currency = [("EUR", "GBP", "USD")[(index + variant) % 3] for index in range(count)]
    fixing = {"EUR": (109_327, 111_197)[variant], "GBP": (126_745, 128_413)[variant], "USD": 100_000}
    rates = [rng.randrange(347, 727) for _ in range(count)]
    fs = 360 if variant == 0 else 365
    start = date(2025, 9, 3)
    opening = rng.randrange(1_723_523_961, 2_319_418_117)
    boundaries = [start]
    for _ in moves:
        boundaries.append(boundaries[-1] + timedelta(days=rng.randrange(9, 25)))
    waived = {1, count - 2}
    premium = 83
    principal = Fraction(opening)
    multiplier_base = 10_000 * fs
    for i, movement in enumerate(moves):
        principal += Fraction(movement * fixing[currency[i]], 100_000)
        rate = rates[i] + (0 if i in waived else premium)
        days = (boundaries[i+1] - boundaries[i]).days
        principal *= Fraction(multiplier_base + rate, multiplier_base) ** days
    with localcontext() as context:
        context.prec = 95
        decimal_principal = Decimal(opening)
        for i, movement in enumerate(moves):
            decimal_principal += Decimal(movement) * Decimal(fixing[currency[i]]).scaleb(-5)
            day_rate = Decimal(rates[i] + (0 if i in waived else premium)) / multiplier_base
            for _ in range((boundaries[i+1] - boundaries[i]).days):
                decimal_principal += decimal_principal * day_rate
        assert _decimal_round(decimal_principal) == _round(principal)

    postings = _table("Opening date | Currency | Signed movement",
                      [(boundaries[i], currency[i], _money(amount)) for i, amount in enumerate(moves)])
    prices = _table("Start inclusive | End exclusive | Base annual rate in basis points",
                    [(boundaries[i], boundaries[i+1], rate) for i, rate in enumerate(rates)])
    evidence = [
        ("board-close", f"Approved indexed facility close. Start at {start} before that date's posted movement, "
         f"with USD {_money(opening)} principal. Include interest up to the last interval's exclusive end, "
         f"{boundaries[-1]}. Close with principal after accrual. Nothing from the following issue is included."),
        ("index-calculation-deed", "Executed call instrument. On each listed opening apply the signed movement translated "
         "to USD, preserving full precision. Thereafter compound for the interval's actual calendar days at 1 plus "
         "the annual rate as a decimal divided by the approved day-count denominator. Treat 100 basis points as 1%. "
         "Use the rate including any pricing rider premium. Carry all principal and accrued interest at full precision "
         "until the closing balance. Round that total once to USD cents, half up."),
        ("final-movements", "Facility cash tape. Plus draws principal, minus repays principal. No unlisted event occurred.\n"
         + postings),
        ("approved-intervals", "Facility posted annual base rates. The dates determine which movements and rates go "
         "together. Use the approved rider where applicable.\n" + prices),
        ("pricing-rider", f"Approved index rider. Use actual days / {fs} and a fixed translation of "
         f"{Decimal(fixing['EUR']).scaleb(-5)} USD per EUR, {Decimal(fixing['GBP']).scaleb(-5)} USD per GBP, "
         f"and 1 USD per USD. Add a premium of {premium} basis points except for the openings on "
         f"{', '.join(str(boundaries[i]) for i in sorted(waived))}. Those intervals retain their printed base rates. "
         "An old forecasting coupon used a uniform premium and was superseded."),
    ]
    return "closing principal of the approved indexed facility", evidence, (0, 1, 2, 3, 4), _round(principal)


def _record(
    row: int,
    issuer: str,
    family: str,
    case: tuple[str, list[tuple[str, str]], tuple[int, ...], int],
    rng: Random,
) -> tuple[dict, dict]:
    metric, excerpts, required, cents = case
    prefix = "blind-verdigris/" + issuer.removeprefix("Verdigris ").lower().replace(" ", "-")
    order = rng.sample(range(len(excerpts)), len(excerpts))
    refs = dict(zip(order, REFS))
    evidence = [{"ref": refs[index], "document_id": f"{prefix}/{excerpts[index][0]}",
                 "text": f"{issuer} — {excerpts[index][1]}"}
                for index in order]
    question = {"row": row, "issuer": issuer, "question": f"{issuer}. What is the {metric} in US dollars?",
                "evidence": evidence}
    label = {"row": row, "family": family, "verdict": "answer", "unit": "usd",
             "answer_value": _money(cents).replace(",", ""),
             "evidence_ids": sorted(refs[index] for index in required)}
    answer = json.dumps({"verdict": label["verdict"], "unit": label["unit"],
                         "answer_value": label["answer_value"], "citations": label["evidence_ids"]})
    hits = [{"evidence_id": ref} for ref in REFS]
    assert score_answer(label, answer, hits, top_k=5).passed
    assert all(not score_answer(label, answer, [hit for hit in hits if hit["evidence_id"] != ref], top_k=5).passed
               for ref in label["evidence_ids"])
    return question, label


def build() -> tuple[list[dict], list[dict]]:
    rng = Random(628_831_703)
    fixtures = []
    for issuers, family, builders in (
        (ASSET_NAMES, ASSET_FAMILY, (_simple_asset, _moderate_asset, _hard_asset)),
        (FINANCE_NAMES, FX_FAMILY, (_simple_fx, _moderate_fx, _hard_fx)),
    ):
        for index, issuer in enumerate(issuers):
            tier = min(index // 4, 2)
            fixture = builders[tier](rng, index % 4)
            fixtures.append(_record(len(fixtures)+1, issuer, family, fixture, rng))
    public, private = (list(values) for values in zip(*fixtures))
    assert len({row["issuer"] for row in public}) == 20
    assert len({hit["document_id"] for row in public for hit in row["evidence"]}) == 100
    return public, private
