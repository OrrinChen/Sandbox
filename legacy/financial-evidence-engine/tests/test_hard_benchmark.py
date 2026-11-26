"""Synthetic hard benchmark: construction, CPU rerun, and published numbers."""

import json
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments" / "hard_benchmark" / "hard_benchmark.json"
ORIGINAL_LSA = ROOT / "experiments" / "dense_lsa" / "dense_lsa_rerank_ablation.json"


def test_hard_benchmark_is_synthetic_labeled_and_lexically_separated():
    from financial_evidence_engine.evaluation.hard_benchmark import build_hard_benchmark, provenance_record

    benchmark = build_hard_benchmark()
    provenance = provenance_record(benchmark)

    assert provenance["construction"] == "synthetic-and-labeled"
    assert provenance["real_filings_used"] is False
    assert provenance["document_count"] == 156
    assert provenance["task_count"] == 65
    assert provenance["splits"]["test"] == 47
    assert provenance["splits"]["dev"] == 18
    assert any(task.family == "margin_multihop" and len(task.gold_document_ids) == 2 for task in benchmark.tasks)
    assert any(task.expected_verdict == "insufficient" for task in benchmark.tasks)


def test_cpu_hard_benchmark_matches_the_committed_test_split():
    from financial_evidence_engine.evaluation.hard_benchmark import build_hard_benchmark, evaluate_hard_benchmark

    committed = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fresh = evaluate_hard_benchmark(build_hard_benchmark())
    for method in (
        "bm25",
        "bm25_metadata_rerank",
        "dense_lsa",
        "dense_lsa_metadata_rerank",
        "full_engine",
    ):
        assert fresh["methods"][method]["test"] == committed["methods"][method]["test"]

    recalls = [
        Decimal(committed["methods"][method]["test"]["recall_at_5"])
        for method in ("bm25", "dense_lsa", "dense_minilm", "full_engine")
    ]
    assert max(recalls) - min(recalls) >= Decimal("0.5")
    assert committed["methods"]["dense_minilm"]["status"] == "ran"
    assert "all-MiniLM-L6-v2" in committed["setup"]["dense_encoder"]
    assert "2.15.0+cpu" in committed["setup"]["dense_encoder"]


def test_readme_keeps_original_headline_and_quotes_hard_benchmark_test_split():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    committed = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL_LSA.read_text(encoding="utf-8"))

    lead, results_and_after = readme.split("## Results", 1)
    assert "## Hard benchmark" in lead
    assert "83.3%" in results_and_after
    assert "66.7%" in results_and_after
    assert "75.0%" in results_and_after
    assert "47/47" not in lead
    assert "100%" not in lead
    assert "47/47 (100%)" in results_and_after
    assert original["reported_metrics"]["bm25"]["evidence_recall_at_k"] == "0.995"
    assert original["reported_metrics"]["dense_lsa"]["evidence_recall_at_k"] == "1"
    rounded_recall = {
        "bm25": "0.159",
        "dense_lsa": "0.182",
        "dense_minilm": "0.466",
        "full_engine": "1.000",
    }
    for method, rounded in rounded_recall.items():
        assert committed["methods"][method]["test"]["recall_at_5"] not in readme or method == "full_engine"
        assert rounded in readme
    assert committed["methods"]["bm25"]["test"]["recall_at_5"] == "0.1590909090909090909090909091"
    assert "not yet run" in readme
