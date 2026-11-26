"""Export the frozen cross-source reader inputs and score recorded LLM responses."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.data import load_questions
from sandboxed_agent_eval_harness.tracing import TraceReplay


SPLIT = "cross_source_test"
METHOD = "hybrid_split_verified"
RULE_READER = f"{METHOD}_text_only"
MODEL = "Codex conversation subagents (inherited model)"
PROMPT = (
    "Answer each financial question independently using only that row's question and the supplied verbatim excerpts, "
    "in their given order. The excerpt letters are the citation handles. Use the excerpts that match the requested "
    "issuer, period, source, and measure. Respect any qualifier or reporting basis in the question and the excerpt. "
    "For a difference, use the order requested and convert both amounts to the requested unit before subtracting. "
    "Use exact decimal arithmetic. If either required operand lacks evidence, use verdict \"insufficient\", a null "
    "answer_value, and no citations. If relevant excerpts give incompatible values for the same required operand "
    "and the question does not resolve the discrepancy, use verdict \"conflict\", a null answer_value, and cite the "
    "conflicting excerpts. Otherwise use verdict \"answer\", give answer_value as an exact decimal string without a "
    "separator, and cite only the excerpt letters used. For every verdict, set unit to \"usd\", \"usd_thousands\", "
    "or \"usd_millions\" as requested. Output a JSON array with one object per row, with fields row, verdict, "
    "answer_value, unit, citations. Do not use external sources or any other row's evidence.\n"
)


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _single(trace: TraceReplay, event_type: str) -> dict:
    (event,) = trace.events_by_type(event_type)
    return event.payload


def _traces(archive: Path, arm: str, questions: dict) -> dict:
    traces = {}
    for path in sorted((archive / "traces").glob(f"{arm}-*.jsonl")):
        trace = TraceReplay.from_jsonl(path)
        task = trace.metadata["task_id"]
        if (task in traces or trace.metadata["agent_id"] != arm or trace.metadata["benchmark_split"] != SPLIT
                or _single(trace, "user_message")["content"] != questions[task]):
            raise ValueError(f"Trace does not match the frozen question and method: {path}")
        traces[task] = (path, trace)
    if traces.keys() != questions.keys() or len(traces) != 80:
        raise ValueError(f"Expected exactly 80 archived traces for {arm}")
    return traces


def _cases(archive: Path) -> list[tuple[dict, dict, dict, TraceReplay]]:
    questions = {q["task_id"]: q["question"] for q in load_questions(SPLIT)}
    structured = _traces(archive, METHOD, questions)
    rule = _traces(archive, RULE_READER, questions)
    cases = []
    for row, (task, (structured_path, trace)) in enumerate(structured.items(), 1):
        rule_path, rule_trace = rule[task]
        call = _single(trace, "tool_call")
        result_event = _single(trace, "tool_result")
        result = result_event["result"]
        hits = result["hits"]
        if (call != _single(rule_trace, "tool_call") or result_event != _single(rule_trace, "tool_result")
                or call["tool_name"] != result_event["tool_name"] or call["tool_name"] != "rag.search"
                or call["arguments"]["top_k"] != 5 or result["top_k"] != 5 or result["method"] != "hybrid_split"
                or len(hits) > 5 or len({hit["evidence_id"] for hit in hits}) != len(hits)):
            raise ValueError(f"Archived ordered top-five calls or results differ for {task}")
        references = list(zip("ABCDE", hits))
        reader_input = {"row": row, "question": questions[task], "evidence": [
            {"ref": letter, "text": hit["text"]} for letter, hit in references
        ]}
        manifest_entry = {"row": row, "task_id": task,
                          "citations": {letter: hit["evidence_id"] for letter, hit in references},
                          "structured_trace": str(structured_path), "rule_trace": str(rule_path),
                          "tool_result_sha256": sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()}
        cases.append((reader_input, manifest_entry, result, rule_trace))
    return cases


def _batches(cases):
    return (cases[:27], cases[27:54], cases[54:])


def _prepare(output: Path, cases) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "reader_prompt.txt").write_text(PROMPT, encoding="utf-8")
    for index, batch in enumerate(_batches(cases), 1):
        _write(output / f"inputs-{index}.json", [case[0] for case in batch])
    _write(output / "scoring_manifest.json", [case[1] for case in cases])


def _load_responses(output: Path, cases) -> tuple[dict, dict]:
    prompt = output / "reader_prompt.txt"
    if prompt.read_text(encoding="utf-8") != PROMPT:
        raise ValueError("Reader prompt differs from the frozen prompt")
    hashes = {prompt.name: sha256(prompt.read_bytes()).hexdigest()}
    responses = {}
    for index, batch in enumerate(_batches(cases), 1):
        inputs = output / f"inputs-{index}.json"
        expected = [case[0] for case in batch]
        if _read(inputs) != expected:
            raise ValueError(f"Reader inputs differ from the archived top five: {inputs}")
        response = output / f"responses-{index}.json"
        rows = _read(response)
        row_ids = {row["row"] for row in rows}
        if len(rows) != len(row_ids) or row_ids != {item["row"] for item in expected}:
            raise ValueError(f"Expected one response per assigned question: {response}")
        responses.update((row["row"], row) for row in rows)
        for path in (inputs, response):
            hashes[path.name] = sha256(path.read_bytes()).hexdigest()
    return responses, hashes


def _answer_payload(response: dict, references: dict) -> str:
    answer = {key: value for key, value in response.items() if key != "row"}
    if isinstance(answer.get("citations"), list):
        answer["citations"] = [references.get(citation, f"unrecognized-reference:{citation}")
                               if isinstance(citation, str) else citation for citation in answer["citations"]]
    return json.dumps(answer, ensure_ascii=False, sort_keys=True)


def _metrics(result) -> dict[str, bool]:
    details = result.details
    return {"strict_pass": result.passed, "citation_support": details["citation_correct"],
            "answer_correct": all(details[key] for key in ("verdict_correct", "numeric_correct", "unit_correct"))}


def _compare(rows: list[dict], metric: str) -> dict:
    counts = Counter((row["rule_metrics"][metric], row["llm_metrics"][metric]) for row in rows)
    return {"rule_reader_passed": counts[True, True] + counts[True, False],
            "llm_reader_passed": counts[True, True] + counts[False, True],
            "llm_only": counts[False, True], "rule_only": counts[True, False],
            "both_passed": counts[True, True], "both_failed": counts[False, False]}


def _score(output: Path, cases) -> None:
    from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score

    responses, hashes = _load_responses(output, cases)
    if _read(output / "scoring_manifest.json") != [case[1] for case in cases]:
        raise ValueError("Scoring manifest differs from the archived retrieval")
    rows = []
    for _, manifest, result, rule_trace in cases:
        response = responses[manifest["row"]]
        task = manifest["task_id"]
        rule_answer = _single(rule_trace, "final_answer")["content"]
        rule_score = score(task, SPLIT, rule_answer, result)
        if rule_score.to_dict() != _single(rule_trace, "validator_result"):
            raise ValueError(f"Current strict scorer differs from the archived rule score for {task}")
        llm_score = score(task, SPLIT, _answer_payload(response, manifest["citations"]), result)
        rows.append({**manifest, "rule_answer": json.loads(rule_answer), "llm_response": response,
                     "rule_metrics": _metrics(rule_score), "llm_metrics": _metrics(llm_score),
                     "rule_score": rule_score.to_dict(), "llm_score": llm_score.to_dict()})

    evidence_complete = [row for row in rows if not row["rule_score"]["details"]["missing_evidence_ids"]]
    rule_abstentions = [row for row in evidence_complete if not row["rule_metrics"]["strict_pass"]
                        and row["rule_answer"]["verdict"] == "insufficient"]
    if len(evidence_complete) != 71 or len(rule_abstentions) != 51:
        raise ValueError("Archived evidence and abstention counts differ from the frozen experiment")
    report = {"experiment": "recorded_llm_reader_vs_rule_reader", "split": SPLIT, "retrieval_variant": METHOD,
              "llm_reader": MODEL, "mode": "recorded", "prompt_version": "cross-source-llm-reader-v1",
              "task_count": len(rows), "top_k": 5, "identical_retrieval_pair_count": len(rows),
              "evidence_complete_count": len(evidence_complete), "input_response_sha256": hashes,
              "paired_metrics": {metric: _compare(rows, metric) for metric in rows[0]["rule_metrics"]},
              "rule_abstentions_with_complete_evidence": {"count": len(rule_abstentions),
                  "llm_strict_passed": sum(row["llm_metrics"]["strict_pass"] for row in rule_abstentions)},
              "rows": rows}
    path = output / "comparison_report.json"
    _write(path, report)
    print(f"Scored {len(rows)} pairs: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "score"))
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = _cases(args.archive)
    if args.action == "prepare":
        _prepare(args.output, cases)
    else:
        _score(args.output, cases)


if __name__ == "__main__":
    main()
