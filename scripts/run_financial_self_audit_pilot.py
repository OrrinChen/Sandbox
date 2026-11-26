"""Stage and strictly score the recorded 32-question financial self-audit pilot."""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path


REFS = "ABCDE"
FIELDS = ("verdict", "answer_value", "unit", "citations")
STAGES = ("initial", "audit", "retry")
COMMON = """Work independently on each row with the question and that row's five excerpts in their given order.
Use only the excerpts. Preserve the requested company, period, reporting basis, units and signed calculation.
Use verdict answer, insufficient, or conflict. Output the exact number as a decimal string or null when appropriate.
Unit is usd, usd_thousands, or usd_millions. Cite only excerpt handles used. Record operands in calculation
order as ref, value (exact decimal string, using the source amount before conversion), and unit (same enum).
Each response must be a JSON object with row, verdict, answer_value, unit, citations, and operands.
Use at most 220 output tokens per row, including any audit fields. Submit only the requested JSON.
One response per row. Do not use tools to solve the financial questions or look up outside information.
"""
PROMPTS = {
    "initial": COMMON + "Solve each question and submit the result as a JSON array.\n",
    "retry": COMMON + "Solve each question independently and submit the result as a JSON array.\n",
    "audit": COMMON + """Review the supplied initial answer, which you produced on your first attempt.
Before giving the final fields, emit decision (keep or revise) and issues (a JSON list, empty if none).
For each actual error you find, give field (operand_ref, operand_value, operand_unit, verdict, answer_value,
unit, or citations), slot (one-based operand index for operand errors, otherwise null), and ref
(one supplied excerpt handle supporting your diagnosis). Verify before deciding whether to keep or revise.
When keeping the answer, reproduce its answer fields. Submit one JSON array.\n""",
}
IMPLICIT_OUTPUT_TOKENS = 480


def stage_prompt(stage: str, implicit: bool) -> str:
    prompt = PROMPTS[stage]
    if not implicit:
        return prompt
    prompt = prompt.replace("in calculation\norder", "in your calculation order")
    prompt = prompt.replace("and unit (same enum).", "unit (same enum), and sign (1 for added, -1 for subtracted).")
    prompt = prompt.replace("Cite only excerpt handles used.", "Cite all and only excerpt handles used, including policy or date evidence needed to interpret the amounts.")
    return prompt.replace("220 output tokens", f"{IMPLICIT_OUTPUT_TOKENS} output tokens").replace(
        "operand_value, operand_unit, verdict", "operand_value, operand_unit, operand_sign, verdict")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def indexed(rows: list[dict], expected: set[int]) -> dict[int, dict]:
    result = {row["row"]: row for row in rows}
    if len(result) != len(rows) or result.keys() != expected:
        raise ValueError("Expected one response per assigned row")
    return result


def questions(root: Path) -> list[dict]:
    relative_path = "public/questions.json"
    path = root / relative_path
    if read(root / "fixture_hashes.json")[relative_path] != digest(path):
        raise ValueError("Public questions differ from the fixed pilot fixture")
    rows = read(path)
    indexed(rows, set(range(1, 33)))
    for row in rows:
        if set(row) != {"row", "question", "evidence"} or [hit["ref"] for hit in row["evidence"]] != list(REFS):
            raise ValueError("Model inputs must contain a question and five ordered excerpts")
        if any(set(hit) != {"ref", "text"} or not hit["text"] for hit in row["evidence"]):
            raise ValueError("Excerpts must contain only text and a rank-based citation handle")
    return sorted(rows, key=lambda row: row["row"])


def stage_rows(rows: list[dict], initial: dict | None) -> list[dict]:
    return [{**row, "initial_answer": initial[row["row"]]} for row in rows] if initial is not None else rows


def prepare(root: Path, stage: str, rows: list[dict], initial: dict | None, *, implicit: bool = False) -> None:
    folder = root / stage
    folder.mkdir()
    (folder / "prompt.txt").write_text(stage_prompt(stage, implicit), encoding="utf-8")
    source = stage_rows(rows, initial)
    for batch, offset in enumerate((0, 16), 1):
        write(folder / f"inputs-{batch}.json", source[offset:offset + 16])


def stage_results(root: Path, stage: str, rows: list[dict], initial: dict | None, *, implicit: bool = False) -> tuple[dict, dict]:
    folder = root / stage
    prompt = folder / "prompt.txt"
    if prompt.read_text(encoding="utf-8") != stage_prompt(stage, implicit):
        raise ValueError(f"Prompt drift in {stage}")
    hashes = {str(prompt.relative_to(root)): digest(prompt)}
    results = {}
    source = stage_rows(rows, initial)
    for batch, offset in enumerate((0, 16), 1):
        inputs = folder / f"inputs-{batch}.json"
        if read(inputs) != source[offset:offset + 16]:
            raise ValueError(f"Evidence or prior answer drift in {inputs}")
        responses = folder / f"responses-{batch}.json"
        results.update(indexed(read(responses), {row["row"] for row in source[offset:offset + 16]}))
        for path in (inputs, responses):
            hashes[str(path.relative_to(root))] = digest(path)
    return results, hashes


