"""BM25 adapted from A1's ``src/financial_evidence_engine/retrieval/real_baselines.py``.

Upstream commit: 9bc84f7ef222c8eb829a576c4605ab19719204a4.
"""

from __future__ import annotations

from collections import Counter
from importlib.resources import files
import json
from math import log1p
import re
from typing import Sequence

from sandboxed_agent_eval_harness.schemas import JsonDict


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def load_corpus() -> JsonDict:
    return json.loads(files(__package__).joinpath("corpus.json").read_text(encoding="utf-8"))


def search(query: str, top_k: int, documents: Sequence[JsonDict]) -> list[JsonDict]:
    """Return positive-scoring hits in deterministic rank order."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    query_terms = sorted(set(_tokenize(query)))
    if not documents or not query_terms:
        return []

    document_count = len(documents)
    document_tokens = [_tokenize(document["text"]) for document in documents]
    document_frequencies = Counter(token for tokens in document_tokens for token in set(tokens))
    average_length = sum(map(len, document_tokens)) / document_count
    if not average_length:
        return []

    k1, b = 1.5, 0.75
    hits: list[JsonDict] = []
    for document, tokens in zip(documents, document_tokens):
        counts = Counter(tokens)
        length_normalizer = k1 * (1 - b + b * len(tokens) / average_length)
        score = 0.0
        for term in query_terms:
            frequency = counts[term]
            if frequency:
                document_frequency = document_frequencies[term]
                idf = log1p((document_count - document_frequency + 0.5) / (document_frequency + 0.5))
                score += idf * frequency * (k1 + 1) / (frequency + length_normalizer)
        rounded_score = round(score, 8)
        if rounded_score > 0:
            hits.append({**document, "score": rounded_score})

    return sorted(hits, key=lambda hit: (-hit["score"], hit["evidence_id"]))[:top_k]


def _tokenize(text: str) -> list[str]:
    return [match.group().lower() for match in _TOKEN_PATTERN.finditer(text)]
