import json
from decimal import Decimal

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.text_reader import read_text_answer


@pytest.mark.parametrize(("question", "value", "citations"), [
    ("For Blue Hill in FY2025, subtract capital spending in the slide deck from cash from operations in the call.",
     "449.5", ["receipt", "outlay"]),
    ("For Blue Hill in FY2025, start from capital spending in the deck, then remove cash from operations in the call.",
     "-449.5", ["outlay", "receipt"]),
    ("Calculate Blue Hill's FY2025 cash from operations minus capital spending. Use the call and the deck respectively.",
     "449.5", ["receipt", "outlay"]),
])
def test_text_reader_preserves_signed_order_and_uses_raw_amounts(question, value, citations):
    hits = [
        ("wrong basis", "Blue Hill, FY2025, earnings call transcript. Adjusted cash from operations: 900 USD millions."),
        ("wrong company", "Blue Hill Partners, FY2025, earnings call transcript. Cash from operations: 900 USD millions."),
        ("wrong period", "Blue Hill, FY2024, investor presentation. Capital spending: 900 USD millions."),
        ("outlay", "Investor presentation for Blue Hill (BLUE) | FY2025 | capital spending | 300.5 USD thousands."),
        ("receipt", "Blue Hill (BLUE) disclosed 0.75 USD millions in cash from operations for FY2025. Source: earnings call transcript."),
    ]
    result = read_text_answer(f"{question} Use thousands of US dollars.", hits, method="full_engine")
    answer = json.loads(result)
    assert Decimal(answer.pop("answer_value")) == Decimal(value)
    assert answer == {"verdict": "answer", "unit": "usd_thousands", "citations": citations}


def test_text_reader_shares_conflict_policy_and_abstains_without_a_matching_fact():
    question = "What was Blue Hill's FY2025 lease expense, in millions of US dollars?"
    hits = [
        ("filing", "Blue Hill (BLUE) annual filing, FY2025. Lease expense was 1.25 USD millions."),
        ("transcript", "Blue Hill [BLUE] · earnings call transcript · FY2025\nThe reporting basis was unchanged. Lease expense: 1500 USD thousands."),
    ]
    assert json.loads(read_text_answer(question, hits, method="hybrid")) == {
        "verdict": "answer", "answer_value": "1.25", "unit": "usd_millions", "citations": ["filing"],
    }
    assert json.loads(read_text_answer(question, hits, method="full_engine")) == {
        "verdict": "conflict", "answer_value": None, "unit": "usd_millions", "citations": ["filing", "transcript"],
    }
    assert json.loads(read_text_answer(question.replace("FY2025", "FY2024"), hits, method="full_engine")) == {
        "verdict": "insufficient", "answer_value": None, "unit": "usd_millions", "citations": [],
    }