def answer(response: dict) -> dict:
    return {field: response[field] for field in FIELDS if field in response}


def same_number(actual, expected: str) -> bool:
    try:
        return isinstance(actual, str) and Decimal(actual) == Decimal(expected)
    except InvalidOperation:
        return False


def diagnostic_targets(response: dict, label: dict, details: dict, *, implicit: bool = False) -> dict:
    refs = set(label["evidence_ids"])
    targets = {}
    for field, key in zip(FIELDS, ("verdict_correct", "numeric_correct", "unit_correct", "citation_correct")):
        if not details[key]:
            targets[field, None] = refs
    observed = response.get("operands", [])
    if implicit:
        if ("citations", None) in targets:
            cited = set(details.get("cited_evidence_ids", []))
            mismatched_refs = (refs ^ cited) & set(REFS)
            targets["citations", None] = mismatched_refs or refs
        for slot, operand, gold in _match_operands(observed, label["operands"]):
            for field in ("ref", "value", "unit", "sign"):
                if not _same_operand_field(field, operand, gold):
                    targets[f"operand_{field}", slot] = {gold["ref"]}
        return targets
    for slot, gold in enumerate(label["operands"], 1):
        operand = observed[slot - 1] if slot <= len(observed) else {}
        for field in ("ref", "value", "unit"):
            actual = operand.get(field)
            matches = same_number(actual, gold[field]) if field == "value" else actual == gold[field]
            if not matches:
                targets[f"operand_{field}", slot] = {gold["ref"]}
    return targets


def _same_operand_field(field: str, actual: dict, expected: dict) -> bool:
    return (same_number(actual.get(field), expected[field]) if field == "value"
            else actual.get(field) == expected[field])


def _match_operands(observed: list[dict], expected: list[dict]) -> list[tuple[int, dict, dict]]:
    """Align unambiguous terms without penalizing a commutative reorder."""
    unmatched = dict(enumerate(observed, 1))
    remaining = list(expected)
    matches = []
    for fields in (("ref", "value", "unit", "sign"), ("ref", "value", "unit"), ("ref",), ("value", "unit")):
        for slot, actual in list(unmatched.items()):
            candidates = [gold for gold in remaining if all(_same_operand_field(field, actual, gold) for field in fields)]
            if len(candidates) == 1:
                gold = candidates[0]
                matches.append((slot, unmatched.pop(slot), gold))
                remaining.remove(gold)
    if len(unmatched) == len(remaining) == 1:
        slot, actual = next(iter(unmatched.items()))
        matches.append((slot, actual, remaining[0]))
    return matches


def diagnosis_hits(issues: list[dict], targets: dict) -> int:
    return sum(issue.get("ref") in targets.get((issue.get("field"), issue.get("slot")), ())
               for issue in issues)


def paired(rows: list[dict], left: str, right: str) -> dict:
    counts = Counter((row[left]["passed"], row[right]["passed"]) for row in rows)
    return {"both_pass": counts[True, True], "left_only": counts[True, False],
            "right_only": counts[False, True], "both_fail": counts[False, False]}


