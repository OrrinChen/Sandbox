from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
import json
import re

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark import data, scoring
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.benchmark import FinancialBenchmarkBaseline, task_suite
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor
from sandboxed_agent_eval_harness.tools import execution


_DOLLAR_SCALES = {None: 1, "thousands": 1_000, "millions": 1_000_000}
_OUTPUT_SCALES = {"usd": 1, "usd_thousands": 1_000, "usd_millions": 1_000_000}
_DISCLOSED_AMOUNT = re.compile(r"(-?\d+(?:\.\d+)?) USD(?: (thousands|millions))?\.")


def test_challenge_artifacts_and_company_groups_are_frozen_and_disjoint():
    manifest = data.load_manifest(challenge=True)
    original = data.load_manifest()
    corpus = data.load_corpus(challenge=True)
    docs = corpus["documents"]
    original_docs = data.load_corpus()["documents"]
    questions = data.load_questions("challenge")
    issuers = set(manifest["challenge_groups"])
    pairs = manifest["company_pair_groups"]

    assert manifest["synthetic"] and corpus["version"] == manifest["dataset_version"]
    assert len(issuers) == 80 and issuers == set(pairs)
    assert Counter(pairs.values()) == dict.fromkeys(pairs.values(), 2)
    assert len(set(pairs.values())) == 40
    assert issuers.isdisjoint(original["dev_groups"] + original["test_groups"])
    assert set(pairs.values()).isdisjoint(original["company_pair_groups"].values())
    assert {doc["company_name"] for doc in docs}.isdisjoint(doc["company_name"] for doc in original_docs)
    assert {doc["company_ticker"] for doc in docs} == issuers
    assert len({doc["evidence_id"] for doc in docs}) == len(docs) == manifest["document_count"]
    assert {doc["evidence_id"] for doc in docs}.isdisjoint(doc["evidence_id"] for doc in original_docs)
    assert {doc["document_id"] for doc in docs}.isdisjoint(doc["document_id"] for doc in original_docs)
    document_issuers = defaultdict(set)
    for doc in docs:
        document_issuers[doc["document_id"]].add(doc["company_ticker"])
    assert len(document_issuers) == manifest["source_document_count"]
    assert all(len(companies) == 1 for companies in document_issuers.values())
    assert len({q["task_id"] for q in questions}) == len({q["question"] for q in questions}) == 240
    assert Counter(q["family"] for q in questions) == dict.fromkeys(manifest["families"], 40)
    assert Counter(pairs[q["company_tickers"][0]] for q in questions) == dict.fromkeys(pairs.values(), 6)

    assert sha256(data._resource("challenge_corpus").read_bytes()).hexdigest() == manifest["corpus_sha256"]
    assert set(manifest["split_sha256"]) == {"challenge_questions.json", "challenge_labels.json"}
    for filename, expected in manifest["split_sha256"].items():
        assert sha256(data._resource(filename.removesuffix(".json")).read_bytes()).hexdigest() == expected


