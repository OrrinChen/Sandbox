from pathlib import Path


FIXTURE_DECK = Path("tests/fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf")


def test_raw_corpus_builder_indexes_raw_financial_document_chunks():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import build_raw_financial_corpus, build_retrieval_corpus

    task_set = build_seed_task_set()
    benchmark_corpus = build_retrieval_corpus(task_set)
    raw_corpus = build_raw_financial_corpus(task_set, deck_fixture_path=FIXTURE_DECK)

    assert raw_corpus.manifest.corpus_mode == "raw"
    assert raw_corpus.manifest.chunk_index.chunk_count == len(raw_corpus.chunks)
    assert len(raw_corpus.chunks) > len(benchmark_corpus.documents)

    sec_paragraph_chunks = [
        chunk for chunk in raw_corpus.chunks if chunk.chunk_type == "sec_filing_paragraph"
    ]
    assert len({chunk.provenance.company_ticker for chunk in sec_paragraph_chunks}) >= 3
    assert any(chunk.chunk_type == "transcript_turn" for chunk in raw_corpus.chunks)
    assert any(chunk.chunk_type == "xbrl_fact" for chunk in raw_corpus.chunks)
    assert any(chunk.chunk_type == "deck_page" for chunk in raw_corpus.chunks)
    assert any(chunk.chunk_type == "deck_chart" for chunk in raw_corpus.chunks)

    assert all(chunk.chunk_hash for chunk in raw_corpus.chunks)
    assert all(chunk.provenance.document_id for chunk in raw_corpus.chunks)
    assert all(chunk.provenance.source_span_start < chunk.provenance.source_span_end for chunk in raw_corpus.chunks)
    assert raw_corpus.manifest.chunk_index.source_type_counts["sec_filing"] >= len(sec_paragraph_chunks)
    assert raw_corpus.manifest.chunk_index.source_type_counts["transcript"] > 0
    assert raw_corpus.manifest.chunk_index.source_type_counts["investor_deck"] > 0


def test_raw_corpus_adapts_to_existing_retrieval_corpus_interface():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import BM25EvidenceRetriever, build_raw_financial_corpus

    task_set = build_seed_task_set()
    raw_corpus = build_raw_financial_corpus(task_set, deck_fixture_path=FIXTURE_DECK)
    retrieval_corpus = raw_corpus.to_retrieval_corpus()

    assert len(retrieval_corpus.documents) == len(raw_corpus.chunks)
    assert any(document.source_type == "sec_filing" and document.modality == "text" for document in retrieval_corpus.documents)
    assert any(document.source_type == "transcript" and document.modality == "transcript" for document in retrieval_corpus.documents)
    assert any(document.source_type == "sec_xbrl_companyfacts" and document.modality == "xbrl" for document in retrieval_corpus.documents)
    assert any(document.source_type == "investor_deck" and document.modality == "chart" for document in retrieval_corpus.documents)

    results = BM25EvidenceRetriever(retrieval_corpus).retrieve(task_set.tasks[0], top_k=5)

    assert results
    assert all(result.document.document_id.startswith("raw:") for result in results)


def test_real_retrieval_evaluation_selects_benchmark_or_raw_corpus():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import build_raw_financial_corpus, run_real_retrieval_evaluation

    task_set = build_seed_task_set()
    raw_corpus = build_raw_financial_corpus(task_set, deck_fixture_path=FIXTURE_DECK)

    benchmark_result = run_real_retrieval_evaluation(task_set, corpus_mode="benchmark")
    raw_result = run_real_retrieval_evaluation(task_set, corpus_mode="raw", raw_corpus=raw_corpus)

    assert benchmark_result.corpus_mode == "benchmark"
    assert raw_result.corpus_mode == "raw"
    assert raw_result.raw_chunk_count == len(raw_corpus.chunks)
    assert raw_result.corpus_document_count > benchmark_result.corpus_document_count
    assert set(raw_result.reports) == set(benchmark_result.reports)
    assert raw_result.to_dict()["corpus_mode"] == "raw"