def score(root: Path, rows: list[dict], initial: dict, first_hashes: dict, *, implicit: bool = False) -> dict:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer

    audited, audit_hashes = stage_results(root, "audit", rows, initial, implicit=implicit)
    retried, retry_hashes = stage_results(root, "retry", rows, None, implicit=implicit)
    labels_path = root / "private/labels.json"
    labels_hash = digest(labels_path)
    if read(root / "fixture_hashes.json")["private/labels.json"] != labels_hash:
        raise ValueError("Scoring labels differ from the fixed pilot fixture")
    labels = indexed(read(labels_path), initial.keys())
    details = []
    for question in rows:
        row = question["row"]
        label = labels[row]
        hits = [{"evidence_id": hit["ref"]} for hit in question["evidence"]]
        if not set(label["evidence_ids"]) <= set(REFS) or not label["evidence_ids"]:
            raise ValueError(f"Missing reference evidence for row {row}")
        first, audit, retry = initial[row], audited[row], retried[row]
        scores = {stage: score_answer(label, json.dumps(answer(response)), hits, 5).to_dict()
                  for stage, response in zip(STAGES, (first, audit, retry))}
        issues = audit["issues"]
        if not isinstance(issues, list) or any(not isinstance(issue, dict) for issue in issues):
            raise ValueError(f"Invalid diagnostic record for row {row}")
        if audit["decision"] not in {"keep", "revise"}:
            raise ValueError(f"Invalid audit decision for row {row}")
        diagnosis = diagnostic_targets(first, label, scores["initial"]["details"], implicit=implicit)
        details.append({"row": row, "family": label["family"], **scores,
                        "initial_answer": first, "self_audit": audit, "independent_retry": retry,
                        "checked_diagnoses": diagnosis_hits(issues, diagnosis),
                        "flagged": bool(issues) or audit["decision"] == "revise",
                        "initial_operand_trace_matches": not any(slot for _, slot in diagnosis)
                        and (not implicit or len(first.get("operands", [])) == len(label["operands"])
                             == len(_match_operands(first.get("operands", []), label["operands"])))})
    wrong = [row for row in details if not row["initial"]["passed"]]
    right = [row for row in details if row["initial"]["passed"]]
    localized = sum(row["checked_diagnoses"] > 0 for row in wrong)
    repaired = sum(row["audit"]["passed"] for row in wrong)
    wrong_by_family = Counter(row["family"] for row in wrong)
    substantive = [row for row in wrong if not all(row["initial"]["details"][field] for field in
                   ("verdict_correct", "numeric_correct", "unit_correct"))]
    substantive_by_family = Counter(row["family"] for row in substantive)
    return {"task_count": len(details), "top_k": 5, "model": "Codex conversation subagents (inherited model)",
            "budget": {"responses_per_stage_per_batch": 1, "batch_sizes": [16, 16],
                       "requested_output_tokens_per_row": IMPLICIT_OUTPUT_TOKENS if implicit else 220,
                       "inference_settings": "same inherited settings; actual reasoning tokens unavailable"},
            "initial_passed": len(right), "initial_wrong": len(wrong),
            **({"initial_wrong_by_family": dict(wrong_by_family),
                "initial_substantive_wrong_by_family": dict(substantive_by_family),
                "initial_citation_only_wrong": len(wrong) - len(substantive),
                "development_gate": {"minimum_natural_errors": 8, "minimum_error_families": 3,
                                     "passed": len(wrong) >= 8 and len(wrong_by_family) >= 3,
                                     "substantive_only_passed": len(substantive) >= 8
                                     and len(substantive_by_family) >= 3}} if implicit else {}),
            "wrong_flagged": sum(row["flagged"] for row in wrong),
            "wrong_localized": localized,
            "wrong_repaired": repaired,
            "wrong_localization_rate": localized / len(wrong) if wrong else None,
            "wrong_repair_rate": repaired / len(wrong) if wrong else None,
            "wrong_localized_and_repaired": sum(row["checked_diagnoses"] > 0 and row["audit"]["passed"] for row in wrong),
            "false_alarms": sum(row["flagged"] for row in right),
            "correct_answers_broken": sum(not row["audit"]["passed"] for row in right),
            "audit_passed": sum(row["audit"]["passed"] for row in details),
            "retry_passed": sum(row["retry"]["passed"] for row in details),
            "retry_repairs": sum(row["retry"]["passed"] for row in wrong),
            "retry_breaks": sum(not row["retry"]["passed"] for row in right),
            "audit_vs_retry": paired(details, "audit", "retry"),
            "hashes": {**first_hashes, **audit_hashes, **retry_hashes,
                       str(labels_path.relative_to(root)): labels_hash},
            "rows": details}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "lock-initial", "score"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--implicit", action="store_true", help="Use the implicit-question pilot prompts and report.")
    args = parser.parse_args()
    root = args.directory
    rows = questions(root)
    if args.action == "prepare":
        prepare(root, "initial", rows, None, implicit=args.implicit)
        return
    initial, hashes = stage_results(root, "initial", rows, None, implicit=args.implicit)
    lock = root / "initial_lock.json"
    hashes["public/questions.json"] = digest(root / "public/questions.json")
    hashes["fixture_hashes.json"] = digest(root / "fixture_hashes.json")
    if args.action == "lock-initial":
        with lock.open("x", encoding="utf-8") as output:
            json.dump(hashes, output, indent=2)
        prepare(root, "audit", rows, initial, implicit=args.implicit)
        prepare(root, "retry", rows, None, implicit=args.implicit)
        return
    if read(lock) != hashes:
        raise ValueError("Initial answers or their inputs changed after locking")
    report = score(root, rows, initial, hashes, implicit=args.implicit)
    write(root / "report.json", report)
    print(json.dumps({key: value for key, value in report.items() if key not in ("rows", "hashes")}, indent=2))


if __name__ == "__main__":
    main()
