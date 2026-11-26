"""Export the pinned A1 task set and label-independent raw retrieval fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


PACKAGE_DATA = (
    Path(__file__).resolve().parents[1]
    / "src" / "sandboxed_agent_eval_harness" / "benchmarks" / "financial_evidence"
)
PUBLIC_FIELDS = ("family", "question", "claim_text", "company_tickers", "fiscal_periods", "allowed_source_types")
DECK = Path("tests/fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf")


def _normalize_source_metadata(document: dict) -> dict:
    """Use explicit source scope and exclude inconsistent numeric metadata."""
    if (document["chunk_type"] == "deck_chart"
            and document["section_or_page"].partition(" / ")[2] == "Data Center Revenue"):
        document["metric"] = "data_center_revenue"
    if document["section_or_page"] == "dei:EntityCommonStockSharesOutstanding":
        document.update(metric="shares_outstanding", numeric_value=None, unit=None, currency=None)
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a1_checkout", type=Path)
    args = parser.parse_args()
    checkout = args.a1_checkout.resolve()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "src", str(DECK)], cwd=checkout, text=True,
    )
    if status:
        parser.error("A1 source or deck fixture has local changes. Export from a clean revision.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(checkout / "src"))
    from financial_evidence_engine.evaluation import build_seed_task_set
    from financial_evidence_engine.retrieval import build_raw_financial_corpus

    task_set = build_seed_task_set()
    questions = {}
    labels = {}
    for task in task_set.tasks:
        payload = task.to_dict()
        questions[task.task_id] = {key: payload[key] for key in ("task_id", *PUBLIC_FIELDS)}
        labels[task.task_id] = {key: value for key, value in payload.items() if key not in PUBLIC_FIELDS}

    upstream = {"repository": "https://github.com/OrrinChen/multimodal_FEE", "commit": commit}
    dataset = {
        "task_set_id": task_set.task_set_id,
        "version": task_set.version,
        "provenance": {**upstream, "source": "src/financial_evidence_engine/evaluation/gold_builder.py"},
    }
    corpus = build_raw_financial_corpus(
        SimpleNamespace(tasks=[SimpleNamespace(company_tickers=task["company_tickers"]) for task in questions.values()]),
        deck_fixture_path=checkout / DECK,
    )
    documents = []
    for chunk in corpus.chunks:
        document = dict(chunk.to_dict())
        provenance = document.pop("provenance")
        documents.append(_normalize_source_metadata({
            "evidence_id": document.pop("chunk_id"),
            "modality": chunk.modality,
            "metric": document.pop("normalized_metric"),
            **document,
            **provenance,
        }))
    canonical_documents = json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    corpus_hash = hashlib.sha256(canonical_documents.encode("utf-8")).hexdigest()
    exports = {
        "a1_questions.json": {**dataset, "tasks": questions},
        "a1_labels.json": {**dataset, "tasks": labels},
        "a1_raw_corpus.json": {
            "version": f"a1-raw-{corpus_hash}",
            "provenance": {
                **upstream,
                "source": "src/financial_evidence_engine/retrieval/raw_corpus.py",
                "deck_fixture": DECK.as_posix(),
                "normalization": "Chart title defines segment scope. The shares-outstanding fixture reports a currency unit, so its normalized value and unit are unavailable. Raw source text, IDs, hashes, and manifest are retained.",
            },
            "manifest": corpus.manifest.to_dict(),
            "documents": documents,
        },
    }
    if len(questions) != 60 or len(documents) != 482:
        raise ValueError(f"Expected 60 tasks and 482 chunks, got {len(questions)} tasks and {len(documents)} chunks")
    for name, payload in exports.items():
        (PACKAGE_DATA / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
