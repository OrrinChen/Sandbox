"""Scoring-side fixtures for evidence selection and decision materiality."""
from __future__ import annotations

from fractions import Fraction
from typing import Optional


def member(question: str, evidence: list[str], refs: list[str], *,
           choice: Optional[str] = None, value: Optional[int] = None) -> dict:
    return {
        "question": question,
        "evidence": evidence,
        "gold": {
            "choice": choice, "value": None if value is None else str(value),
            "citations": [list(group) for group in refs],
        },
    }


def pair(case: str, dimension: str, kind: str, first: dict, second: dict) -> dict:
    return {"id": case, "dimension": dimension, "kind": kind, "members": [first, second]}


def source_set(question: str, evidence: list[str], *refs: str) -> dict:
    return member(
        question + " Give one set of excerpts sufficient to establish the answer, with "
        "no redundant excerpt. Return null for both choice and value.",
        evidence, list(refs),
    )


def relevance() -> list[dict]:
    depot = [
        "Bark Quay field draft. The western depot anticipated 34 cash-on-delivery parcels on Monday.",
        "Western depot final dispatch register. Monday dispatch comprised 38 prepaid parcels and 31 cash-on-delivery parcels.",
        "Carrier receipt, Tuesday. The Monday dispatch arrived with 64 prepaid parcels and 49 cash-on-delivery parcels.",
        "Bark Quay signed consolidated dispatch control. Monday dispatch from the two depots totaled 115 parcels. The control has no breakdown by payment or depot.",
        "Eastern depot final dispatch register. Monday dispatch comprised 27 prepaid parcels and 19 cash-on-delivery parcels. East and west are the two dispatching depots.",
    ]
    clearing = [
        "Settlement mapping. Class V closes on the last bank day before shipment. Class M closes on the first bank day after shipment. The fixing at the applicable close is final.",
        "Ship register, consignment 314. The last bank day before shipment was June 3; the first bank day after shipment was June 6.",
        "Published June 3 fixing: 1.085 local dollars per token.",
        "Published June 6 fixing: 1.077 local dollars per token.",
        "Executed tranche register. The class on consignment 314 is V.",
    ]
    settling_m = clearing[:-1] + ["Executed tranche register. The class on consignment 314 is M."]
    settle_q = "Which source material establishes the contractual fixing on consignment 314?"
    furnace = [
        "June serial-number certification. Fifteen defective shells were found among the flagged shells sent for inspection.",
        "April engineering trial. Only shells above 900 degrees were flagged during the trial.",
        "June final inspection log. A total of 60 flagged shells were inspected. No unflagged shells were inspected.",
        "June line controller. Across all runs exactly 80 shells were flagged.",
        "June production register. Across all runs the line produced 800 shells.",
    ]
    release = [
        "Cash appendix 4, authorized value for claim RN5: USD 62,140.",
        "Restricted packet index for RN5. Release key oak selects signed cash appendix 4. Key elm selects signed appendix 7. A release key selects exactly one appendix.",
        "Controller memo from a different claim, RX5. Its trustee certified key elm.",
        "RN5 trustee certificate. The release key for the settlement is elm.",
        "Cash appendix 7, authorized value for claim RN5: USD 61,920.",
    ]
    oak = release.copy()
    oak[3] = "RN5 trustee certificate. The release key for the settlement is oak."
    release_q = "Which excerpts establish the cash amount authorized for claim RN5 under its release key?"
    return [
        pair("depot_dispatch", "relevance", "question",
             source_set("Which excerpts establish the total number of parcels dispatched Monday by the two Bark Quay depots together?", depot, "D", "BE"),
             source_set("Which excerpts establish the cash-on-delivery parcel count dispatched Monday by the western Bark Quay depot?", depot, "B")),
        pair("token_fixing", "relevance", "fact", source_set(settle_q, clearing, "ABCE"),
             source_set(settle_q, settling_m, "ABDE")),
        pair("kiln_screening", "relevance", "question",
             source_set("Which excerpts establish what fraction of all shells produced in June were flagged?", furnace, "DE"),
             source_set("Which excerpts establish what fraction of inspected flagged shells were confirmed defective in June?", furnace, "AC")),
        pair("trustee_release", "relevance", "fact", source_set(release_q, release, "BDE"),
             source_set(release_q, oak, "ABD")),
    ]


