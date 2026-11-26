"""A1's offline retrieval methods over the bundled raw fixture corpus.

Adapted from ``retrieval/real_baselines.py`` at A1 commit
9bc84f7ef222c8eb829a576c4605ab19719204a4. The rerankers use the
public query and corpus metadata for their metric and relationship signals.
"""

from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Sequence

from sandboxed_agent_eval_harness.benchmarks.financial_evidence.retrieval import _tokenize, search
from sandboxed_agent_eval_harness.schemas import JsonDict


METHODS = ("bm25", "dense_proxy", "hybrid", "graph", "full_engine")

_SYNONYMS = {
    "revenue": ("sales", "net", "actual"),
    "sales": ("revenue",),
    "margin": ("income", "profitability"),
    "operating": ("operations", "income"),
    "risk": ("exposure", "supply", "demand"),
    "guidance": ("estimate", "range", "forecast"),
    "chart": ("deck", "presentation", "table"),
    "filing": ("sec", "10k", "annual"),
}
_OPERATING_MARGIN_OPERANDS = {"operating_income", "revenue"}


def search_full(
    method: str,
    query: str,
    top_k: int,
    documents: Sequence[JsonDict],
    *,
    tickers: Sequence[str],
    fiscal_periods: Sequence[str],
    source_types: Sequence[str],
) -> list[JsonDict]:
    """Return ranked evidence using only inputs visible to a retriever."""
    if method not in METHODS:
        raise ValueError(f"unknown A1 retrieval method: {method}")
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if method == "bm25":
        return search(query, top_k, documents)
    if method == "dense_proxy":
        return _dense_search(query, top_k, documents)

    graph = method in {"graph", "full_engine"}
    if graph:
        documents = [
            document for document in documents
            if all(_metadata_matches(document, tickers, fiscal_periods, source_types))
        ]
    if not documents:
        return []

    tokens = _tokenize(query)
    query_terms = set(tokens)
    operating_margin = ("operating", "margin") in zip(tokens, tokens[1:])
    retrieval_query = f"{query} operating income revenue" if operating_margin else query
    indexed_documents = [
        {
            **document,
            "text": " ".join((document["text"], document["modality"], document["metric"] or "")),
        }
        for document in documents
    ]
    bm25_hits = search(retrieval_query, len(indexed_documents), indexed_documents)
    dense_hits = _dense_search(retrieval_query, len(indexed_documents), indexed_documents)
    bm25_scores = {hit["evidence_id"]: hit["score"] for hit in bm25_hits}
    dense_scores = {hit["evidence_id"]: hit["score"] for hit in dense_hits}
    bm25_scale = bm25_hits[0]["score"] if bm25_hits else 1.0
    dense_scale = dense_hits[0]["score"] if dense_hits else 1.0
    candidate_ids = bm25_scores.keys() | dense_scores.keys()

    hybrid_hits = []
    for hit in documents:
        evidence_id = hit["evidence_id"]
        if evidence_id not in candidate_ids:
            continue
        company, period, source = _metadata_matches(hit, tickers, fiscal_periods, source_types)
        metric_terms = _tokenize(hit["metric"] or "")
        metric = bool(metric_terms) and query_terms.issuperset(metric_terms)
        score = (
            0.45 * bm25_scores.get(evidence_id, 0.0) / bm25_scale
            + 0.35 * dense_scores.get(evidence_id, 0.0) / dense_scale
            + 0.08 * company + 0.08 * period + 0.06 * source + 0.06 * metric
            + 0.20 * (hit["modality"] in query_terms)
        )
        if graph:
            score += 0.12 + 0.10 * metric
        hybrid_hits.append({**hit, "score": round(score, 8)})

    ranked = _top_hits(hybrid_hits, len(hybrid_hits))
    operands = []
    if operating_margin:
        operands = _margin_operands(ranked, tickers, fiscal_periods, source_types)
    return _select_hits(ranked, top_k, query_terms, operands)


