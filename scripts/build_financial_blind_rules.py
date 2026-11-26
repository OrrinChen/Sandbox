"""Build held-out version, recognition, eligibility, state, and reconciliation cases."""
from __future__ import annotations

from decimal import Decimal
from itertools import combinations
import json
from random import Random

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer

ISSUERS = (
    "Quay Wind", "Gypsum Works", "Hollowstone Labs", "Leeward Grid",
    "Oldmill Ferries", "Marden Storage", "Dovewater Leasing", "Duskvale Medical",
    "Arrow Point Credit", "Clayhill Trade", "Roan Basin Export", "Silverrush Solar",
    "Cinder Falls Press", "Morrow Fen Timber", "Frost Piers Telecom", "Azurelake Water",
    "Beechline Clearing", "Rillmont Markets", "Narrow Bridge Trust", "Fieldfare Custody",
)
REFS = "ABCDE"


def usd(cents: int) -> str:
    return f"{Decimal(cents).scaleb(-2):,.2f}"


def table(columns: str, rows) -> str:
    return "\n" + columns + "\n" + "\n".join(" | ".join(map(str, row)) for row in rows)


def version(rng: Random, index: int):
    base = [rng.randrange(425_300, 890_300) for _ in range(4)]
    first = [rng.randrange(538_400, 833_900) for _ in range(4)]
    second = [rng.randrange(497_100, 772_800) for _ in range(4)]
    mode = ("active", "pending", "active", "pending")[index]
    first_fields = ((0, 2), (0, 3), (1, 3), (0, 2, 3))[index]
    second_fields = ((0, 3), (1, 3), (2, 3), (0, 1))[index]
    keys = ("license receipts", "service receipts", "early close refunds", "settled settlement credits")
    left, right = sum(base[:2]), sum(base[2:])
    signs = (1, 1, -1, -1)
    for slot in first_fields:
        if signs[slot] == 1:
            left += first[slot] - base[slot]
        else:
            right += first[slot] - base[slot]
    if mode == "active":
        for slot in second_fields:
            earlier = first[slot] if slot in first_fields else base[slot]
            if signs[slot] == 1:
                left += second[slot] - earlier
            else:
                right += second[slot] - earlier
    computed = left - right
    versions = [(base, range(4)), (first, first_fields)]
    if mode == "active":
        versions.append((second, second_fields))
    reference = sum(sign * next(grid[slot] for grid, fields in reversed(versions) if slot in fields)
                    for slot, sign in enumerate(signs))
    assert computed == reference

    always = index % 2 == 0
    fiscal_period = 2021 + index
    third = (
        "Revision C was activated for this close by the trustee's signed effective notice."
        if mode == "active" else
        "Revision C was received before sign-off but stayed pending at sign-off. Its status excludes it from the close."
    )
    authority = (
        third if always else
        "Under the executed workflow, the latest signed controller status record controls whether Revision C is active."
    )
    excerpts = [
        ("close-mandate",
         f"Executed FY{fiscal_period} close mandate. Compute the approved receipts surplus as license receipts "
         "plus service receipts less early close refunds and less settled settlement credits. Original snapshot A is "
         "in force as restated. Revision B is active and replaces only its listed fields. Apply Revision C after B "
         "only if it is active, and only to its listed fields. A number shown on a revision comparison worksheet "
         "does not create a replacement for an unlisted field. " + authority),
        ("signed-snapshot-a", "Signed snapshot A at the approved close, USD." + table(
            "Metric | USD", ((k, usd(v)) for k, v in zip(keys, base)))),
        ("restatement-b", "Executed Revision B, replacements in USD, superseding only these metrics." + table(
            "Metric | USD", ((keys[slot], usd(first[slot])) for slot in first_fields))),
        ("restatement-c", "Revision C replacement schedule, USD. This schedule has authority only if activated "
         "at sign-off." + table("Metric | USD", ((keys[slot], usd(second[slot])) for slot in second_fields))),
        ("status-or-outlook", ("Internal planning note. Next year's forecast format reports receipts before "
                                "refunds or credits. The forecast is not a close instruction."
                                if always else "Signed controller status record. " + third)),
    ]
    selected = {0, 1, 2}
    if mode == "active":
        selected.add(3)
    if not always:
        selected.add(4)
    return "operative_revision_priority", "approved receipts surplus", excerpts, selected, computed


