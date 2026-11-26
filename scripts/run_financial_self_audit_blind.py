"""Freeze and replay a recorded, company-disjoint financial self-audit comparison."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from typing import Iterable

from run_financial_self_audit_pilot import FIELDS, digest, indexed, paired, read, stage_rows, write


ROOT = Path(__file__).resolve().parents[1]
REFS = "ABCDE"
STAGES = ("initial", "audit", "retry")
BATCH_SIZE = 10
COUNT = 60
BATCHES = range(1, COUNT // BATCH_SIZE + 1)
OUTPUT_TOKENS = 480
FAMILIES = {
    "asset_measurement_policy": 10,
    "fx_indexed_financing": 10,
    "survival_weighted_credit_loss": 10,
    "dealing_nav_waterfall": 10,
    "exact_batch_reconciliation": 4,
}
SCORER = "src/sandboxed_agent_eval_harness/benchmarks/financial_benchmark/scoring.py"
CHECKS = dict(zip(FIELDS, ("verdict_correct", "numeric_correct", "unit_correct", "citation_correct")))
COMMON = """Answer each row independently, using only its question and five ordered excerpts.
Use the stated date, applicable rules and source version. Use exact decimals and the stated rounding.
Return one JSON array, with one object per row. Include row, verdict (answer, insufficient, or conflict),
answer_value (a decimal string, or null when applicable), unit (usd, usd_thousands, or usd_millions),
and all and only necessary citation handles in citations. You may include a compact checkpoints field.
Use one response and at most 480 output tokens per row, including any review fields. Do not use code,
calculation tools, outside information, or other files to solve these questions.
"""
AUDIT = """Review the supplied initial answer from your model against the same excerpts. Decide keep or revise.
Return your final answer in the same fields, plus decision and issues. Use an empty issues list if no
error was found. For each error you actually found, give field (verdict, answer_value, unit, or citations),
ref (one excerpt handle supporting the issue), and a short explanation of what is wrong. If you choose
keep, preserve the original answer fields. A revised answer must still satisfy the original requirements.
"""


def stable_text(value: str) -> str:
    return " ".join(value.casefold().split())


def text_digest(value: str) -> str:
    return sha256(stable_text(value).encode()).hexdigest()


def inventory(rows: Iterable[dict]) -> tuple[set[str], set[str], set[str]]:
    companies, documents, fingerprints = set(), set(), set()
    for row in rows:
        companies.add(stable_text(row.get("issuer") or row["question"].split(".", 1)[0]))
        for source in row["evidence"]:
            if source.get("document_id"):
                documents.add(source["document_id"])
            fingerprints.add(text_digest(source["text"]))
    return companies, documents, fingerprints


def dev_inventory(artifacts: Path) -> tuple[set, set, set, dict]:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.data import load_corpus

    paths = [
        artifacts / "financial-self-audit-dev/public/questions.json",
        artifacts / "financial-self-audit-implicit-dev/public/questions.json",
        *sorted((artifacts / "financial-self-audit-natural-errors").glob("*/public/questions.json")),
    ]
    if len(paths) < 3 or not all(path.is_file() for path in paths):
        raise ValueError("Expected the archived self-audit development inputs")
    companies, documents, fingerprints = inventory(row for path in paths for row in read(path))
    for split in ("dev", "cross_source_dev"):
        for source in load_corpus(split=split)["documents"]:
            companies.add(stable_text(source["company_name"]))
            documents.add(source["document_id"])
            fingerprints.add(text_digest(source["text"]))
    return companies, documents, fingerprints, {str(path.relative_to(artifacts)): digest(path) for path in paths}


def build_fixture() -> tuple[list[dict], list[dict]]:
    from build_financial_blind_assets import build as build_assets
    from build_financial_blind_risk import build as build_risk
    from build_financial_blind_rules import build as build_rules

    pairs = []
    for build in (build_assets, build_risk, build_rules):
        source, labels = build()
        if [row["row"] for row in source] != [label["row"] for label in labels]:
            raise ValueError("Generated question and label rows disagree")
        pairs.extend(zip(source, labels))
    Random(840917).shuffle(pairs)
    rows, labels = zip(*pairs)
    return ([{**item, "row": n} for n, item in enumerate(rows, 1)],
            [{**item, "row": n} for n, item in enumerate(labels, 1)])


def write_once(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def reader_rows(rows: Iterable[dict]) -> list[dict]:
    return [{"row": row["row"], "question": row["question"],
             "evidence": [{"ref": hit["ref"], "text": hit["text"]} for hit in row["evidence"]]}
            for row in rows]


def stage_files(root: Path, stage: str, rows: list[dict], initial: dict | None = None) -> list[Path]:
    directory = root / stage
    directory.mkdir()
    prompt = directory / "prompt.txt"
    prompt.write_text(COMMON + (AUDIT if stage == "audit" else ""), encoding="utf-8")
    payload = stage_rows(rows, initial)
    paths = [prompt]
    for batch in BATCHES:
        offset = (batch - 1) * BATCH_SIZE
        path = directory / f"inputs-{batch}.json"
        write_once(path, payload[offset:offset + BATCH_SIZE])
        paths.append(path)
    return paths


def hashes(root: Path, paths: Iterable[Path]) -> dict[str, str]:
    return {str(path.relative_to(root)): digest(path) for path in paths}


def verify_hashes(root: Path, expected: dict[str, str]) -> None:
    for relative, value in expected.items():
        if digest(root / relative) != value:
            raise ValueError(f"Recorded content changed after locking: {relative}")


def validate_fixture(rows: list[dict], labels: list[dict], artifacts: Path) -> dict:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer

    public = indexed(rows, set(range(1, COUNT + 1)))
    private = indexed(labels, public.keys())
    quotas = Counter(label["family"] for label in labels)
    if any(quotas.pop(family, 0) != count for family, count in FAMILIES.items()):
        raise ValueError("Unexpected quantitative family counts")
    if sorted(quotas.values()) != [4, 4, 4, 4]:
        raise ValueError("Expected four distinct rule and transaction-state families")
    for row, question in public.items():
        refs = [hit["ref"] for hit in question["evidence"]]
        if (refs != list(REFS) or not question["question"].startswith(question["issuer"])
                or any(not hit["text"] or not hit["document_id"] for hit in question["evidence"])):
            raise ValueError(f"Bad fixed evidence in row {row}")
        label = private[row]
        hits = [{"evidence_id": ref} for ref in refs]
        reference = {key: label[key] for key in ("verdict", "answer_value", "unit")} | {"citations": label["evidence_ids"]}
        full = score_answer(label, json.dumps(reference), hits, 5)
        if not full.passed or any(score_answer(label, json.dumps(reference),
                    [hit for hit in hits if hit["evidence_id"] != ref], 5).passed for ref in label["evidence_ids"]):
            raise ValueError(f"Reference is not uniquely covered in row {row}")

    companies, documents, fingerprints = inventory(rows)
    prior_companies, prior_docs, prior_fingerprints, prior_hashes = dev_inventory(artifacts)
    if (len(companies) != COUNT or len(documents) != COUNT * 5 or len(fingerprints) != COUNT * 5
            or companies & prior_companies or documents & prior_docs or fingerprints & prior_fingerprints):
        raise ValueError("Blind sources are repeated or overlap development sources")
    return {
        "family_counts": dict(sorted(Counter(label["family"] for label in labels).items())),
        "issuer_count": len(companies), "original_document_count": len(documents),
        "development_issuers_compared": len(prior_companies),
        "development_source_document_ids_compared": len(prior_docs),
        "development_excerpt_hashes_compared": len(prior_fingerprints),
        "development_input_sha256": prior_hashes,
        "overlap": {"issuer_names": 0, "document_ids": 0, "normalized_excerpt_hashes": 0},
    }


def freeze(root: Path, artifacts: Path) -> None:
    rows, labels = build_fixture()
    separation = validate_fixture(rows, labels, artifacts)
    root.mkdir(parents=True)
    for name in ("public", "private"):
        (root / name).mkdir()
    question_path, label_path = root / "public/questions.json", root / "private/labels.json"
    write_once(question_path, rows)
    write_once(label_path, labels)
    paths = [question_path, label_path, *stage_files(root, "initial", reader_rows(rows))]
    meta = {"schema": 1, "question_count": COUNT, "top_k": 5, "scorer": SCORER,
            "scorer_sha256": digest(ROOT / SCORER), "fixture_sha256": hashes(root, paths), **separation}
    write_once(root / "freeze.json", meta)


def frozen_public(root: Path, manifest: dict) -> list[dict]:
    if digest(ROOT / SCORER) != manifest["scorer_sha256"]:
        raise ValueError("Strict rubric changed after freezing")
    verify_hashes(root, {name: value for name, value in manifest["fixture_sha256"].items()
                         if not name.startswith("private/")})
    return reader_rows(read(root / "public/questions.json"))


def stage_responses(root: Path, stage: str) -> tuple[dict, list[Path]]:
    results, paths = {}, []
    for batch in BATCHES:
        directory = root / stage
        responses_path = directory / f"responses-{batch}.json"
        inputs = read(directory / f"inputs-{batch}.json")
        expected = {row["row"] for row in inputs}
        if expected.intersection(results):
            raise ValueError("Question assigned more than once")
        results.update(indexed(read(responses_path), expected))
        paths.append(responses_path)
    if results.keys() != set(range(1, COUNT + 1)):
        raise ValueError(f"Incomplete {stage} stage")
    return results, paths


def lock_initial(root: Path, rows: list[dict]) -> None:
    initial, responses = stage_responses(root, "initial")
    paths = [root / "freeze.json", *responses, *stage_files(root, "audit", rows, initial),
             *stage_files(root, "retry", rows)]
    write_once(root / "initial_lock.json", hashes(root, paths))


def grade_diagnoses(response: dict, initial_score: dict) -> tuple[bool, list[dict]]:
    issues = response.get("issues", [])
    if (response.get("decision") not in {"keep", "revise"} or not isinstance(issues, list)
            or not all(isinstance(issue, dict) for issue in issues)):
        raise ValueError(f"Malformed audit decision/issues on row {response['row']}")
    details = initial_score["details"]
    refs = set(details["expected_evidence_ids"])
    cited = set(details["cited_evidence_ids"])
    supported = []
    for issue in issues:
        field = issue.get("field")
        clue = issue.get("ref")
        explanation = issue.get("explanation")
        if field not in CHECKS or not isinstance(explanation, str) or not explanation.strip():
            continue
        targets = ((refs ^ cited) & set(REFS) or refs) if field == "citations" else refs
        if not details[CHECKS[field]] and clue in targets:
            supported.append(issue)
    return bool(issues) or response["decision"] == "revise", supported


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    correct = sum(row["initial"]["passed"] for row in rows)
    return {
        "questions": total,
        "initial_passed": correct,
        "initial_failed": total - correct,
        "audit_passed": sum(row["audit"]["passed"] for row in rows),
        "retry_passed": sum(row["retry"]["passed"] for row in rows),
        **{metric: sum(row[metric] for row in rows) for metric in (
            "detected", "localized", "repaired", "localized_and_repaired",
            "false_alarm", "spoiled", "retry_repaired", "retry_spoiled",
        )},
        "audit_vs_retry": paired(rows, "audit", "retry"),
    }


def score(root: Path, rows: list[dict], manifest: dict) -> None:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer

    verify_hashes(root, read(root / "initial_lock.json"))
    recordings = {stage: stage_responses(root, stage) for stage in STAGES}
    verify_hashes(root, manifest["fixture_sha256"])
    labels = indexed(read(root / "private/labels.json"), set(range(1, COUNT + 1)))
    report_rows = []
    for question in rows:
        number = question["row"]
        label = labels[number]
        responses = {stage: recording[number] for stage, (recording, _) in recordings.items()}
        hits = [{"evidence_id": hit["ref"]} for hit in question["evidence"]]
        scores = {stage: score_answer(label, json.dumps({field: res[field] for field in FIELDS if field in res}),
                                      hits, 5).to_dict() for stage, res in responses.items()}
        flagged, diagnoses = grade_diagnoses(responses["audit"], scores["initial"])
        original = scores["initial"]["passed"]
        final, retry = scores["audit"]["passed"], scores["retry"]["passed"]
        report_rows.append({
            "row": number, "family": label["family"], "question": question["question"], **scores,
            "answers": responses, "matched_diagnoses": diagnoses,
            "detected": not original and flagged, "localized": not original and bool(diagnoses),
            "repaired": not original and final, "localized_and_repaired": not original and bool(diagnoses) and final,
            "false_alarm": original and flagged, "spoiled": original and not final,
            "retry_repaired": not original and retry, "retry_spoiled": original and not retry,
        })

    summary = summarize(report_rows)
    report = {
        "protocol": {"model": "inherited Codex conversation model via independent readers",
                     "batch_size": BATCH_SIZE, "completions_per_batch_per_stage": 1,
                     "requested_output_tokens_per_row": OUTPUT_TOKENS, "actual_reasoning_tokens": "unavailable",
                     "top_k": 5, "calculation_tools": False, "scorer_sha256": manifest["scorer_sha256"]},
        "freeze_sha256": digest(root / "freeze.json"),
        "initial_lock_sha256": digest(root / "initial_lock.json"),
        "recording_sha256": hashes(root, (path for _, paths in recordings.values() for path in paths)),
        "summary": summary,
        "by_family": {family: summarize([r for r in report_rows if r["family"] == family])
                      for family in manifest["family_counts"]},
        "diagnosis_rule": "Localized requires a marked failed score field and an applicable evidence handle. "
                          "The free-text explanation is recorded and is not automatically judged.",
        "rows": report_rows,
    }
    write(root / "report.json", report)
    with (root / "per_question.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["row", "family", "question", *[f"{stage}_passed" for stage in STAGES],
                  "detected", "localized", "repaired", "localized_and_repaired",
                  "false_alarm", "spoiled", "retry_repaired", "retry_spoiled"]
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        for row in report_rows:
            writer.writerow({**row, **{f"{stage}_passed": row[stage]["passed"] for stage in STAGES}})
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "lock-initial", "score"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--development-artifacts", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.directory, args.development_artifacts)
        return
    manifest = read(args.directory / "freeze.json")
    rows = frozen_public(args.directory, manifest)
    if args.action == "lock-initial":
        lock_initial(args.directory, rows)
    else:
        score(args.directory, rows, manifest)


if __name__ == "__main__":
    main()
