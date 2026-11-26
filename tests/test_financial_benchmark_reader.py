import json

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.reader import read_answer


def _question(*operands, operation="lookup", unit="usd_millions"):
    return {
        "allowed_source_types": ["filing", "release"],
        "operation": operation,
        "operands": list(operands),
        "unit": unit,
    }


def _operand(metric="revenue", **fields):
    return {"ticker": "ABCD", "period": "FY2025", "metric": metric, **fields}


def _hit(evidence_id, value, **fields):
    return {
        "evidence_id": evidence_id,
        "company_ticker": "ABCD",
        "fiscal_period": "FY2025",
        "metric": "revenue",
        "source_type": "filing",
        "currency": "USD",
        "unit": "thousands",
        "numeric_value": value,
        **fields,
    }


@pytest.mark.parametrize("method", ["bm25", "dense_proxy", "hybrid", "graph", "full_engine"])
def test_reader_calculates_ordered_difference_with_exact_units_and_sources(method):
    question = _question(_operand(source_type="filing"), _operand("cost", source_type="release"), operation="difference")
    hits = [
        _hit("wrong_issuer", "45", company_ticker="WXYZ", metric="cost", source_type="release"),
        _hit("wrong_source", "51", source_type="release"),
        _hit("wrong_period", "52", fiscal_period="FY2024"),
        _hit("cost", "300501", metric="cost", source_type="release", unit="USD"),
        _hit("revenue", "710.5"),
    ]
    answer = json.loads(read_answer(question, hits, method=method))
    assert answer == {"verdict": "answer", "answer_value": "0.409999", "unit": "usd_millions", "citations": ["revenue", "cost"]}


def test_reader_reconciles_values_across_units_and_cites_conflicting_facts():
    question = _question(_operand())
    hits = [
        _hit("release", "7", unit="millions", source_type="release"),
        _hit("equivalent", "7000"),
        _hit("conflict", "7500000", unit="USD"),
    ]
    baseline = json.loads(read_answer(question, hits, method="graph"))
    reconciled = json.loads(read_answer(question, hits[:2], method="full_engine"))
    conflicting = json.loads(read_answer(question, hits, method="full_engine"))
    assert baseline == reconciled == {"verdict": "answer", "answer_value": "7", "unit": "usd_millions", "citations": ["release"]}
    assert conflicting == {"verdict": "conflict", "answer_value": None, "unit": "usd_millions", "citations": ["release", "conflict"]}


def test_reader_abstains_without_valid_observed_evidence():
    question = _question(_operand())
    hits = [
        _hit("wrong_metric", "100", metric="cash"),
        _hit("wrong_currency", "100", currency="EUR"),
        _hit("unknown_unit", "100", unit="billions"),
        _hit("non_finite", "NaN"),
        _hit("not_numeric", "pending"),
    ]
    answer = json.loads(read_answer(question, hits, method="full_engine"))
    assert answer == {"verdict": "insufficient", "answer_value": None, "unit": "usd_millions", "citations": []}