def recognition(rng: Random, index: int):
    close = (23, 25, 26, 27)[index]
    applies_after = (11, 12, 14, 15)[index]
    opening = rng.randrange(6_270_101, 10_211_512)
    pairs = [
        ("C12", 8, 15, "agent", 15, "cleared", 18, "valid"),
        ("C17", 9, 14, "principal", 30, "pending", 25, "valid"),
        ("C21", 13, 12, "agent", 17, "cleared", 10, "valid"),
        ("C26", 15, 24, "agent", 26, "cleared", 22, "valid"),
        ("C34", 14, 19, "principal", 15, "cleared", 13, "void"),
        ("C39", 16, 21, "agent", 21, "cleared", 24, "valid"),
        ("C52", 20, 29, "principal", 22, "cleared", 16, "valid"),
        ("C67", 21, 22, "agent", 13, "pending", 18, "valid"),
    ]
    pairs = [(k, service, acceptance, role, settlement, pay_status, adjustment_day, adjustment_status,
              rng.randrange(955_100, 1_813_000), rng.randrange(138_600, 361_000),
              rng.randrange(24_050, 92_100), rng.randrange(10_030, 16_020))
             for (k, service, acceptance, role, settlement, pay_status, adjustment_day, adjustment_status) in pairs]
    total = opening
    for _, service, acceptance, role, settle, state, adjustment_day, adjusted, gross, pay, c_gross, c_pay in pairs:
        if acceptance > close:
            continue
        if adjusted == "valid" and adjustment_day <= close:
            gross, pay = gross - c_gross, pay - c_pay
        if role == "agent" and service >= applies_after and state == "cleared" and settle <= close:
            gross -= pay
        total += gross
    included = [row for row in pairs if row[2] <= close]
    netted = [row for row in included if row[3] == "agent" and row[1] >= applies_after
             and (row[5], row[4] <= close) == ("cleared", True)]
    gross_total = sum(row[8] for row in included) - sum(row[10] for row in included
                                                       if row[6] <= close and row[7] == "valid")
    pass_total = sum(row[9] for row in netted) - sum(row[11] for row in netted
                                                   if row[6] <= close and row[7] == "valid")
    assert opening + gross_total - pass_total == total

    consolidated = index == 3
    policy = (
        "A principal claim is recognized gross. An agent claim is also gross unless its service date is on "
        f"or after the {applies_after}th and its remittance is cleared no later than close. Then recognize adjusted "
        "gross less adjusted pass-through. They are both reduced only by valid corrections validated by close."
    )
    closed = [
        ("recognition-mandate", f"Settled service revenue pack. Approved carry-in is USD {usd(opening)}. "
         f"The current period is certified through business day {close}, inclusive. Add claims on their first "
         "unconditional acceptance day. No duplicate claims exist. A valid correction validated by close "
         "reduces both its linked claim's gross and linked pass-through when that claim is recognized. "
         "Validation can precede first acceptance. All listed monetary amounts are US dollars. "
         + (policy if consolidated else "The binding principal-versus-agent supplement determines gross or net.")),
        ("recognition-supplement", policy if not consolidated else
         "Draft for the next period. Its proposed policy would net every agent claim as of service date. "
         "It was not signed and does not apply to the settled pack."),
        ("claim-register-1", "Unconditional acceptance register, claims C12 through C26." + table(
            "Claim | Service day | Acceptance day | Role | Remittance day | Remittance status | Gross | Pass-through",
            ((k, sv, a, r, s, p, usd(g), usd(h)) for k, sv, a, r, s, p, _, _, g, h, _, _ in pairs[:4]))),
        ("claim-register-2", "Unconditional acceptance register, remaining claims. A pending status cannot "
         "be treated as cleared even if the planned date is before close." + table(
            "Claim | Service day | Acceptance day | Role | Remittance day | Remittance status | Gross | Pass-through",
            ((k, sv, a, r, s, p, usd(g), usd(h)) for k, sv, a, r, s, p, _, _, g, h, _, _ in pairs[4:]))),
        ("correction-control", "Signed validated corrections ledger. Void entries have no accounting effect." + table(
            "Claim | Validation day | Status | Gross reduction | Pass-through reduction",
            ((k, d, s, usd(g), usd(p)) for k, _, _, _, _, _, d, s, _, _, g, p in pairs))),
    ]
    return "gross_net_close_adjustments", "settled service revenue at the approved close", closed, (
        {0, 2, 3, 4} if consolidated else {0, 1, 2, 3, 4}), total


