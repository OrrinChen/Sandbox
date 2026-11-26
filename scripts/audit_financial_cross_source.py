"""Attribute missed operands in the archived cross-source challenge traces."""

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.data import load_corpus, load_questions
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.methods import _select_hits, search_full
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.retrieval import _tokenize


def _matches(hit, operand):
    return (hit["company_ticker"], hit["fiscal_period"], hit["metric"], hit["source_type"]) == (
        operand["ticker"], operand["period"], operand["metric"], operand["source_type"],
    )


def _decoy_kind(hit, target):
    if hit["company_ticker"] != target["company_ticker"]:
        return "different_issuer"
    if hit["fiscal_period"] != target["fiscal_period"]:
        return "different_period"
    if hit["metric"] == f"adjusted_{target['metric']}":
        return "adjusted_target_metric"
    if hit["source_type"] != target["source_type"]:
        return "different_source"
    return "other_metric"


def _scope(hit, arguments):
    return all(hit[field] in arguments[key] for field, key in (
        ("company_ticker", "tickers"), ("fiscal_period", "fiscal_periods"), ("source_type", "source_types"),
    ))


def _ids(hits):
    return [hit["evidence_id"] for hit in hits]


def _audit(run, question, documents):
    events = [json.loads(line) for line in Path(run["trace_path"]).read_text(encoding="utf-8").splitlines()]
    arguments = next(event["payload"]["arguments"] for event in events if event["event_type"] == "tool_call")
    recorded = next(event["payload"]["result"]["hits"] for event in events if event["event_type"] == "tool_result")
    validator = run["validator_results"][0]["details"]
    assert arguments["method"] == "hybrid" and arguments["top_k"] == 5
    query = arguments["query"]
    terms = set(_tokenize(query))
    assert not {"operating", "margin"} <= terms
    filters = {key: arguments[key] for key in ("tickers", "fiscal_periods", "source_types")}
    ranking = search_full("hybrid", query, len(documents), documents, **filters)
    assert _ids(_select_hits(ranking, 5, terms, [])) == _ids(recorded), run["task_id"]
    by_id = {hit["evidence_id"]: hit for hit in documents}
    reference = [by_id[evidence_id] for evidence_id in validator["expected_evidence_ids"]]
    sides = {}
    for index, (side, operand) in enumerate(zip(("left", "right"), question["operands"])):
        target, = (hit for hit in reference if _matches(hit, operand))
        target_id = target["evidence_id"]
        if target_id in _ids(recorded):
            continue
        rank = _ids(ranking).index(target_id) + 1
        missing_terms = sorted(set(_tokenize(target["metric"])) - terms)
        alias_query = " ".join((query, *missing_terms))
        alias_hits = search_full("hybrid", alias_query, 5, documents, **filters) if missing_terms else recorded
        other_operand = question["operands"][1 - index]
        adjusted = f"adjusted_{target['metric']}"
        controls = {
            "canonical_terms_added": target_id in _ids(alias_hits),
            "remove_outside_public_scope_fixed_scores": target_id in _ids(_select_hits(
                [hit for hit in ranking if _scope(hit, arguments)], 5, terms, [],
            )),
            "remove_adjusted_target_metric_fixed_scores": target_id in _ids(_select_hits(
                [hit for hit in ranking if hit["metric"] != adjusted], 5, terms, [],
            )),
            "restrict_to_operand_issuer_period_source_fixed_scores": target_id in _ids(_select_hits(
                [hit for hit in ranking if (hit["company_ticker"], hit["fiscal_period"], hit["source_type"])
                 == (target["company_ticker"], target["fiscal_period"], target["source_type"])], 5, terms, [],
            )),
        }
        sides[side] = {
            "source_type": target["source_type"],
            "metric": target["metric"],
            "evidence_id": target_id,
            "raw_rank": rank,
            "missing_canonical_metric_terms": missing_terms,
            "decoys_in_recorded_top5": dict(Counter(
                "other_required_operand" if _matches(hit, other_operand)
                else _decoy_kind(hit, target) for hit in recorded
            )),
            "diagnostic_recovery": controls,
        }
    assert {row["evidence_id"] for row in sides.values()} == set(validator["missing_evidence_ids"])
    all_missing_terms = sorted({term for row in sides.values() for term in row["missing_canonical_metric_terms"]})
    joint_query = " ".join((query, *all_missing_terms))
    joint_hits = search_full("hybrid", joint_query, 5, documents, **filters)
    return {
        "task_id": run["task_id"], "trace_path": run["trace_path"], "missed_operands": sides,
        "joint_canonical_terms_recover_all_evidence": set(validator["expected_evidence_ids"]) <= set(_ids(joint_hits)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=Path("artifacts/financial-challenge-wheel-run/challenge/summary.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/financial-cross-source-audit/prior_failures.json"))
    args = parser.parse_args()
    questions = {q["task_id"]: q for q in load_questions("challenge") if q["family"] == "cross_source"}
    runs = [run for run in json.loads(args.summary.read_text(encoding="utf-8"))["runs"]
            if run["baseline_name"] == "hybrid_verified" and run["task_id"] in questions]
    failed = [run for run in runs if not run["passed"]]
    assert len(runs) == 40 and len(failed) == 39
    documents = load_corpus(challenge=True)["documents"]
    cases = [_audit(run, questions[run["task_id"]], documents) for run in failed]
    misses = [row for case in cases for row in case["missed_operands"].values()]
    controls = tuple(misses[0]["diagnostic_recovery"])
    decoy_slots = Counter()
    for row in misses:
        decoy_slots.update(row["decoys_in_recorded_top5"])
    questions_by_decoy = Counter()
    for case in cases:
        questions_by_decoy.update({key for row in case["missed_operands"].values() for key in row["decoys_in_recorded_top5"]})
    counts = {
        "passed_questions": len(runs) - len(failed),
        "failed_questions": len(cases),
        "left_only": sum(set(case["missed_operands"]) == {"left"} for case in cases),
        "right_only": sum(set(case["missed_operands"]) == {"right"} for case in cases),
        "both": sum(len(case["missed_operands"]) == 2 for case in cases),
        "missed_operands": len(misses),
        "missing_canonical_metric_terms_operands": sum(bool(row["missing_canonical_metric_terms"]) for row in misses),
        "raw_ranks_1_to_5": sum(row["raw_rank"] <= 5 for row in misses),
        "raw_ranks_6_to_10": sum(6 <= row["raw_rank"] <= 10 for row in misses),
        "raw_ranks_11_to_20": sum(11 <= row["raw_rank"] <= 20 for row in misses),
        "raw_ranks_21_plus": sum(row["raw_rank"] >= 21 for row in misses),
        "raw_rank_median": median(row["raw_rank"] for row in misses),
        "recorded_slots_across_missed_operands": dict(decoy_slots),
        "questions_with_each_slot_category": dict(questions_by_decoy),
        "joint_canonical_terms_recover_all_evidence_questions": sum(
            case["joint_canonical_terms_recover_all_evidence"] for case in cases
        ),
        "recovered_operands_by_control": {key: sum(row["diagnostic_recovery"][key] for row in misses) for key in controls},
        "any_operand_recovered_questions_by_control": {
            key: sum(any(row["diagnostic_recovery"][key] for row in case["missed_operands"].values()) for case in cases)
            for key in controls
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "summary": counts,
        "interpretation": (
            "Controls are retrospective, nonexclusive, and never used at runtime. "
            "The canonical-term control uses the reference metric to measure alias sensitivity. "
            "Decoy removal retains the original scores, avoiding corpus-statistics changes. "
            "Exact operand scope is an oracle on issuer, period, and source, and reruns allocation for one side only. "
            "Recorded slot counts are per missed operand, so a two-sided miss contributes its five slots twice. "
            "Each slot is classified once, preferring other required operand, then issuer, period, adjusted metric, source, and other metric. "
            "Rank is raw global hybrid score order before modality reservation, so misses with rank <= 5 are allocation losses."
        ),
        "cases": cases,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