def _margin_operands(
    ranked: Sequence[JsonDict], tickers: Sequence[str], fiscal_periods: Sequence[str], source_types: Sequence[str],
) -> list[JsonDict]:
    groups: dict[tuple[str, str, str], list[JsonDict]] = {}
    for hit in ranked:
        if (hit["metric"] not in _OPERATING_MARGIN_OPERANDS or hit.get("numeric_value") is None
                or not hit.get("currency") or not all(_metadata_matches(hit, tickers, fiscal_periods, source_types))):
            continue
        group = (hit["company_ticker"], hit["fiscal_period"], hit["currency"])
        groups.setdefault(group, []).append(hit)

    operands = []
    corroboration = []
    for (ticker, _, _), hits in groups.items():
        by_source: dict[tuple[str, str, str], dict[str, JsonDict]] = {}
        best_per_metric = {}
        for hit in hits:
            source = (hit["source_type"], hit["modality"], hit.get("document_id", ""))
            by_source.setdefault(source, {}).setdefault(hit["metric"], hit)
            best_per_metric.setdefault(hit["metric"], hit)
        if best_per_metric.keys() != _OPERATING_MARGIN_OPERANDS:
            continue

        # Prefer a complete structured statement before mixing operands across presentations.
        complete = [source for source, pair in by_source.items() if pair.keys() == _OPERATING_MARGIN_OPERANDS]
        primary = min(complete, key=lambda source: source[1] != "xbrl") if complete else None
        pair = by_source[primary] if primary is not None else best_per_metric
        operands.extend(pair.values())

        # Use spare slots to cross-check the reference side of an ordered comparison.
        if ticker in tickers[1:]:
            alternate = next((hit for hit in hits if hit["source_type"] != pair[hit["metric"]]["source_type"]
                              and hit["modality"] != pair[hit["metric"]]["modality"]
                              and hit.get("document_id") != pair[hit["metric"]].get("document_id")), None)
            if alternate is not None:
                corroboration.append(alternate)
    return operands + corroboration


def _select_hits(
    ranked: Sequence[JsonDict], top_k: int, query_terms: set[str], operands: Sequence[JsonDict],
) -> list[JsonDict]:
    requested = set(query_terms)
    selected = {hit["evidence_id"]: hit for hit in operands[:top_k]}
    requested.difference_update(hit["modality"] for hit in selected.values())
    for hit in ranked:
        if len(selected) == top_k:
            break
        modality = hit["modality"]
        if modality in requested:
            selected[hit["evidence_id"]] = hit
            requested.remove(modality)

    for hit in ranked:
        if len(selected) == top_k:
            break
        selected[hit["evidence_id"]] = hit
    return _top_hits(list(selected.values()), top_k)


def _metadata_matches(
    hit: JsonDict, tickers: Sequence[str], fiscal_periods: Sequence[str], source_types: Sequence[str],
) -> tuple[bool, bool, bool]:
    return (
        hit["company_ticker"] in tickers,
        hit["fiscal_period"] in fiscal_periods,
        hit["source_type"] in source_types,
    )


def _dense_search(query: str, top_k: int, documents: Sequence[JsonDict]) -> list[JsonDict]:
    query_vector = _token_vector(query)
    query_norm = _norm(query_vector)
    if not query_norm:
        return []
    hits = []
    for document in documents:
        vector = _token_vector(document["text"])
        dot_product = sum(weight * vector.get(term, 0) for term, weight in query_vector.items())
        if dot_product:
            score = round(dot_product / (query_norm * _norm(vector)), 8)
            hits.append({**document, "score": score})
    return _top_hits(hits, top_k)


def _token_vector(text: str) -> dict[str, float]:
    counts = Counter(_tokenize(text))
    vector: dict[str, float] = dict(counts)
    for term, count in counts.items():
        for synonym in _SYNONYMS.get(term, ()):
            vector[synonym] = vector.get(synonym, 0.0) + 0.5 * count
    return vector


def _norm(vector: dict[str, float]) -> float:
    return sqrt(sum(weight * weight for weight in vector.values()))


def _top_hits(hits: list[JsonDict], top_k: int) -> list[JsonDict]:
    return sorted(hits, key=lambda hit: (-hit["score"], hit["evidence_id"]))[:top_k]