def eligibility(rng: Random, index: int):
    threshold = (13, 15, 14, 16)[index]
    passed_through = (26, 27, 25, 26)[index]
    event_catalog = [
        ("D61", 8, 11, 11, "legacy", "legacy"),
        ("D63", 13, 18, 22, "conversion", "legacy"),
        ("D68", 11, 19, 27, "conversion", "conversion"),
        ("D71", 17, 20, 24, "conversion", "legacy"),
        ("D79", 19, 23, 23, "legacy", "conversion"),
        ("D81", 20, 27, 30, "conversion", "conversion"),
        ("D85", 24, 24, 21, "conversion", "legacy"),
        ("D92", 18, 29, 29, "conversion", "legacy"),
    ]
    records = [(*row, rng.randrange(180_100, 496_200), rng.randrange(131_200, 351_500))
               for row in event_catalog]
    total = 0
    for _, intake, binding, approval, origin, requested, legacy_amount, conversion_amount in records:
        if binding > passed_through:
            continue
        tag = requested if approval >= binding and approval <= passed_through else origin
        if intake >= threshold and tag == "conversion":
            total += conversion_amount
        else:
            total += legacy_amount
    binding = {key for key, _, effective, *_ in records if effective <= passed_through}
    migrated = {
        key for key, intake, effective, approved, original, request, *_ in records
        if key in binding and intake >= threshold and (
            effective <= approved <= passed_through and request == "conversion"
            or (approved < effective or approved > passed_through) and original == "conversion"
        )
    }
    assert sum(row[7] if row[0] in migrated else row[6] for row in records if row[0] in binding) == total

    notices = tuple((a, date, label) for a, _, _, date, _, label, *_ in records)
    roster = table("Facility | Intake day | Binding day | Original program",
                   ((a, intake, active, orig) for a, intake, active, _, orig, *_ in records))
    prices = table("Facility | Legacy award USD | Conversion award USD",
                   ((a, usd(old), usd(new)) for a, *_, old, new in records))
    precedence = (
        "A program change in the approvals book replaces the original program only if its approval day is "
        "on or after the facility's binding day and no later than the close. An early approval never carries. "
        "Every row in the book is an approved request subject to this timing rule."
    )
    merged = index == 2
    fragments = [
        ("award-resolution",
         f"Signed supplemental access awards resolution. Close is business day {passed_through} inclusive. Only facilities "
         f"binding by close participate. Give the conversion award only if the operative program is conversion and the "
         f"facility was taken into intake on or after business day {threshold}. All other included facilities receive the "
         "legacy award. Use awards as posted in USD. Days are ordered within the same award period. "
         + (precedence if merged else "The approvals appendix has the applicable authority rule.")),
        ("intake-register", "Certified intake and facility formation records." + roster),
        ("price-schedule", "Executed award amounts. Use exactly the applicable column for each included facility." + prices),
        ("approval-notices", "Final approvals book." + table("Facility | Approval day | Requested program", notices)),
        ("approval-appendix", "Signed approvals appendix. " + precedence if not merged else
         "Planning proposal for the next fiscal year. Suggested excluding all legacy facilities. "
         "No change to the current period was adopted."),
    ]
    return "recognized_eligibility_dates", "approved closed-period access awards", fragments, (
        {0, 1, 2, 3} if merged else {0, 1, 2, 3, 4}), total


