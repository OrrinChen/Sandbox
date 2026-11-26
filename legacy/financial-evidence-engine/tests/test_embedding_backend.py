from decimal import Decimal

import pytest


def test_deterministic_embedding_provider_builds_cached_index_with_manifest(tmp_path):
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import (
        DeterministicTokenEmbeddingProvider,
        EmbeddingIndex,
        build_retrieval_corpus,
    )

    corpus = build_retrieval_corpus(build_seed_task_set())
    provider = DeterministicTokenEmbeddingProvider(dimension=24)

    index = EmbeddingIndex.build(corpus, provider)
    manifest_path = index.save(tmp_path)
    loaded = EmbeddingIndex.load(tmp_path)

    assert manifest_path.name == "embedding_manifest.json"
    assert (tmp_path / "embeddings.json").is_file()
    assert index.manifest.provider_id == "deterministic-token-v1"
    assert index.manifest.backend_kind == "proxy"
    assert index.manifest.dimension == 24
    assert index.manifest.vector_count == len(corpus.documents)
    assert index.manifest.version_hash == loaded.manifest.version_hash
    assert loaded.document_ids == index.document_ids
    assert loaded.vectors == index.vectors


def test_optional_embedding_provider_gracefully_skips_when_disabled():
    from financial_evidence_engine.retrieval import EmbeddingBackendUnavailable, LocalSentenceTransformerProvider

    provider = LocalSentenceTransformerProvider(model_name="sentence-transformers/all-MiniLM-L6-v2")

    assert provider.provider_id == "local-sentence-transformer:sentence-transformers/all-MiniLM-L6-v2"
    assert not provider.is_available()
    assert "disabled" in provider.unavailable_reason().lower()
    with pytest.raises(EmbeddingBackendUnavailable):
        provider.embed_texts(("financial evidence",))


def test_metadata_reranker_boosts_company_period_and_metric_matches():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import MetadataBoostReranker, RetrievalCorpusDocument, RetrievalResult

    task = build_seed_task_set().tasks[0]
    wrong = RetrievalCorpusDocument(
        document_id="wrong",
        task_id=task.task_id,
        evidence_key="wrong",
        source_type="transcript",
        modality="transcript",
        company_ticker="MSFT",
        fiscal_period="FY2022",
        role="wrong company and period",
        text="Wrong company revenue narrative.",
        metric="revenue",
    )
    right = RetrievalCorpusDocument(
        document_id="right",
        task_id=task.task_id,
        evidence_key="right",
        source_type="sec_xbrl_companyfacts",
        modality="xbrl",
        company_ticker="AAPL",
        fiscal_period="FY2024",
        role="reported revenue fact",
        text="Apple FY2024 revenue fact.",
        metric="revenue",
    )
    results = (
        RetrievalResult(document=wrong, score=Decimal("0.90")),
        RetrievalResult(document=right, score=Decimal("0.70")),
    )

    reranked = MetadataBoostReranker().rerank(task, results)

    assert reranked[0].document.document_id == "right"
    assert reranked[0].score > reranked[1].score


def test_embedding_retrieval_report_separates_proxy_and_optional_real_methods():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import (
        DeterministicTokenEmbeddingProvider,
        run_embedding_retrieval_evaluation,
    )

    task_set = build_seed_task_set()
    proxy_result = run_embedding_retrieval_evaluation(task_set)

    assert set(proxy_result.reports) == {"bm25", "dense_proxy", "hybrid_proxy", "graph", "full_engine"}
    assert set(proxy_result.skipped_methods) == {"dense_real", "hybrid_real"}
    assert proxy_result.embedding_index_manifest.provider_id == "deterministic-token-v1"
    assert proxy_result.to_dict()["reports"]["dense_proxy"]["method"] == "dense_proxy"
    assert "no real embedding provider" in proxy_result.skipped_methods["dense_real"].lower()

    real_provider = DeterministicTokenEmbeddingProvider(
        provider_id="local-test-real",
        backend_kind="real",
        dimension=24,
    )
    real_result = run_embedding_retrieval_evaluation(task_set, real_embedding_provider=real_provider)

    assert {"dense_real", "hybrid_real"}.issubset(real_result.reports)
    assert real_result.skipped_methods == {}
    assert real_result.method_notes["dense_real"].startswith("Optional real embedding provider")
