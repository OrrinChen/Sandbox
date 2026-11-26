"""Paired development cases on observed associations and causal identification."""

from __future__ import annotations

from typing import Optional


def _case(question: str, evidence: list[str], choice: str, value: Optional[str], refs: str) -> dict:
    return {
        "question": question,
        "evidence": evidence.copy(),
        "gold": {"choice": choice, "value": value, "citations": [list(refs)]},
    }


def _pair(pair_id: str, dimension: str, kind: str, left: dict, right: dict) -> dict:
    return {"id": pair_id, "dimension": dimension, "kind": kind, "members": [left, right]}


def _direction(metric: str) -> str:
    return (
        f"{metric} Give the signed difference as value. Use choice positive, negative or zero "
        "for its sign. Cite only the records needed to calculate this comparison."
    )


def _causal(target: str) -> str:
    return (
        f"{target} Use choice identified if the stated design supports a point estimate of that "
        "causal effect and give the signed estimate as value. Cite the records establishing the "
        "design and supplying the estimate. Otherwise use choice unidentified, value null, and cite "
        "only the record(s) establishing the specific obstacle. Use the stated assumptions; ordinary "
        "sampling uncertainty by itself does not preclude estimation."
    )


def _association_pairs() -> list[dict]:
    evidence = [
        "Marsh Bell Credit | new accounts | renewed / eligible: assisted 18/20, standard 63/75.",
        "Customer care recorded an agent training day in March.",
        "A separate calendar-year report counts every renewal request, including repeats.",
        "Marsh Bell Credit | established accounts | renewed / eligible: assisted 48/80, standard 14/25. "
        "New and established are the two disjoint groups in the quarterly register.",
        "The following quarter, a service fee changed across both products.",
    ]
    crude = _case(_direction("For this quarter, pool account counts and compare renewal rates, assisted "
                              "minus standard, in percentage points."), evidence, "negative", "-11", "AD")
    equal = _case(_direction("For this quarter, give each account-age group half the weight in both "
                              "products. Compare renewal rates, assisted minus standard, in percentage "
                              "points."), evidence, "positive", "5", "AD")
    mix = _pair("marsh-bell-renewals", "association", "question", crude, equal)

    evidence = [
        "Gull Strand weekly ledger | sales receipts in thousand USD: W1 80; W2 100; W3 60; W4 90; W5 50.",
        "Gull Strand mailing file | circular was sent in W1 and W3, and withheld in W2 and W4.",
        "A W5 circular was prepared, but the postage ledger for that week was lost.",
        "Trade directory | Gull Strand's accounting year has 52 weeks.",
        "The mailing contractor charges by the envelope regardless of orders.",
    ]
    weeks = "Across mailing decisions W1 through W4, compare mean receipts for sent minus withheld, "
    current = _case(_direction(weeks + "using receipts in the mailing-decision week, in thousand USD."),
                    evidence, "negative", "-25", "AB")
    following = _case(_direction(weeks + "using receipts in the week after each decision, in thousand USD."),
                      evidence, "positive", "40", "AB")
    lag = _pair("gull-strand-mailings", "association", "question", current, following)

    evidence = [
        "Regional sales described a national campaign planned for the next quarter.",
        "Mica Draw | port branches: reconciled automatically 72% of priority claims and 60% of regular claims.",
        "Published benchmark population | port branches carry 75% of the portfolio weight; the balance is inland.",
        "The two claim channels each pay the same monthly license fees.",
        "Mica Draw | inland branches: reconciled automatically 40% of priority claims and 48% of regular claims.",
    ]
    question = _direction("Using the published benchmark population for both channels, what is the weighted "
                          "observed automatic-reconciliation rate for priority minus regular claims, in percentage points?")
    port = _case(question, evidence, "positive", "7", "BCE")
    evidence[2] = evidence[2].replace("75%", "25%")
    inland = _case(question, evidence, "negative", "-3", "BCE")
    weighting = _pair("mica-draw-population", "association", "fact", port, inland)

    evidence = [
        "The matched desks write the same type of paper; matched desk IDs are stable over the review.",
        "Quince Market | closing proceeds in thousand USD for desk P, each paired deal: K 94, L 75, M 118, N 115.",
        "Unpaired short-dated deals | desk P 400, desk Q 390, both in thousand USD.",
        "Quince Market | closing proceeds in thousand USD for desk Q, each paired deal: N 90, L 80, K 100, M 120.",
        "A desk fee was announced for the following year and had no effect on the closing-proceeds series.",
    ]
    target = ("For the four deals recorded by both desks, form each deal's desk-P minus desk-Q difference "
              "using deal ID. Report the ")
    mean = _case(_direction(target + "arithmetic mean of these differences in thousand USD."),
                 evidence, "positive", "3", "BD")
    median = _case(_direction(target + "median of these differences in thousand USD, averaging the middle "
                              "two observations for an even sample."), evidence, "negative", "-3.5", "BD")
    paired = _pair("quince-market-desks", "association", "question", mean, median)
    return [mix, lag, weighting, paired]


