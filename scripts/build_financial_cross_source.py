"""Freeze independent synthetic cross-source development and blind corpora."""

from __future__ import annotations

import argparse
from decimal import Decimal
from hashlib import sha256
import json
from random import Random

from build_financial_benchmark import (
    DATA, MODALITIES, OUTPUT_NAMES, SOURCE_NAMES, SOURCE_SCALE,
    decimal_text, encoded, matches, reference, write_frozen,
)


METRICS = {
    "dev": (
        (("credit_facility_fees", "fees for revolving credit", "revolving credit facility fees"),
         ("software_capitalization", "capitalised software work", "capitalized software development costs")),
        (("facility_rental_income", "income from renting facilities", "facility rental receipts"),
         ("flood_recovery_cost", "spending to recover from floods", "flood recovery expenses")),
        (("parts_refurbishment_sales", "sales of reconditioned parts", "refurbished parts revenue"),
         ("inventory_obsolescence", "write-downs on outdated stock", "obsolete inventory write-downs")),
        (("grid_connection_receipts", "payments for hooking up to the grid", "grid connection proceeds"),
         ("meter_installation_cost", "cost of fitting new meters", "meter installation expenses")),
        (("maintenance_contract_collections", "cash collected on upkeep agreements", "maintenance contract collections"),
         ("field_service_outlays", "spending on field service", "field service cash payments")),
        (("deposit_interest_income", "interest earned on deposits", "deposit interest revenue"),
         ("reseller_incentives", "incentive payments to resellers", "reseller incentive costs")),
    ),
    "test": (
        (("network_usage_fees", "charges for network use", "network usage fee receipts"),
         ("fiber_replacement_cost", "spending to replace fibre", "fiber replacement expenses")),
        (("customs_duty_rebates", "rebates on import duties", "customs duty recoveries"),
         ("freight_demurrage", "charges for holding freight", "freight demurrage costs")),
        (("marketplace_commissions", "commission earned through the marketplace", "marketplace commission receipts"),
         ("merchant_onboarding_costs", "costs of bringing merchants aboard", "merchant onboarding expenses")),
        (("terminal_handling_receipts", "cash from handling at terminals", "terminal handling revenues"),
         ("terminal_security_outlays", "payments for terminal security", "terminal security expenditure")),
        (("carbon_credit_receipts", "collections from carbon credits", "carbon credit sale proceeds"),
         ("verification_contract_fees", "fees for contracted verification", "verification contract expenses")),
        (("warranty_reimbursements", "payments recovered under warranties", "warranty reimbursement receipts"),
         ("repair_center_cost", "spending at repair centres", "repair center operating expenses")),
        (("capacity_booking_receipts", "payments for booking capacity", "capacity reservation proceeds"),
         ("connection_credit_payouts", "payouts on connection credits", "connection credit payments")),
        (("equipment_salvage_revenue", "sales of equipment recovered for salvage", "equipment salvage receipts"),
         ("retirement_site_costs", "spending at sites being retired", "asset retirement site costs")),
    ),
}

PROMPTS = {
    "dev": (
        "For {name} ({period}), start with {left} from the earnings Q&A, then subtract {right} from the investor slides. Report in {unit}.",
        "{name}, {period}: how much higher is {left} in the analyst call than {right} in the slide deck? Give a signed result in {unit}.",
        "Use the {period} disclosures for {name}: take {right} in the investor presentation away from {left} in the earnings call. Show the result in {unit}.",
        "For {name} and {period}, give {left} from the results call less {right} in the investor deck, in {unit}.",
        "From {right} in the slide pack, subtract {left} in the call transcript. Use {name}'s {period} figures in {unit}.",
        "For the {period} {name} workbook in {unit}, what is {right} from the slide deck minus {left} from the earnings transcript?",
    ),
    "test": (
        "For {name}'s {period} review, put the earnings transcript figure for {left} first and deduct the slide deck figure for {right}. Return the signed amount in {unit}.",
        "{name} ({period}) is the only issuer in scope. Take the investor deck's {right} away from the results call's {left}. Express it in {unit}.",
        "In {unit}, what remains for {name} at {period} after subtracting the investor slides' {right} from the analyst call's {left}?",
        "For {name} in {period}, start from the presentation amount for {right}; then remove the call transcript amount for {left}. Report the difference in {unit}.",
        "Use the {period} {name} packet. By how much does {right} in the slide pack exceed {left} in the earnings call? Keep the sign and use {unit}.",
        "I need {name}'s {period} bridge in {unit}: {right} as shown in the investor presentation minus {left} as discussed in the earnings Q&A.",
    ),
}

ROOTS = {
    "dev": ("Fenwick", "Loam", "Hearth", "Osier", "Kite"),
    "test": ("Aster", "Brindle", "Cobalt", "Dunlin", "Flint", "Gorse", "Hawthorn", "Ilex", "Larch", "Marten"),
}
REGIONS = ("March", "Sound", "Bluff", "Cove")
SOURCES = tuple(SOURCE_NAMES)
UNITS = tuple(OUTPUT_NAMES)
RAW_UNITS = {"USD": "USD", "thousands": "USD thousands", "millions": "USD millions"}
PASSAGES = (
    "{company}, {period}, {source}. {fact}. See the full packet for related comparative amounts.",
    "{source} | {company} | {period}\n{fact}. Amounts in the appendix use their stated units.",
    "{period} disclosure of {company}, extract from {source}: {fact}.",
    "The {source} for {company} covered the {period} close. {fact}. Other schedules may use a different basis.",
    "Source: {source}, {company} ({period}). Consolidated reporting figures follow. {fact}.",
    "Reporting entity {company}\nFiscal period {period}\nDocument {source}\n{fact}.",
)


