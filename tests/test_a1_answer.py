import json

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_evidence.answer import build_answer


def test_chart_comparison_requires_the_same_reporting_scope():
    question = {
        "question": "Does NVIDIA's investor-deck chart reconcile to the SEC filing?",
        "company_tickers": ["NVDA"],
        "fiscal_periods": ["FY2024"],
        "allowed_source_types": ["investor_deck", "sec_xbrl_companyfacts"],
    }
    facts = {"company_ticker": "NVDA", "fiscal_period": "FY2024", "metric": "revenue", "currency": "USD"}
    chart = {
        **facts, "evidence_id": "chart", "source_type": "investor_deck", "modality": "chart",
        "section_or_page": "Page 1 / Data Center Revenue", "numeric_value": "47.5", "unit": "billions",
    }
    filing = {
        **facts, "evidence_id": "filing", "source_type": "sec_xbrl_companyfacts", "modality": "xbrl",
        "section_or_page": "us-gaap:Revenues", "numeric_value": "114000000000", "unit": "USD",
    }
    answer = json.loads(build_answer(question, [chart, filing], method="full_engine"))
    assert answer["verdict"] == "insufficient"

    total_chart = {**chart, "section_or_page": "Page 1 / Total Revenue", "numeric_value": "114"}
    answer = json.loads(build_answer(question, [total_chart, filing], method="full_engine"))
    assert answer["verdict"] == "support"


@pytest.mark.parametrize("subject,peer,verdict", [("AAA", "BBB", "support"), ("BBB", "AAA", "contradict")])
def test_operating_margin_cites_the_calculation_operands(subject, peer, verdict):
    question, hits = _margin_fixture(subject, peer)

    answer = json.loads(build_answer(question, hits, method="full_engine"))

    assert answer["verdict"] == verdict
    assert set(answer["citations"]) == {
        f"{subject}-income", f"{subject}-revenue", f"{peer}-income", f"{peer}-table",
    }


def test_operating_margin_abstains_when_the_peer_sources_disagree():
    question, hits = _margin_fixture("AAA", "BBB")
    peer_table = next(hit for hit in hits if hit["evidence_id"] == "BBB-table")
    peer_table["numeric_value"] = "90"

    answer = json.loads(build_answer(question, hits, method="full_engine"))

    assert answer["verdict"] == "insufficient"
    assert {"BBB-revenue", "BBB-table"} <= set(answer["citations"])


def test_operating_margin_uses_peer_xbrl_when_a_table_is_missing():
    question, hits = _margin_fixture("AAA", "BBB")
    hits = [hit for hit in hits if hit["evidence_id"] != "BBB-table"]

    answer = json.loads(build_answer(question, hits, method="full_engine"))

    assert answer["verdict"] == "support"
    assert set(answer["citations"]) == {"AAA-income", "AAA-revenue", "BBB-income", "BBB-revenue"}


def _margin_fixture(subject, peer):
    question = {
        "question": f"Was {subject}'s operating margin higher than {peer}'s in FY2024?",
        "company_tickers": [subject, peer],
        "fiscal_periods": ["FY2024"],
        "allowed_source_types": ["sec_xbrl_companyfacts", "sec_filing"],
    }
    hits = []
    for ticker, income, revenue in [("AAA", "30000000000", "100"), ("BBB", "20000000000", "100")]:
        common = {"company_ticker": ticker, "fiscal_period": "FY2024", "currency": "USD"}
        xbrl = {**common, "source_type": "sec_xbrl_companyfacts", "modality": "xbrl", "unit": "USD"}
        filing = {**common, "source_type": "sec_filing", "metric": "revenue"}
        hits.extend([
            {**filing, "evidence_id": f"{ticker}-paragraph", "modality": "text"},
            {**filing, "evidence_id": f"{ticker}-table", "modality": "table", "unit": "billions", "numeric_value": revenue},
            {**xbrl, "evidence_id": f"{ticker}-income", "metric": "operating_income", "numeric_value": income},
            {**xbrl, "evidence_id": f"{ticker}-revenue", "metric": "revenue", "numeric_value": str(int(revenue) * 10**9)},
        ])
    return question, hits