def state(rng: Random, index: int):
    cap = rng.randrange(92_100, 123_700)
    opening = {"Red": rng.randrange(32_000, 60_800), "Blue": rng.randrange(37_300, 65_900)}
    locked = {"Red": False, "Blue": False}
    events = [
        ("Red", "release", 43_900, "effective"), ("Blue", "release", 44_200, "effective"),
        ("Red", "hold", 0, "effective"), ("Red", "release", 60_300, "effective"),
        ("Blue", "return", 13_900, "effective"), ("Blue", "release", 46_700, "effective"),
        ("Red", "resume", 0, "pending"), ("Blue", "return", 6_600, "pending"),
        ("Red", "resume", 0, "effective"), ("Red", "release", 49_100, "effective"),
        ("Blue", "hold", 0, "effective"), ("Red", "return", 17_600, "effective"),
        ("Blue", "resume", 0, "effective"), ("Blue", "release", 66_200, "effective"),
        ("Red", "release", 73_100, "effective"),
    ]
    cut = (9, 10, 12, 14)[index]
    remaining = cap
    reserve = opening.copy()
    for office, operation, amount, disposition in events[:cut]:
        if disposition == "pending":
            continue
        if operation in ("hold", "resume"):
            locked[office] = operation == "hold"
        elif operation == "return":
            assert amount <= opening[office] - reserve[office]
            reserve[office] += amount
            remaining += amount
        elif not locked[office]:
            take = min(amount, remaining, reserve[office])
            reserve[office] -= take
            remaining -= take
    net = cap - remaining
    spent = {"Red": 0, "Blue": 0}
    status = set()
    for office, operation, amount, disposition in events[:cut]:
        if disposition != "effective":
            continue
        if operation == "hold":
            status.add(office)
        if operation == "resume":
            status.remove(office)
        if operation == "return":
            spent[office] -= amount
        if operation == "release" and office not in status:
            spent[office] += min(amount, opening[office] - spent[office], cap - sum(spent.values()))
    assert sum(spent.values()) == net and net > 0
    consolidated = index % 2 == 0
    transitions = (
        "Apply effective events in sequence. Ignore all pending events. Start with both offices open. A hold "
        "blocks future releases but keeps prior transactions. A resume unblocks future releases without retrying "
        "blocked releases. Each requested release actually disburses the least of requested amount, remaining shared "
        "authorization, and the named office's available cash; it reduces both available balances. A return reverses "
        "an earlier disbursement by the stated amount, replenishing cash and shared authorization even under a hold."
    )
    docs = [
        ("shared-limit", f"Signed regional cash close. Beginning shared release authorization is USD {usd(cap)}. "
         f"Process signed event numbers 1 through {cut} inclusive. Closed net disbursed amount is total actual "
         "release disbursements less effective returns. Do not reopen completed approvals. "
         + (transitions if consolidated else "Use the signed event treatment policy for releases and returns.")),
        ("office-opening", "Signed office opening balances. These amounts are fully available before event 1."
         + table("Office | Available cash USD", ((key, usd(value)) for key, value in opening.items()))),
        ("event-treatment", "Signed event treatment policy. " + transitions if not consolidated else
         "Non-binding archive of old event treatment. Returns replenished branch liquidity only. "
         "Superseded before this file opened."),
        ("event-register", "Certified event ledger, all monetary amounts US dollars." + table(
            "Event | Office | Type | Requested or returned USD | Status",
            ((no, off, op, usd(v), quality) for no, (off, op, v, quality) in enumerate(events, 1)))),
        ("next-close-draft", "Following close preparation. Future proposed office authorization would carry "
         "unused capacity into the following period. The proposal has no effect on the current close."),
    ]
    return "release_and_return_state", "net cash disbursed at the approved close", docs, (
        {0, 1, 3} if consolidated else {0, 1, 2, 3}), net


