"""Score A1 evidence and verdicts after the search and answer have finished."""

from __future__ import annotations

import json
from typing import Sequence

from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_data import load_full_corpus, load_labels
from sandboxed_agent_eval_harness.schemas import JsonDict, ValidatorResult


_MATCH_FIELDS = ("source_type", "modality", "company_ticker", "fiscal_period", "metric")
_VERDICTS = {"support", "contradict", "insufficient"}
_FAILURE_MESSAGES = {
    "a1_invalid_answer": "The response did not contain a valid verdict and citation list.",
    "a1_retrieval_miss": "The ranked evidence did not cover all required source, period, and metric combinations.",
    "a1_invalid_citation": "The response cited irrelevant or unseen evidence, or omitted required citations.",
    "a1_verdict_mismatch": "The response verdict did not match the task label.",
}


def score_full(task_id: str, final_answer: str, result: JsonDict) -> ValidatorResult:
    """Require the labeled evidence even when the verdict is insufficient."""
    labels = load_labels()["tasks"][task_id]
    requirements = labels["expected_evidence"]
    top_k = result.get("top_k")
    hits = result.get("hits", [])[:top_k]
    hit_by_id = {}
    for hit in hits:
        hit_by_id.setdefault(hit["evidence_id"], hit)
    answer = _parse_answer(final_answer)
    citations = answer.get("citations", [])
    verdict = answer.get("verdict")

    matched = _covered_requirements(requirements, list(hit_by_id.values()))
    missing = [req["requirement_id"] for req in requirements if req["requirement_id"] not in matched]
    corpus_matches = set(_covered_requirements(requirements, load_full_corpus()["documents"]))
    cited = [hit_by_id[citation] for citation in dict.fromkeys(citations) if citation in hit_by_id]
    cited_matches = _covered_requirements(requirements, cited)
    valid_citations = {
        hit["evidence_id"] for hit in cited
        if any(_matches(requirement, hit) for requirement in requirements)
    }
    invalid_citations = sorted(set(citations) - valid_citations)
    expected_verdict = labels["expected_verdict"]
    total = len(requirements)
    failures = []
    if not answer:
        failures.append("a1_invalid_answer")
    if len(matched) != total:
        failures.append("a1_retrieval_miss")
    missing_citations = labels["requires_citation"] and (not citations or cited_matches != matched)
    if answer and (invalid_citations or missing_citations):
        failures.append("a1_invalid_citation")
    if answer and verdict != expected_verdict:
        failures.append("a1_verdict_mismatch")

    details = {
        "top_k": top_k,
        "method": result.get("method"),
        "corpus_version": result.get("corpus_version"),
        "retrieved_evidence_ids": list(hit_by_id),
        "matched_requirement_ids": matched,
        "missing_requirement_ids": missing,
        "absent_from_corpus_requirement_ids": [requirement_id for requirement_id in missing if requirement_id not in corpus_matches],
        "outside_top_k_requirement_ids": [requirement_id for requirement_id in missing if requirement_id in corpus_matches],
        "citations": citations,
        "invalid_citations": invalid_citations,
        "evidence_requirements_matched": len(matched),
        "evidence_requirements_total": total,
        "citation_requirements_matched": len(cited_matches),
        "evidence_recall_at_k": len(matched) / total if total else 0.0,
        "citation_exactness": len(cited_matches) / total if total else 0.0,
        "citation_precision": len(valid_citations) / len(set(citations)) if citations else 0.0,
        "expected_verdict": expected_verdict,
        "predicted_verdict": verdict,
        "verdict_correct": verdict == expected_verdict,
        "numeric_checks_total": len(labels["numeric_checks"]),
        # All original seed checks specify a relation with no reference value.
        "numeric_checks_scored": 0,
        "failure_types": failures,
    }
    failure = failures[0] if failures else None
    message = _FAILURE_MESSAGES[failure] if failure else "The ranked evidence, citations, and verdict satisfied the A1 labels."
    return ValidatorResult("a1_rag", not failures, message, failure_type=failure, details=details)


def corpus_evidence_coverage(documents: Sequence[JsonDict]) -> JsonDict:
    """Compute the maximum label coverage supported by the corpus, before ranking."""
    labels = load_labels()["tasks"].values()
    coverage = [
        (len(_covered_requirements(task["expected_evidence"], documents)), len(task["expected_evidence"]))
        for task in labels
    ]
    return {
        "evidence_requirements_available": sum(available for available, _ in coverage),
        "evidence_requirements_total": sum(total for _, total in coverage),
        "fully_covered_tasks": sum(available == total for available, total in coverage),
        "tasks_total": len(coverage),
    }


def corpus_reference_conflicts(questions: Sequence[JsonDict], documents: Sequence[JsonDict]) -> list[JsonDict]:
    """Audit conclusive same-period margin comparisons using the whole corpus."""
    from sandboxed_agent_eval_harness.benchmarks.financial_evidence.answer import build_answer

    labels = load_labels()["tasks"]
    conflicts = []
    for question in questions:
        if question["family"] != "cross_company_comparison":
            continue
        task_id = question["task_id"]
        corpus_answer = _parse_answer(build_answer(question, documents, method="full_engine"))
        corpus_verdict = corpus_answer.get("verdict")
        reference = labels[task_id]
        requirements = reference["expected_evidence"]
        if (corpus_verdict not in {"support", "contradict"}
                or corpus_verdict == reference["expected_verdict"]
                or len(_covered_requirements(requirements, documents)) != len(requirements)):
            continue
        conflicts.append({
            "task_id": task_id,
            "expected_verdict": reference["expected_verdict"],
            "corpus_verdict": corpus_verdict,
        })
    return conflicts


def _parse_answer(final_answer: str) -> JsonDict:
    try:
        answer = json.loads(final_answer)
    except json.JSONDecodeError:
        return {}
    if not isinstance(answer, dict):
        return {}
    verdict = answer.get("verdict")
    citations = answer.get("citations")
    if (not isinstance(verdict, str) or verdict not in _VERDICTS or not isinstance(citations, list)
            or any(not isinstance(citation, str) or not citation for citation in citations)):
        return {}
    return answer


def _matches(requirement: JsonDict, hit: JsonDict) -> bool:
    return all(hit.get(field) == requirement[field] for field in _MATCH_FIELDS)


def _covered_requirements(requirements: Sequence[JsonDict], hits: Sequence[JsonDict]) -> list[str]:
    remaining = list(hits)
    covered = []
    for requirement in requirements:
        matches = [hit for hit in remaining if _matches(requirement, hit)][:requirement["min_count"]]
        if len(matches) == requirement["min_count"]:
            covered.append(requirement["requirement_id"])
            remaining = [hit for hit in remaining if hit not in matches]
    return covered