def importance() -> list[dict]:
    rollout = [
        "Fimble Rail May renewal. The gross incremental proceeds before launch charges are USD 102 thousand.",
        "Signed offer. Of the launch charges, processing is USD 4 thousand and setup is USD 8 thousand. The prior year's USD 50 thousand rent was paid before renewal and is sunk.",
        "Renewal rule. Approve at net incremental proceeds of at least USD 96 thousand. Deduct processing and any setup charge the signed rebate register leaves for the operator. Exclude sunk rent.",
        "Signed rebate register for May. The sponsor reimburses 0 percent of setup.",
        "Pipeline report: renewal visibility could attract USD 500 thousand in future orders.",
    ]
    rebated = rollout.copy()
    rebated[3] = "Signed rebate register for May. The sponsor reimburses 100 percent of setup."
    rollout_q = (
        "Test processing, setup and rent separately. Which single charge, if omitted in error, "
        "would change a rejection into approval? Set choice to processing, setup, rent or none. "
        "For value give actual net incremental proceeds minus the approval threshold, in signed "
        "USD thousands, including all applicable charges. Cite one irreducible basis for both."
    )
    options = [
        "Annual insurance renewal. All three repair sites carry the same premium and the premium is fixed for the next year.",
        "Flood model. The year's two possible states are a surge (one chance in five) and ordinary water (four chances in five).",
        "Quote sheet, USD thousands. The wall costs 8, the gate costs 12, and the drain costs 10.",
        "Damage study, USD thousands avoided before price, in the order surge / ordinary. Wall 120 / 12; gate 65 / 42; drain 260 / 30.",
        "An obsolete concept drawing priced a floating barrier at 140. The supplier withdrew that option before the board met.",
    ]
    option_q = (
        "For each repair use avoided damage less its price. Return choice wall, gate or drain and the winning net benefit in USD thousands as value. "
        "Use a set of citations with no redundant excerpt."
    )
    # The same payoffs support different rational choices under two stated objectives.
    avoided = [(120, 12, 8), (65, 42, 12), (260, 30, 10)]
    mean = [Fraction(high + 4 * low, 5) - price for high, low, price in avoided]
    worst = [min(high, low) - price for high, low, price in avoided]

    bid = [
        "Alpine sorting tender. A signed contract yields the following net incremental payoff in USD thousands. Mild season, firm fuel 140; mild season, soft fuel 60; harsh season, firm fuel 20; harsh season, soft fuel -100.",
        "Tender terms. One may buy exactly one free perfect signal before deciding to sign or walk away. Choose to maximize expected payoff; walking away pays zero. The two candidate signals reveal season or fuel separately.",
        "Fuel bulletin. Firm and soft fuel are equally likely. The fuel state is statistically independent of season.",
        "Risk circular. Probability of a mild season is 50 percent. The only other season is harsh.",
        "Purchasing memo. The largest annual fuel contract elsewhere in the group totals USD 19 million.",
    ]
    rare = bid.copy()
    rare[3] = "Risk circular. Probability of a mild season is 10 percent. The only other season is harsh."
    bid_q = (
        "Which single signal is more valuable to this tender decision? Set choice to season or fuel. "
        "Set value to the expected payoff gain over deciding with no signal, in USD thousands. "
        "Cite one irreducible basis for the result."
    )

    def signal(prob: Fraction) -> tuple[str, int]:
        bid_without_signal = max(0, prob * 100 + (1 - prob) * -40)
        season = prob * 100
        fuel = sum(max(Fraction(0), prob * good + (1 - prob) * bad) / 2
                   for good, bad in [(140, 20), (60, -100)])
        gross, which = max((season, "season"), (fuel, "fuel"))
        gain = gross - bid_without_signal
        assert gain.denominator == 1
        return which, int(gain)

    covenants = [
        "Closing certificate, before the three transactions. Cash was USD 100 thousand and covenant earnings were USD 40 thousand.",
        "Earnings covenant. Require closing covenant earnings of at least USD 30 thousand.",
        "Cash covenant. Require closing cash of at least USD 30 thousand.",
        "Signed postings for the three transactions, effects in USD thousands (cash, covenant earnings). Deposit (-85, 0), provision (0, -13), service (-4, -4). No other adjustments apply.",
        "Risk manager's quarterly exposure estimate for the site was USD 510 thousand.",
    ]
    omit_q = (
        " Which single posting would make this failed covenant appear to pass if omitted? "
        "Return choice deposit, provision or service. Return value equal to the resulting "
        "balance above the covenant minimum after omitting that posting, in USD thousands. "
        "Cite a sufficient set without redundant excerpts."
    )
    first_signal = signal(Fraction(1, 2))
    second_signal = signal(Fraction(1, 10))
    assert first_signal == ("season", 20) and second_signal == ("fuel", 16)
    assert max(mean) == mean[2] == 66 and max(worst) == worst[1] == 30
    return [
        pair("renewal_margin", "importance", "fact",
             member(rollout_q, rollout, ["ABCD"], choice="setup", value=102 - 4 - 8 - 96),
             member(rollout_q, rebated, ["ABCD"], choice="none", value=102 - 4 - 96)),
        pair("flood_protection", "importance", "question",
             member("Which repair maximizes expected net benefit over the entire year? " + option_q,
                    options, ["BCD"], choice="drain", value=int(mean[2])),
             member("Which repair maximizes its minimum net benefit across the surge and ordinary states? " + option_q,
                    options, ["CD"], choice="gate", value=worst[1])),
        pair("sorting_tender", "importance", "fact",
             member(bid_q, bid, ["ABCD"], choice=first_signal[0], value=first_signal[1]),
             member(bid_q, rare, ["ABCD"], choice=second_signal[0], value=second_signal[1])),
        pair("covenant_postings", "importance", "question",
             member("Assess the cash covenant." + omit_q, covenants, ["ACD"], choice="deposit", value=100 - 4 - 30),
             member("Assess the earnings covenant." + omit_q, covenants, ["ABD"], choice="provision", value=40 - 4 - 30)),
    ]


def build() -> list[dict]:
    return relevance() + importance()
