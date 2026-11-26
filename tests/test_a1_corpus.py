import hashlib
import json

from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_data import load_full_corpus


def test_exported_a1_corpus_keeps_scope_and_versions_normalized_metadata():
    corpus = load_full_corpus()
    documents = corpus["documents"]
    (chart,) = [document for document in documents if document["chunk_type"] == "deck_chart"]
    assert "Data Center Revenue" in chart["text"]
    assert chart["metric"] == "data_center_revenue"
    assert chart["evidence_id"].endswith(chart["chunk_hash"][:12])

    shares = [document for document in documents if document["section_or_page"] == "dei:EntityCommonStockSharesOutstanding"]
    assert len(shares) == 10
    for document in shares:
        assert document["metric"] == "shares_outstanding"
        assert all(document[field] is None for field in ("numeric_value", "unit", "currency"))
        assert "USD" in document["text"]

    canonical = json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert corpus["version"] == f"a1-raw-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
    assert corpus["version"] != f"a1-raw-{corpus['manifest']['version_hash']}"
