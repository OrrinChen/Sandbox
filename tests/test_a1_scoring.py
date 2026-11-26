import json

from sandboxed_agent_eval_harness.benchmarks.financial_evidence import scoring
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.answer import build_answer
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_data import load_full_corpus, load_questions
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.scoring import score_full


_TASK_ID = "phase6:aapl:single_company_trend"


def _annual_revenue_hit():
    return next(
        hit for hit in load_full_corpus()["documents"]
        if hit["company_ticker"] == "AAPL" and hit["fiscal_period"] == "FY2024"
        and hit["source_type"] == "sec_xbrl_companyfacts" and hit["metric"] == "revenue"
    )


def test_a1_scoring_distinguishes_corpus_gap_from_ranked_miss():
    hit = _annual_revenue_hit()
    answer = json.dumps({"verdict": "support", "citations": [hit["evidence_id"]]})
    result = score_full(_TASK_ID, answer, {"top_k": 5, "hits": [hit]})

    assert result.failure_type == "a1_retrieval_miss"
    assert result.details["matched_requirement_ids"] == [f"{_TASK_ID}:ev1"]
    assert result.details["absent_from_corpus_requirement_ids"] == [f"{_TASK_ID}:ev2"]
    assert result.details["outside_top_k_requirement_ids"] == [f"{_TASK_ID}:ev3"]
    assert result.details["failure_types"] == ["a1_retrieval_miss"]


def test_a1_scoring_cannot_replace_first_rank_with_duplicate_id():
    hit = _annual_revenue_hit()
    conflicting_duplicate = {**hit, "fiscal_period": "FY2023"}
    answer = json.dumps({"verdict": "support", "citations": [hit["evidence_id"]]})
    result = score_full(_TASK_ID, answer, {"top_k": 5, "hits": [hit, conflicting_duplicate]})

    assert result.details["retrieved_evidence_ids"] == [hit["evidence_id"]]
    assert result.details["matched_requirement_ids"] == [f"{_TASK_ID}:ev1"]
    assert result.details["citation_requirements_matched"] == 1


def test_a1_scoring_audits_corpus_verdict_conflicts_without_passing_them():
    documents = load_full_corpus()["documents"]
    questions = load_questions()["tasks"]
    task_id = "phase6:aapl:cross_company_comparison"
    conflicts = scoring.corpus_reference_conflicts(list(questions.values()), documents)
    assert len(conflicts) == 9
    conflict = next(item for item in conflicts if item["task_id"] == task_id)
    assert conflict["expected_verdict"] == "support"
    assert conflict["corpus_verdict"] == "contradict"

    signatures = {
        ("AAPL", "sec_xbrl_companyfacts", "operating_income"),
        ("AAPL", "sec_xbrl_companyfacts", "revenue"),
        ("MSFT", "sec_xbrl_companyfacts", "operating_income"),
        ("MSFT", "sec_filing", "revenue"),
    }
    hits = [
        document for document in documents
        if document["fiscal_period"] == "FY2024" and document["numeric_value"] is not None
        and (document["company_ticker"], document["source_type"], document["metric"]) in signatures
    ]
    answer = build_answer(questions[task_id], hits, method="full_engine")
    result = score_full(task_id, answer, {"top_k": 5, "hits": hits})

    assert result.details["evidence_recall_at_k"] == 1
    assert result.details["citation_exactness"] == 1
    assert result.details["failure_types"] == ["a1_verdict_mismatch"]
    assert result.passed is False
