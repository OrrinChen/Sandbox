"""Split explicitly sourced comparisons into two budgeted hybrid searches."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from sandboxed_agent_eval_harness.benchmarks.financial_evidence.methods import search_full
from sandboxed_agent_eval_harness.schemas import JsonDict


_SOURCE = re.compile(
    r"\b(?:(?P<transcript>(?:(?:earnings|analyst|results|conference)\s+)?call(?:\s+transcript)?|"
    r"(?:earnings\s+)?transcript|(?:earnings\s+)?q\s*&\s*a)|"
    r"(?P<investor_deck>(?:investor\s+|slide\s+)?(?:deck|presentation)|(?:investor\s+)?slides|slide\s+pack))\b",
    re.IGNORECASE,
)
_SEPARATOR = re.compile(
    r"\b(?:minus|less|(?:subtract(?:ed|ing)?|deduct(?:ed|ing)?|remov(?:e|ed|ing))(?:\s+from)?|"
    r"away\s+from|take\s+off|net\s+of|than|exceed(?:s|ed)?|versus|vs\.?|"
    r"(?:compared|relative)\s+(?:with|to)|(?:offset|reduced)\s+by)\b|[−–]",
    re.IGNORECASE,
)
_DIFFERENCE_AND = re.compile(r"\b(?:difference|gap|spread)\s+between\b", re.IGNORECASE)
_REVERSE = re.compile(r"\b(?:subtract(?:ing)?|deduct(?:ing)?|remov(?:e|ing))\b", re.IGNORECASE)
_AND = re.compile(r"\band\b", re.IGNORECASE)
_FROM = re.compile(r"\bfrom\b", re.IGNORECASE)
_SENTENCE = re.compile(r"[.!?](?=\s|$)")
_REPORTING_SCOPE = {
    "adjusted": re.compile(r"\b(?:adjusted|normalized|non[-\s]?gaap)\b", re.IGNORECASE),
    "projected": re.compile(r"\b(?:project(?:ed|ion)|forecast|guidance|estimate[ds]?)\b", re.IGNORECASE),
    "quarterly": re.compile(r"\b(?:quarter(?:ly)?|q[1-4])\b", re.IGNORECASE),
    "segment": re.compile(r"\b(?:segment|business\s+unit|division)\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class Subquery:
    text: str
    source_type: str


def split_query(query: str) -> tuple[Subquery, ...]:
    """Extract the two source-bearing clauses from an explicit comparison."""
    sources = list(_SOURCE.finditer(query))
    if len(sources) != 2 or sources[0].lastgroup == sources[1].lastgroup:
        return ()
    first, second = sources
    separator = _SEPARATOR.search(query, first.end(), second.start())
    if separator is None and _DIFFERENCE_AND.search(query, 0, first.start()):
        separator = _AND.search(query, first.end(), second.start())
    if separator is None and _REVERSE.search(query, 0, first.start()):
        separator = _FROM.search(query, first.end(), second.start())
    if separator is None:
        return ()

    start = max((punctuation.end() for punctuation in _SENTENCE.finditer(query, 0, first.start())), default=0)
    end = _SENTENCE.search(query, second.end())
    clauses = (query[start:separator.start()], query[separator.end():end.start() if end else len(query)])
    return tuple(Subquery(text.strip(" ,:;"), str(source.lastgroup)) for text, source in zip(clauses, sources))


def search_split(
    query: str,
    top_k: int,
    documents: Sequence[JsonDict],
    *,
    tickers: Sequence[str],
    fiscal_periods: Sequence[str],
    source_types: Sequence[str],
) -> list[JsonDict]:
    """Search source clauses with a shared hit budget, preserving both ranked lists."""
    subqueries = split_query(query)
    if top_k < 2 or not subqueries or any(branch.source_type not in source_types for branch in subqueries):
        return search_full("hybrid", query, top_k, documents, tickers=tickers, fiscal_periods=fiscal_periods,
                           source_types=source_types)

    # Restrict to entities and periods only when the text resolves them unambiguously.
    names = {(d.get("company_name") or d["company_ticker"], d["company_ticker"]) for d in documents
             if d["company_ticker"] in tickers}
    mentioned_tickers = {ticker for name, ticker in names if _mentions(query, name) or _mentions(query, ticker)}
    mentioned_periods = {period for period in fiscal_periods if _mentions(query, period)}
    issuer_scope = sorted(mentioned_tickers) if len(mentioned_tickers) == 1 else tickers
    period_scope = sorted(mentioned_periods) if len(mentioned_periods) == 1 else fiscal_periods

    branches = []
    for index, branch in enumerate(subqueries):
        candidates = [d for d in documents if d["source_type"] == branch.source_type
                      and (not issuer_scope or d["company_ticker"] in issuer_scope)
                      and (not period_scope or d["fiscal_period"] in period_scope)]
        # An unqualified reporting request uses the reported figure when both bases are present.
        metrics = {(d["company_ticker"], d["fiscal_period"], d.get("metric")) for d in candidates}
        hits = search_full("hybrid", _SOURCE.sub(" ", branch.text), (top_k + 1 - index) // 2,
                           [d for d in candidates if _reporting_basis_matches(d, branch.text, metrics)],
                           tickers=issuer_scope, fiscal_periods=period_scope, source_types=(branch.source_type,))
        branches.append(hits)

    # Interleave branch ranks because scores are normalized within each source.
    return list({hit["evidence_id"]: hit for rank in range((top_k + 1) // 2)
                 for branch in branches for hit in branch[rank:rank + 1]}.values())


def _mentions(query: str, name: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", query, re.IGNORECASE) is not None


def _reporting_basis_matches(document: JsonDict, clause: str, metrics: set[tuple[str, str, str | None]]) -> bool:
    prefix, _, base = (document.get("metric") or "").partition("_")
    qualifier = _REPORTING_SCOPE.get(prefix)
    base_key = (document["company_ticker"], document["fiscal_period"], base)
    return qualifier is None or base_key not in metrics or qualifier.search(clause) is not None
