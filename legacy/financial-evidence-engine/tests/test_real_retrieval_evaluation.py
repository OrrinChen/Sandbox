from decimal import Decimal


def test_real_retrieval_corpus_contains_gold_documents_and_distractors():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import build_retrieval_corpus

    task_set = build_seed_task_set()
    corpus = build_retrieval_corpus(task_set)

    expected_gold_count = sum(len(task.expected_evidence) for task in task_set.tasks)

    assert len(corpus.documents) > expected_gold_count
    assert any(document.is_distractor for document in corpus.documents)
    assert any(document.source_type == "investor_deck" for document in corpus.documents)
    assert all(document.text for document in corpus.documents)
    assert all(document.company_ticker for document in corpus.documents)
    assert all(document.fiscal_period for document in corpus.documents)


def test_bm25_retriever_returns_ranked_documents_from_the_corpus():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import BM25EvidenceRetriever, build_retrieval_corpus

    task_set = build_seed_task_set()
    task = task_set.tasks[0]
    retriever = BM25EvidenceRetriever(build_retrieval_corpus(task_set))

    results = retriever.retrieve(task, top_k=5)

    assert results
    assert results[0].score >= results[-1].score
    assert all(result.document.evidence_key for result in results)
    assert all(result.document.text for result in results)


def test_real_retrieval_evaluation_runs_methods_and_surfaces_failures():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import run_real_retrieval_evaluation

    result = run_real_retrieval_evaluation(build_seed_task_set())

    assert result.corpus_mode == "benchmark"
    assert set(result.reports) == {
        "bm25_real",
        "dense_real",
        "hybrid_real",
        "graph_real",
        "full_engine_real",
    }
    assert result.task_count == 60
    assert result.corpus_document_count > 0
    assert result.reports["full_engine_real"].metrics["verdict_accuracy"] < Decimal("1")
    assert (
        result.reports["full_engine_real"].metrics["citation_exactness"]
        >= result.reports["bm25_real"].metrics["citation_exactness"]
    )
    assert (
        result.reports["full_engine_real"].metrics["numeric_correctness"]
        > result.reports["bm25_real"].metrics["numeric_correctness"]
    )
    assert result.failure_cases
    assert {
        "period_confusion",
        "citation_mismatch",
        "numeric_validation_gap",
        "chart_extraction_gap",
    }.intersection({failure.category for failure in result.failure_cases})


def test_real_retrieval_report_serializes_retrieved_evidence_and_failure_cases():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import run_real_retrieval_evaluation

    payload = run_real_retrieval_evaluation(build_seed_task_set()).to_dict()

    assert payload["task_count"] == 60
    assert payload["corpus_mode"] == "benchmark"
    assert payload["raw_chunk_count"] == 0
    assert payload["corpus_document_count"] > 60
    assert payload["reports"]["bm25_real"]["method"] == "bm25_real"
    assert payload["runs"]["bm25_real"]["predictions"][0]["retrieved_evidence"]
    assert payload["failure_cases"]
    assert payload["method_notes"]["dense_real"].startswith("Deterministic token-vector")
