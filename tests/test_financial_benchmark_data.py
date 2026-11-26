from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark import data, scoring
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.benchmark import FinancialBenchmarkBaseline, task_suite
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor


_SCALES = {"USD": 1, "millions": 10**6, "thousands": 10**3}
_OUTPUT = {"usd": 1, "usd_millions": 10**6, "usd_thousands": 10**3}


@pytest.mark.parametrize("split,count", [("pilot", 24), ("dev", 120), ("test", 480)])
def test_frozen_questions_and_references_against_corpus(split, count):
    manifest = data.load_manifest()
    questions = data.load_questions(split)
    labels = scoring.load_labels(split)
    corpus = data.load_corpus()["documents"]
    by_id = {row["evidence_id"]: row for row in corpus}
    assert len(by_id) == len(corpus)
    assert len(questions) == count
    assert len({q["question"] for q in questions}) == count
    assert Counter(q["family"] for q in questions) == {family: count // 6 for family in manifest["families"]}
    assert set(manifest["dev_groups"]).isdisjoint(manifest["test_groups"])
    groups = set(manifest["test_groups" if split == "test" else "dev_groups"])
    assert len({q["company_tickers"][0] for q in questions}) == count // 6
    document_groups = {}
    for row in corpus:
        assert document_groups.setdefault(row["document_id"], row["company_ticker"]) == row["company_ticker"]
        unit = {"USD": "USD", "millions": "USD millions", "thousands": "USD thousands"}[row["unit"]]
        assert f"{row['numeric_value']} {unit}" in row["text"]
    assert {q["task_id"] for q in questions} == set(labels) or split == "pilot"

    for question in questions:
        assert set(question["company_tickers"]) <= groups
        label = labels[question["task_id"]]
        cited = [by_id[evidence_id] for evidence_id in label["evidence_ids"]]
        assert len(cited) <= 5
        assert all(row["company_ticker"] in groups for row in cited)
        assert label["unit"] == question["unit"]
        candidates = [
            [row for row in corpus if _matches(row, operand, question)]
            for operand in question["operands"]
        ]
        if label["verdict"] == "insufficient":
            assert not all(candidates)
            assert label["answer_value"] is None and not cited
        elif label["verdict"] == "conflict":
            assert len(candidates) == 1 and len(cited) == 2
            assert set(label["evidence_ids"]) == {r["evidence_id"] for r in candidates[0]}
            assert _usd(cited[0]) != _usd(cited[1])
            assert label["answer_value"] is None
        else:
            assert label["verdict"] == "answer"
            assert all(len(rows) == 1 for rows in candidates)
            operands = [rows[0] for rows in candidates]
            assert set(label["evidence_ids"]) == {row["evidence_id"] for row in operands}
            expected = _usd(operands[0]) - (_usd(operands[1]) if question["operation"] == "difference" else 0)
            assert Fraction(label["answer_value"]) == expected / _OUTPUT[question["unit"]]
        answer = json.dumps({**label, "citations": label["evidence_ids"]})
        assert scoring.score_answer(label, answer, cited, 5).passed
        bad_answer = json.dumps({**label, "answer_value": "-999", "citations": label["evidence_ids"]})
        assert not scoring.score_answer(label, bad_answer, cited, 5).passed
        assert not scoring.score_answer(label, answer, cited, 6).passed
        if cited:
            assert not scoring.score_answer(label, answer, cited[:-1], 5).passed


def _matches(row, operand, question):
    return (
        row["company_ticker"] == operand["ticker"] and row["fiscal_period"] == operand["period"]
        and row["metric"] == operand["metric"] and row["source_type"] in question["allowed_source_types"]
        and row["source_type"] == operand.get("source_type", row["source_type"])
        and row.get("numeric_value") is not None and row.get("currency") == "USD" and row.get("unit") in _SCALES
    )


def _usd(row):
    return Fraction(row["numeric_value"]) * _SCALES[row["unit"]]


def test_frozen_file_digests():
    manifest = data.load_manifest()
    for filename, expected in manifest["split_sha256"].items():
        assert sha256(data._resource(filename.removesuffix(".json")).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize(("method", "split"), [
    ("full_engine", "pilot"), ("hybrid_verified", "pilot"), ("hybrid_split_verified", "cross_source_dev"),
])
def test_label_files_never_open_during_inference(monkeypatch, tmp_path, method, split):
    original = data._resource

    def public_only(name):
        assert not name.endswith("_labels")
        return original(name)

    monkeypatch.setattr(data, "_resource", public_only)
    scoring.load_labels.cache_clear()
    data.load_questions.cache_clear()
    data.load_corpus.cache_clear()
    task = task_suite(split).tasks[0]
    assert not task.hidden_expected_state
    assert not {"family", "task_id", "evidence_ids", "verdict"} & task.initial_state["question"].keys()
    baseline = FinancialBenchmarkBaseline(method)
    plan = baseline.run(task)
    call = plan.tool_calls[0]
    executor = FixtureToolExecutor()
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")
    hits = executor.execute(call.tool_name, call.arguments, sandbox)
    assert hits["top_k"] == 5 and len(hits["hits"]) <= 5
    if method == "hybrid_split_verified":
        assert call.arguments["query"] == task.instruction
        assert set(call.arguments) == {"query", "top_k", "method", "corpus", "tickers", "fiscal_periods", "source_types"}
        assert len(hits["subqueries"]) == 2
    event = TraceEvent("result", "tool_result", 0, {"tool_name": call.tool_name, "result": hits})
    assert json.loads(baseline.finalize(task, plan, [event]).final_answer)["verdict"] in {"answer", "insufficient", "conflict"}