def test_broad_challenge_scope_and_raw_reference_answers():
    questions = data.load_questions("challenge")
    docs = data.load_corpus(challenge=True)["documents"]
    labels = scoring.load_labels("challenge")
    assert {q["task_id"] for q in questions} == set(labels)

    amounts = {}
    for doc in docs:
        matches = _DISCLOSED_AMOUNT.findall(doc["text"])
        assert len(matches) == 1, doc["evidence_id"]
        value, unit = matches[0]
        assert doc["unit"] == (unit or "USD") and doc["currency"] == "USD"
        assert Fraction(value) == Fraction(doc["numeric_value"])
        amounts[doc["evidence_id"]] = Fraction(value) * _DOLLAR_SCALES[unit or None]

    scopes = {}
    lookup_verdicts = defaultdict(set)
    target_positions = Counter()
    for q in questions:
        assert len(set(q["company_tickers"])) == 2 and len(set(q["fiscal_periods"])) == 3
        assert len(set(q["allowed_source_types"])) == 4
        group = tuple(q["company_tickers"])
        scope = (tuple(q["fiscal_periods"]), tuple(q["allowed_source_types"]))
        assert scopes.setdefault(group, scope) == scope
        candidates = [
            doc for doc in docs if doc["company_ticker"] in group
            and doc["fiscal_period"] in scope[0] and doc["source_type"] in scope[1]
        ]
        assert len(candidates) > 5
        target_positions[group.index(q["operands"][0]["ticker"])] += 1
        matches = [
            [
                doc for doc in candidates
                if doc["company_ticker"] == operand["ticker"] and doc["fiscal_period"] == operand["period"]
                and doc["metric"] == operand["metric"] and doc["source_type"] == operand.get("source_type", doc["source_type"])
            ]
            for operand in q["operands"]
        ]
        values = [{amounts[doc["evidence_id"]] for doc in rows} for rows in matches]
        label = labels[q["task_id"]]
        if not all(values):
            expected_verdict, expected_answer, evidence = "insufficient", None, []
        else:
            evidence = [doc for rows in matches for doc in rows]
            if any(len(group) > 1 for group in values):
                expected_verdict, expected_answer = "conflict", None
            else:
                expected_verdict = "answer"
                result = next(iter(values[0]))
                if q["operation"] == "difference":
                    result -= next(iter(values[1]))
                expected_answer = result / _OUTPUT_SCALES[q["unit"]]
        assert label["verdict"] == expected_verdict and label["unit"] == q["unit"]
        assert (Fraction(label["answer_value"]) if label["answer_value"] is not None else None) == expected_answer
        assert {doc["evidence_id"] for doc in evidence} == set(label["evidence_ids"])
        assert len(evidence) <= 5
        answer = {"verdict": expected_verdict, "answer_value": label["answer_value"], "unit": q["unit"],
                  "citations": [doc["evidence_id"] for doc in evidence]}
        assert scoring.score_answer(label, json.dumps(answer), evidence, 5).passed
        assert not scoring.score_answer(label, json.dumps({**answer, "answer_value": "-999"}), evidence, 5).passed
        assert not scoring.score_answer(label, json.dumps(answer), evidence, 6).passed
        if evidence:
            assert not scoring.score_answer(label, json.dumps(answer), evidence[:-1], 5).passed
        if q["operation"] == "lookup":
            lookup_verdicts[(len(group), len(scope[0]), scope[1])].add(expected_verdict)
    assert target_positions == {0: 120, 1: 120}
    assert len(lookup_verdicts) == 1
    assert next(iter(lookup_verdicts.values())) == {"answer", "conflict", "insufficient"}


def test_challenge_inference_never_loads_labels_or_passes_operands_to_search(monkeypatch, tmp_path):
    original = data._resource

    def public_only(name):
        assert not name.endswith("_labels")
        return original(name)

    def inspect_search(method, query, top_k, docs, **filters):
        assert method == "hybrid" and query == task.instruction and top_k == 5
        assert set(filters) == {"tickers", "fiscal_periods", "source_types"}
        assert docs == data.load_corpus(challenge=True)["documents"]
        return []

    monkeypatch.setattr(data, "_resource", public_only)
    monkeypatch.setattr(execution, "search_full", inspect_search)
    scoring.load_labels.cache_clear()
    data.load_manifest.cache_clear()
    data.load_questions.cache_clear()
    data.load_corpus.cache_clear()
    task = task_suite("challenge").tasks[0]
    assert not task.hidden_expected_state
    assert not {"family", "task_id", "evidence_ids", "verdict", "answer_value"} & task.initial_state["question"].keys()
    baseline = FinancialBenchmarkBaseline("hybrid_verified")
    plan = baseline.run(task)
    call = plan.tool_calls[0]
    assert call.arguments["corpus"] == "financial-challenge"
    executor = FixtureToolExecutor()
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")
    result = executor.execute(call.tool_name, call.arguments, sandbox)
    event = TraceEvent("result", "tool_result", 0, {"tool_name": call.tool_name, "result": result})
    assert json.loads(baseline.finalize(task, plan, [event]).final_answer)["verdict"] == "insufficient"
