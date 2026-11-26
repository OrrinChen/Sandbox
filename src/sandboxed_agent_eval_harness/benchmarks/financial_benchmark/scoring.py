"""Score exact numeric values, verdicts, and evidence after inference."""

from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.data import SPLITS, _read_split_file
from sandboxed_agent_eval_harness.schemas import JsonDict, ValidatorResult


@lru_cache(maxsize=6)
def load_labels(split: str) -> dict[str, JsonDict]:
    if split not in SPLITS:
        raise ValueError(f"Unknown financial benchmark split: {split}")
    filename = f"{'dev' if split == 'pilot' else split}_labels"
    return {row["task_id"]: row for row in _read_split_file(filename)}


def score(task_id: str, split: str, final_answer: str, result: JsonDict) -> ValidatorResult:
    label = load_labels(split)[task_id]
    return score_answer(label, final_answer, result.get("hits", [])[:5], result.get("top_k"))


def score_answer(label: JsonDict, final_answer: str, hits: list[JsonDict], top_k: int) -> ValidatorResult:
    try:
        answer = json.loads(final_answer)
    except (TypeError, ValueError):
        answer = None
    if not isinstance(answer, dict):
        answer = {}
    citations = answer.get("citations")
    valid_citations = isinstance(citations, list) and all(isinstance(item, str) for item in citations)
    cited = set(citations) if valid_citations else set()
    expected = set(label["evidence_ids"])
    retrieved = {hit["evidence_id"] for hit in hits[:5]}
    abstention_expected = label["verdict"] == "insufficient"
    verdict_correct = answer.get("verdict") == label["verdict"]
    numeric_correct = "answer_value" in answer and _exact_number(answer["answer_value"], label["answer_value"])
    unit_correct = answer.get("unit") == label["unit"]
    citation_correct = valid_citations and len(cited) == len(citations) and cited == expected and cited <= retrieved
    failures = []
    if top_k != 5:
        failures.append("financial_top_k_mismatch")
    if not expected <= retrieved:
        failures.append("financial_evidence_miss")
    if not verdict_correct:
        failures.append("financial_verdict_mismatch")
    if not numeric_correct or not unit_correct:
        failures.append("financial_value_mismatch")
    if not citation_correct:
        failures.append("financial_citation_mismatch")
    return ValidatorResult(
        "financial_benchmark", not failures,
        "The answer, evidence and citations matched the reference." if not failures else "The answer or retrieved evidence failed strict scoring.",
        failure_type=failures[0] if failures else None,
        details={
            "verdict_correct": verdict_correct,
            "expected_verdict": label["verdict"],
            "predicted_verdict": answer.get("verdict"),
            "numeric_correct": numeric_correct,
            "unit_correct": unit_correct,
            "citation_correct": citation_correct,
            "abstention_expected": abstention_expected,
            "abstention_correct": answer.get("verdict") in ("answer", "conflict", "insufficient")
                                  and abstention_expected == (answer.get("verdict") == "insufficient"),
            "evidence_recall_at_k": len(expected & retrieved) / len(expected) if expected else None,
            "missing_evidence_ids": sorted(expected - retrieved),
            "expected_evidence_ids": sorted(expected),
            "cited_evidence_ids": sorted(cited),
            "failure_types": failures,
        },
    )


def _exact_number(actual, expected) -> bool:
    if expected is None:
        return actual is None
    if not isinstance(actual, str):
        return False
    try:
        number = Decimal(actual)
    except InvalidOperation:
        return False
    return number.is_finite() and number == Decimal(expected)