def _causal_pairs() -> list[dict]:
    evidence = [
        "Beryl Patch | branch IT bill: the median installation fee was USD 410.",
        "The offices were allocated to early activation or usual service by a fair coin independent of "
        "their potential collections.",
        "A different pilot in the neighboring market ended a month earlier.",
        "Close of quarter | average collections per office, thousand USD: early activation 112, usual service 96.",
        "The next operations release will change the activation workflow.",
    ]
    question = _causal("Estimate the average effect of early activation versus usual service on quarterly "
                       "collections, in thousand USD per office (early minus usual). Take complete outcome "
                       "capture, full adherence, and no interference as given. No baseline adjustment records "
                       "or alternate identification designs are available.")
    lottery = _case(question, evidence, "identified", "16", "BD")
    evidence[1] = ("The offices were allocated to early activation or usual service by managers using an "
                   "unrecorded growth forecast that also predicts collections under either service.")
    forecast = _case(question, evidence, "unidentified", None, "B")
    allocation = _pair("beryl-patch-allocation", "causality", "fact", lottery, forecast)

    evidence = [
        "Canal Larch invoice register | reminder versus no reminder was assigned by an independent fair coin, "
        "and every invoice received its assigned service.",
        "The pilot enrolled accounts from the prior fiscal year.",
        "Outcome archive | average days to payment among retained invoices: reminder 9, no reminder 11.",
        "Reminders were dispatched with the existing email service.",
        "Within each arm the archive retained 80 of 100 payment records, selecting invoices by their actual "
        "days to payment with an undisclosed arm-specific rule; no selection probabilities or missing days survive.",
    ]
    question = _causal("Estimate the average effect of a reminder on days to payment across all enrolled "
                       "invoices (reminder minus no reminder). Assume no interference and no alternate "
                       "measurements, adjustments or designs.")
    selective = _case(question, evidence, "unidentified", None, "E")
    evidence[4] = ("Within each arm the archive retained 80 of 100 payment records, selecting invoices by "
                   "simple random sampling independent of days to payment; the missing days do not survive.")
    random = _case(question, evidence, "identified", "-2", "ACE")
    followup = _pair("canal-larch-archive", "causality", "fact", selective, random)

    evidence = [
        "East Alder | receipts register for every account. Mean receipts in USD by invitation group: "
        "invited 358, not invited 346. By portal use: users 375, nonusers 332.",
        "Device procurement forecast excluded the holiday season.",
        "Only a fraction of invitees used the portal. Customers chose use based on unrecorded expected "
        "receipts; the invitation also affected receipts directly through fee advice. No adjustment "
        "data, additional instruments or alternative designs exist for portal use.",
        "Randomization log | invitations assigned by a concealed independent coin toss. No customer "
        "could influence assignment, and one account's assignment did not affect another's receipts.",
        "Helpdesk tickets that mention the portal increased in number that quarter.",
    ]
    invitation = _case(_causal("What is the average causal effect of sending the invitation on receipts "
                               "in USD per account (invited minus not invited), with use left as it occurred?"),
                       evidence, "identified", "12", "AD")
    uptake = _case(_causal("What is the average causal effect of using the portal on receipts in USD per "
                           "account (use minus no use), distinct from sending an invitation?"),
                   evidence, "unidentified", None, "C")
    estimand = _pair("east-alder-invitations", "causality", "question", invitation, uptake)

    evidence = [
        "West Mallow | mature accounts, mean quarterly chargebacks in USD: bonded 9, unbonded 5. "
        "Both contracts issued in this group.",
        "The proposed national contract will use a different legal entity.",
        "Target portfolio register | one quarter of accounts are new; all other accounts are mature.",
        "Underwriting audit | within account age, bonding also depends on an unmeasured fraud alert that "
        "predicts chargebacks under either contract. No other adjustment measurements or designs are available.",
        "West Mallow | new accounts, mean quarterly chargebacks in USD: bonded 16, unbonded 28. "
        "Both contracts issued in this group.",
    ]
    question = _causal("Estimate the average causal effect of bonding on quarterly chargebacks for the target "
                       "portfolio, bonded minus unbonded in USD per account. Outcomes are complete and contracts "
                       "consistent, with no interference. The target portfolio and issuer share the same "
                       "age-specific potential outcome means.")
    alert = _case(question, evidence, "unidentified", None, "D")
    evidence[3] = ("Underwriting audit | within account age, bonding is independent of chargebacks under either "
                   "contract. No other adjustment measurements or designs are available.")
    adjusted = _case(question, evidence, "identified", "0", "ACDE")
    adjustment = _pair("west-mallow-underwriting", "causality", "fact", alert, adjusted)
    return [allocation, followup, estimand, adjustment]


def build() -> list[dict]:
    return _association_pairs() + _causal_pairs()
