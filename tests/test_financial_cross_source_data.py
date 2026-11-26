"""Audit frozen cross-source labels independently from the data generator."""

from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
import re

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark import data, scoring


_SCALES = {None: 1, "thousands": 1_000, "millions": 1_000_000}
_OUTPUT = {"usd": 1, "usd_thousands": 1_000, "usd_millions": 1_000_000}
_RAW_AMOUNT = re.compile(r": (-?\d+(?:\.\d+)?) USD(?: (thousands|millions))?\.")


@pytest.mark.parametrize("split, count", [("cross_source_dev", 40), ("cross_source_test", 80)])
def test_cross_source_labels_and_scope_match_frozen_originals(split, count):
    manifest = data.load_manifest(split=split)
    corpus = data.load_corpus(split=split)
    documents = corpus["documents"]
    questions = data.load_questions(split)
    labels = scoring.load_labels(split)
    groups = manifest["company_pair_groups"]

    assert corpus["version"] == manifest["dataset_version"]
    assert manifest["synthetic"]
    assert len(documents) == manifest["document_count"] == count * 20
    assert len({doc["document_id"] for doc in documents}) == manifest["source_document_count"]
    assert len(questions) == len(labels) == count
    assert len({question["question"] for question in questions}) == count
    assert Counter(groups.values()) == dict.fromkeys(groups.values(), 2)
    assert len(set(groups.values())) == count // 2
    assert sha256(data._resource(split + "_corpus").read_bytes()).hexdigest() == manifest["corpus_sha256"]
    assert set(manifest["split_sha256"]) == {split + "_questions.json", split + "_labels.json"}
    for filename, expected in manifest["split_sha256"].items():
        assert sha256(data._resource(filename.removesuffix(".json")).read_bytes()).hexdigest() == expected

    amounts = {}
    document_owner = {}
    for doc in documents:
        (amount,) = _RAW_AMOUNT.finditer(doc["text"])
        assert Fraction(amount[1]) == Fraction(doc["numeric_value"])
        assert (amount[2] or "USD") == doc["unit"] and doc["currency"] == "USD"
        assert doc["evidence_id"] not in amounts
        amounts[doc["evidence_id"]] = Fraction(amount[1]) * _SCALES[amount[2]]
        assert doc["source_group"] == doc["company_ticker"]
        assert document_owner.setdefault(doc["document_id"], doc["source_group"]) == doc["source_group"]

    direction = Counter()
    for question in questions:
        tickers, periods, sources = (question[key] for key in ("company_tickers", "fiscal_periods", "allowed_source_types"))
        assert len(set(tickers)) == 2 and len(set(periods)) == 3 and len(set(sources)) == 4
        assert len({groups[ticker] for ticker in tickers}) == 1
        assert question["family"] == "cross_source" and question["operation"] == "difference"
        candidates = [
            doc for doc in documents if doc["company_ticker"] in tickers
            and doc["fiscal_period"] in periods and doc["source_type"] in sources
        ]
        assert len(candidates) == 40
        left, right = question["operands"]
        assert {left["source_type"], right["source_type"]} == {"transcript", "investor_deck"}
        direction[left["source_type"]] += 1
        hits = [_operand_document(operand, candidates) for operand in (left, right)]
        citations = [hit["evidence_id"] for hit in hits]
        difference = (amounts[citations[0]] - amounts[citations[1]]) / _OUTPUT[question["unit"]]
        label = labels[question["task_id"]]
        assert label["verdict"] == "answer" and label["unit"] == question["unit"]
        assert set(label["evidence_ids"]) == set(citations)
        assert Fraction(label["answer_value"]) == difference
        answer = {"verdict": "answer", "unit": question["unit"], "answer_value": label["answer_value"],
                  "citations": citations}
        assert scoring.score_answer(label, json.dumps(answer), hits, 5).passed
        assert not scoring.score_answer(label, json.dumps(answer), hits[1:], 5).passed
        assert not scoring.score_answer(label, json.dumps(answer), hits[:1], 5).passed
        assert not scoring.score_answer(label, json.dumps(answer), hits, 6).passed
    assert direction.keys() == {"transcript", "investor_deck"}


def test_cross_source_issuer_and_document_identities_are_disjoint():
    sets = [data.load_corpus(split=split)["documents"]
            for split in ("", "challenge", "cross_source_dev", "cross_source_test")]
    for field in ("company_ticker", "company_name", "document_id", "evidence_id"):
        previous = set()
        for documents in sets:
            identities = {doc[field] for doc in documents}
            assert previous.isdisjoint(identities), field
            previous.update(identities)


def _operand_document(operand, candidates):
    (doc,) = [
        doc for doc in candidates if doc["company_ticker"] == operand["ticker"]
        and doc["fiscal_period"] == operand["period"] and doc["metric"] == operand["metric"]
        and doc["source_type"] == operand["source_type"]
    ]
    return doc
