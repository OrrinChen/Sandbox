"""CPU dense retrieval baseline and rerank ablation."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LSA_JSON = ROOT / "experiments" / "dense_lsa" / "dense_lsa_rerank_ablation.json"
LSA_MARKDOWN = ROOT / "reports" / "dense_lsa" / "dense_lsa_rerank_ablation.md"
MINILM_JSON = ROOT / "experiments" / "dense_sentence_transformer" / "dense_sentence_transformer_rerank_ablation.json"


def test_lsa_provider_projects_queries_into_the_fitted_space():
    from financial_evidence_engine.retrieval.dense_lsa import CorpusTfidfSvdEmbeddingProvider, _cosine

    provider = CorpusTfidfSvdEmbeddingProvider(
        dimension=4,
        max_features=50,
        min_df=1,
        subspace_iterations=8,
    )
    documents = (
        "apple revenue fiscal year 2024 billion filing",
        "apple revenue fiscal year 2022 billion filing",
        "microsoft cloud margin transcript commentary",
        "alphabet advertising traffic acquisition cost",
        "amazon retail operating cash flow",
        "nvidia data center revenue outlook",
    )
    vectors = provider.embed_texts(documents)
    query = provider.embed_texts(("apple revenue fiscal year 2024 filing",))[0]

    assert provider.fitted_dimension == 4
    assert len(query) == len(vectors[0])
    assert _cosine(query, vectors[0]) > _cosine(query, vectors[2])


def test_committed_lsa_artifact_matches_a_fresh_run():
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval.dense_lsa import (
        load_dense_lsa_config,
        render_ablation_markdown,
        run_dense_lsa_experiment,
    )

    committed = json.loads(LSA_JSON.read_text(encoding="utf-8"))
    config = load_dense_lsa_config(ROOT / "configs" / "dense_lsa.yaml")
    result = run_dense_lsa_experiment(build_seed_task_set(), config, command=committed["command"])

    assert result.to_dict() == committed
    assert LSA_MARKDOWN.read_text(encoding="utf-8") == render_ablation_markdown(result)
    assert committed["setup"]["task_count"] == 60
    assert committed["setup"]["corpus_document_count"] == 320
    assert committed["reported_metrics"]["bm25"]["evidence_recall_at_k"] == "0.995"
    assert committed["reported_metrics"]["dense_lsa"]["evidence_recall_at_k"] == "1"
    assert committed["reported_metrics"]["dense_proxy"]["evidence_recall_at_k"] == "0.92"


def test_minilm_artifact_records_the_cpu_run_without_replacing_verdict_numbers():
    payload = json.loads(MINILM_JSON.read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert payload["status"] == "ran"
    assert payload["setup"]["device"] == "cpu"
    assert payload["setup"]["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert payload["setup"]["sentence_transformers_version"] == "6.2.0"
    assert payload["setup"]["torch_version"] == "2.15.0+cpu"
    assert payload["setup"]["task_count"] == 60
    assert payload["setup"]["corpus_document_count"] == 320
    assert payload["reported_metrics"]["dense_minilm"]["evidence_recall_at_k"] == "0.96"
    assert payload["reported_metrics"]["dense_minilm_metadata_rerank"]["evidence_recall_at_k"] == "1"
    assert "0.96" in readme
    assert "0.04" in readme
    assert "83.3%" in readme
    assert "not outputs of this run" in payload["metrics_omitted_note"]


def test_disabled_minilm_script_keeps_the_recorded_artifact():
    before = MINILM_JSON.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/run_sentence_transformer_baseline.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
    )

    assert result.returncode == 0
    assert "status=not_yet_run" in result.stdout
    assert "kept_existing_artifact" in result.stdout
    assert MINILM_JSON.read_text(encoding="utf-8") == before