def groups(split):
    code = "XD" if split == "dev" else "XT"
    for index, (root, region) in enumerate((a, b) for a in ROOTS[split] for b in REGIONS):
        group = f"{code}{index + 1:02d}"
        companies = [(group + suffix, f"{root} {region} {name}")
                     for suffix, name in (("A", "Enterprise"), ("B", "Partners"))]
        yield index, group, companies, 2021 + (index * 3) % 6, METRICS[split][index % len(METRICS[split])]


def corpus(split):
    rng = Random(831662 if split == "dev" else 561974)
    documents = []
    for _, _, companies, year, metrics in groups(split):
        for ticker, company in companies:
            def add(code, phrase, source, fiscal_year, unit=None):
                unit = unit or rng.choice(tuple(RAW_UNITS))
                amount = Decimal(rng.randrange(90, 23000)) / 8 * 1_000_000
                value = decimal_text(amount / SOURCE_SCALE[unit])
                period = f"FY{fiscal_year}"
                doc_id = f"packet-{ticker}-{period}-{source}"
                fact = f"{phrase.capitalize()}: {value} {RAW_UNITS[unit]}"
                body = rng.choice(PASSAGES).format(company=company, period=period, source=SOURCE_NAMES[source], fact=fact)
                evidence_id = "line-" + sha256(f"{doc_id}\n{body}".encode()).hexdigest()[:20]
                documents.append({
                    "evidence_id": evidence_id, "document_id": doc_id, "source_group": ticker,
                    "company_ticker": ticker, "company_name": company, "fiscal_period": period,
                    "source_type": source, "modality": MODALITIES[source], "metric": code,
                    "numeric_value": value, "unit": unit, "currency": "USD", "text": body,
                })

            for (code, alias, document_phrase), source, unit in zip(
                metrics, ("transcript", "investor_deck"), ("millions", "thousands"),
            ):
                add(code, document_phrase, source, year, unit)
                for delta in (-1, 1):
                    add(code, rng.choice((document_phrase, alias)), source, year + delta)
                for other_source in SOURCES:
                    if other_source != source:
                        add(code, alias, other_source, year)
                add("adjusted_" + code, "adjusted " + alias, source, year)
                add("projected_" + code, "forecast " + alias, source, year)
                add("segment_" + code, "business unit " + alias, source, year)
                add("quarterly_" + code, "last-quarter " + alias, source, year)
    rng.shuffle(documents)
    return {"version": f"financial-cross-source-{split}-v1", "documents": documents}


def questions_and_labels(split, documents):
    questions, labels = [], []
    for index, _, companies, year, metrics in groups(split):
        for position, (ticker, company) in enumerate(companies):
            form = (index * 2 + position) % len(PROMPTS[split])
            output_unit = UNITS[(index + position) % len(UNITS)]
            period = f"FY{year}"
            text = PROMPTS[split][form].format(
                name=company, period=period, left=metrics[0][1], right=metrics[1][1],
                unit=OUTPUT_NAMES[output_unit],
            )
            operands = [
                {"ticker": ticker, "period": period, "metric": metric[0], "source_type": source}
                for metric, source in zip(metrics, ("transcript", "investor_deck"))
            ]
            if form >= (4 if split == "dev" else 3):
                operands.reverse()
            question = {
                "task_id": f"cross-{split}-" + sha256(text.encode()).hexdigest()[:16],
                "family": "cross_source", "question": text,
                "company_tickers": [name for name, _ in companies], "fiscal_periods": [f"FY{year + delta}" for delta in (-1, 0, 1)],
                "allowed_source_types": list(SOURCES), "operation": "difference", "operands": operands,
                "unit": output_unit,
            }
            if any(len(matches(operand, documents, SOURCES)) != 1 for operand in operands):
                raise ValueError(f"Ambiguous cross-source operand: {text}")
            label = reference(question, documents)
            if label["verdict"] != "answer" or len(label["evidence_ids"]) != 2:
                raise ValueError(f"Incomplete cross-source reference: {text}")
            questions.append(question)
            labels.append(label)
    return questions, labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--stage", choices=("corpus", "questions"), required=True)
    args = parser.parse_args()
    split = args.split
    name = f"cross_source_{split}"
    corpus_path = DATA / f"{name}_corpus.json"
    if args.stage == "corpus":
        payload = encoded(corpus(split))
        write_frozen(corpus_path, payload)
        print(f"{name}_corpus_sha256={sha256(payload).hexdigest()}")
        return

    payload = corpus_path.read_bytes()
    records = json.loads(payload)
    documents = records["documents"]
    questions, labels = questions_and_labels(split, documents)
    issuer_groups = {ticker: group for _, group, companies, _, _ in groups(split) for ticker, _ in companies}
    if len(questions) != (40 if split == "dev" else 80) or len(documents) != 20 * len(issuer_groups):
        raise ValueError("Incorrect frozen split size")
    files = {f"{name}_questions.json": encoded(questions), f"{name}_labels.json": encoded(labels)}
    manifest = {
        "dataset_version": records["version"], "synthetic": True, "families": ["cross_source"],
        "company_pair_groups": issuer_groups, "document_count": len(documents),
        "source_document_count": len({doc["document_id"] for doc in documents}),
        "corpus_sha256": sha256(payload).hexdigest(),
        "split_sha256": {filename: sha256(raw).hexdigest() for filename, raw in files.items()},
    }
    for filename, raw in files.items():
        write_frozen(DATA / filename, raw)
    write_frozen(DATA / f"{name}_manifest.json", encoded(manifest))
    print(f"{name}_questions={len(questions)} original_docs={manifest['source_document_count']}")


if __name__ == "__main__":
    main()
