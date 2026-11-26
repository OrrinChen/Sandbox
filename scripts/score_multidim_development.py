"""Strict per-answer, per-pair and self-audit scores for the multidimensional pilot."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import re


FIELDS = ("choice", "value", "citations")
STAGES = ("initial", "audit", "retry")
REFS = frozenset("ABCDE")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
ERROR_EVENTS = ("detected", "localized", "repaired", "localized_and_repaired", "retry_repaired")
CORRECT_EVENTS = ("false_alarm", "spoiled", "retry_spoiled")


def same_number(actual: object, expected: str | None) -> bool:
    if expected is None:
        return actual is None
    if not isinstance(actual, str) or not NUMBER.fullmatch(actual):
        return False
    try:
        return Decimal(actual) == Decimal(expected)
    except ArithmeticError:
        return False


def grade(answer: dict, gold: dict) -> list[str]:
    """An exact answer uses the target choice, numeric value and any one complete citation set."""
    failed = []
    if "choice" not in answer or answer["choice"] != gold["choice"]:
        failed.append("choice")
    if "value" not in answer or not same_number(answer["value"], gold["value"]):
        failed.append("value")
    refs = answer.get("citations")
    if (not isinstance(refs, list) or not all(isinstance(r, str) and r in REFS for r in refs)
            or len(set(refs)) != len(refs) or not any(set(refs) == set(s) for s in gold["citations"])):
        failed.append("citations")
    return failed


def citation_targets(initial: dict, alternatives: list[set[str]]) -> set[str]:
    """Match omissions/extras on any equally close accepted set, plus repeated valid handles."""
    raw = initial.get("citations")
    refs = Counter(r for r in raw if isinstance(r, str) and r in REFS) if isinstance(raw, list) else Counter()
    differences = [set(refs) ^ expected for expected in alternatives]
    distance = min(map(len, differences))
    targets = {r for r, count in refs.items() if count > 1}
    for diff in differences:
        if len(diff) == distance:
            targets.update(diff)
    return targets


def report_question(label: dict, answers: dict) -> dict:
    gold = label["gold"]
    failed = {stage: grade(answer, gold) for stage, answer in answers.items()}
    passed = {stage: not fields for stage, fields in failed.items()}
    first, reviewed = answers["initial"], answers["audit"]
    issues = reviewed.get("issues")
    valid_issues = [
        issue for issue in (issues if isinstance(issues, list) else [])
        if isinstance(issue, dict) and issue.get("field") in FIELDS
        and isinstance(issue.get("ref"), str) and issue["ref"] in REFS
        and isinstance(issue.get("why"), str) and issue["why"].strip()
    ]
    flagged = reviewed.get("decision") == "revise" and bool(valid_issues)
    alternatives = [set(refs) for refs in gold["citations"]]
    support = set.union(*alternatives)
    cite_targets = citation_targets(first, alternatives)
    matched = [
        issue for issue in valid_issues if flagged and issue["field"] in failed["initial"]
        and issue["ref"] in (cite_targets if issue["field"] == "citations" else support)
    ]
    was_correct = passed["initial"]
    return {
        "row": first["row"], "dimension": label["dimension"], "pair_id": label["pair_id"], "side": label["side"],
        "answers": answers, "gold": gold, "failed_fields": failed, "passed": passed,
        "matched_issues": matched,
        "detected": not was_correct and flagged, "localized": bool(matched),
        "repaired": not was_correct and passed["audit"],
        "localized_and_repaired": bool(matched) and passed["audit"],
        "false_alarm": was_correct and flagged, "spoiled": was_correct and not passed["audit"],
        "retry_repaired": not was_correct and passed["retry"], "retry_spoiled": was_correct and not passed["retry"],
    }


def paired_result(left: bool, right: bool) -> str:
    return {(True, True): "both_pass", (True, False): "left_only",
            (False, True): "right_only", (False, False): "both_fail"}[left, right]


def summarize(rows: list[dict], pairs: list[dict]) -> dict:
    passes = {stage: sum(r["passed"][stage] for r in rows) for stage in STAGES}
    errors = len(rows) - passes["initial"]
    counts = {event: sum(r[event] for r in rows) for event in ERROR_EVENTS + CORRECT_EVENTS}
    ratios = {}
    for event, count in counts.items():
        denominator = errors if event in ERROR_EVENTS else passes["initial"]
        ratios[event] = {"count": count, "denominator": denominator,
                         "rate": count / denominator if denominator else None}
    outcomes = Counter(paired_result(r["passed"]["audit"], r["passed"]["retry"]) for r in rows)
    return {
        "questions": len(rows), "initial_failed": errors, **{f"{s}_passed": passes[s] for s in STAGES},
        **counts, "conditional_rates": ratios, "pair_count": len(pairs),
        "pairs_both_passed": {stage: sum(p["result"][stage] == "both_pass" for p in pairs) for stage in STAGES},
        "failed_field_counts": {
            stage: {field: sum(field in r["failed_fields"][stage] for r in rows) for field in FIELDS}
            for stage in STAGES
        },
        "audit_vs_retry": {"both_pass": outcomes["both_pass"], "audit_only": outcomes["left_only"],
                          "retry_only": outcomes["right_only"], "both_fail": outcomes["both_fail"]},
    }


def make_report(labels: dict[int, dict], initial: dict[int, dict], audit: dict[int, dict],
                retry: dict[int, dict]) -> dict:
    """Use the same question identities for all three stages. Each pair has two ordered sides."""
    stages = {"initial": initial, "audit": audit, "retry": retry}
    if not labels or any(responses.keys() != labels.keys() for responses in stages.values()):
        raise ValueError("Expected the same nonempty row set in all three stages and the scoring labels")
    rows, groups = [], defaultdict(list)
    for number, label in sorted(labels.items()):
        answers = {stage: responses[number] for stage, responses in stages.items()}
        if any(answer.get("row") != number for answer in answers.values()):
            raise ValueError(f"Stage response has an inconsistent row identifier at {number}")
        result = report_question(label, answers)
        rows.append(result)
        groups[result["pair_id"]].append(result)
    pairs = []
    for pair_id, members in sorted(groups.items()):
        members.sort(key=lambda item: item["side"])
        if ([item["side"] for item in members] != [0, 1]
                or members[0]["dimension"] != members[1]["dimension"]):
            raise ValueError(f"Expected two sides in one dimension for pair {pair_id}")
        left, right = members
        pairs.append({
            "pair_id": pair_id, "dimension": left["dimension"], "rows": [left["row"], right["row"]],
            "result": {stage: paired_result(left["passed"][stage], right["passed"][stage]) for stage in STAGES},
        })
    dimensions = sorted({row["dimension"] for row in rows})
    return {
        "overall": summarize(rows, pairs),
        "by_dimension": {d: summarize([r for r in rows if r["dimension"] == d],
                                     [p for p in pairs if p["dimension"] == d]) for d in dimensions},
        "per_question": rows, "pairs": pairs,
        "diagnosis_rule": (
            "Detected requires an explicit revision flag and a structured issue. Localized also requires "
            "a failed field and an applicable evidence handle. Free-text explanations are recorded. "
            "Repairs and spoiled answers follow strict scores independently of the declared decision."
        ),
    }
