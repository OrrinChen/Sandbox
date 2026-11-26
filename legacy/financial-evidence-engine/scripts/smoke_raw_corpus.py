"""Smoke check for Phase 11 raw financial document corpus indexing."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.evaluation import build_seed_task_set
from financial_evidence_engine.retrieval import build_raw_financial_corpus, build_retrieval_corpus


FIXTURE_DECK = Path("tests/fixtures/investor_decks/nvda_fy2024_data_center_chart.pdf")


def main() -> None:
    task_set = build_seed_task_set()
    benchmark_corpus = build_retrieval_corpus(task_set)
    raw_corpus = build_raw_financial_corpus(task_set, deck_fixture_path=FIXTURE_DECK)
    index = raw_corpus.manifest.chunk_index
    sec_paragraph_companies = {
        chunk.provenance.company_ticker
        for chunk in raw_corpus.chunks
        if chunk.chunk_type == "sec_filing_paragraph"
    }
    print(
        f"raw_chunks={len(raw_corpus.chunks)} "
        f"curated_documents={len(benchmark_corpus.documents)} "
        f"companies={len(index.company_counts)} "
        f"sec_paragraph_companies={len(sec_paragraph_companies)} "
        f"transcript_chunks={index.chunk_type_counts.get('transcript_turn', 0)} "
        f"deck_pages={index.chunk_type_counts.get('deck_page', 0)} "
        f"corpus_modes=benchmark,raw"
    )


if __name__ == "__main__":
    main()