def reconcile(rng: Random, index: int):
    count = (10, 14, 17, 19)[index]
    selected_count = (2, 3, 4, 5)[index]
    # Predetermine a witness independent of reader output. Search verifies its unique exact match.
    while True:
        items = [(rng.randrange(11540, 170920), rng.randrange(330, 7930)) for _ in range(count)]
        witness = tuple(sorted(rng.sample(range(count), selected_count)))
        posted = sum(items[i][0] for i in witness)
        matches = [choice for choice in combinations(range(count), selected_count)
                   if sum(items[i][0] for i in choice) == posted]
        if matches == [witness]:
            break
    queue = {(0, 0): [()]}
    for item, (debit, _) in enumerate(items):
        added = {}
        for (value, n), paths in queue.items():
            if n < selected_count and value + debit <= posted:
                added.setdefault((value + debit, n + 1), []).extend(path + (item,) for path in paths)
        for key, paths in added.items():
            queue.setdefault(key, []).extend(paths)
    assert queue[(posted, selected_count)] == matches
    matched = sum(items[i][1] for i in matches[0])
    complement = sum(rebate for _, rebate in items) - sum(
        rebate for i, (_, rebate) in enumerate(items) if i not in witness
    )
    assert matched == complement
    split = (count + 1) // 2
    def render(start: int, stop: int):
        return table("Item | Settled debit USD | Contractual refund USD", (
            (f"RX{i+1:02}", usd(items[i][0]), usd(items[i][1])) for i in range(start, stop)))
    merged = index == 0
    statement = (
        f"The archive aggregate settled debit is USD {usd(posted)} for {selected_count} distinct records. "
        "Sum contractual refunds from the exact matched records, with no rounding, conversion or netting."
    )
    criteria = (
        "The current archive report excludes all outside-batch charges. Find exactly that number of "
        "distinct ledger records whose full settled debit totals the bank's settled debit to the cent. "
        "The ledger identifies all candidates. Never match on contractual refund or gross billed amounts. "
        "No split or duplicate selections are permitted. Check the stated count and exact amount, then add refunds."
    )
    excerpts = [
        ("bank-certified-close", "Bank-certified Archive A6 settled capture. " + statement + (" " + criteria if merged else
         "The signed reconciliation instruction identifies how to match records.")),
        ("refund-ledger-1", "Archive A6 settled ledger page 1 of 2. This page and the closing "
         "page are the full candidate list." + render(0, split)),
        ("refund-ledger-2", "Archive A6 settled ledger page 2 of 2. Figures are already post-fee. "
         "Each refund is separately deposited and does not change the line's settled debit." + render(split, count)),
        ("reconciliation-control", (
            "Signed reconciliation instruction. " + criteria if not merged else
            "Draft for Archive A7. A different future report would match transaction references directly. "
            "A7 has no effect on A6."
        )),
        ("withdrawn-aggregate", "Prior unposted comparison, drawn from an unsettled extract. Its "
         "aggregate included gross billings and is not an approved debit or refund total."),
    ]
    return "exact_batch_reconciliation", "aggregate contractual refund from the closed archive", excerpts, (
        {0, 1, 2} if merged else {0, 1, 2, 3}), matched


def build() -> tuple[list[dict], list[dict]]:
    """Return public documents and scoring-only labels as separate records."""
    rng = Random(4581930)
    builders = (version, recognition, eligibility, state, reconcile)
    public = []
    private = []
    for group, builder in enumerate(builders):
        for index in range(4):
            row = 4 * group + index + 1
            issuer = f"Iron Petrel {ISSUERS[row-1]}"
            token = ISSUERS[row-1].lower().replace(" ", "-")
            family, metric, sources, required, amount = builder(rng, index)
            story = f"{issuer}. What is the {metric} in US dollars?"
            order = rng.sample(range(5), 5)
            refs = dict(zip(order, REFS))
            evidence = [{
                "ref": refs[source],
                "document_id": f"blind-ironpetrel/{token}/{sources[source][0]}",
                "text": f"{issuer} — {sources[source][1]}",
            } for source in order]
            label = {
                "row": row,
                "family": family,
                "verdict": "answer",
                "answer_value": usd(amount).replace(",", ""),
                "unit": "usd",
                "evidence_ids": sorted(refs[source] for source in required),
            }
            answer = {k: label[k] for k in ("verdict", "answer_value", "unit")} | {
                "citations": label["evidence_ids"]
            }
            hits = [{"evidence_id": excerpt["ref"]} for excerpt in evidence]
            assert score_answer(label, json.dumps(answer), hits, 5).passed
            assert all(not score_answer(label, json.dumps(answer),
                                       [hit for hit in hits if hit["evidence_id"] != ref], 5).passed
                       for ref in label["evidence_ids"])
            public.append({"row": row, "issuer": issuer, "question": story, "evidence": evidence})
            private.append(label)
    return public, private
