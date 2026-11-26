"""Extract facts from the synthetic disclosure prose and apply the existing answer policy."""

from __future__ import annotations

import re
from typing import Sequence

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.reader import read_answer


_AMOUNT = r"(?P<value>[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s+USD(?:\s+(?P<scale>millions|thousands))?\b"
_METRIC = r"(?P<metric>[A-Z][a-z0-9-]*(?: [a-z0-9-]+)*)"
_FACT = (
    re.compile(rf"{_METRIC}(?: was |: ){_AMOUNT}"),
    re.compile(rf"\| (?P<metric>[a-z0-9 -]+?) \| {_AMOUNT}"),
    re.compile(rf"{_AMOUNT} in (?P<metric>[a-z0-9 -]+?) for FY\d{{4}}\b"),
)
_SOURCE = re.compile(
    r"\b(?:(?P<sec_filing>annual filing)|(?P<sec_xbrl_companyfacts>tagged annual facts)|"
    r"(?P<transcript>(?:(?:earnings|analyst|results|conference) )?call(?: transcript)?|(?:earnings )?transcript|(?:earnings )?Q&A)|"
    r"(?P<investor_deck>(?:(?:investor|slide) )?(?:deck|presentation)|(?:investor )?slides|slide pack))\b",
    re.IGNORECASE,
)
_PERIOD = re.compile(r"\bFY\d{4}\b")
_UNIT = re.compile(r"\b(?:(thousands|millions) of )?US dollars\b", re.IGNORECASE)
_ISSUER = re.compile(r"\b[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*(?: [A-Z][a-z]+(?:[-'][A-Z][a-z]+)*)+\b")
_INTRO = re.compile(r"^(?:Calculate|Use|Give|Ignore|For|Take) ")
_IGNORED_PREAMBLE = re.compile(r"^(?:Ignore\b|Our draft\b)[^.]*\.\s*", re.IGNORECASE)
_LATTER_ISSUER = re.compile(r"\bfor the latter['’]s\b", re.IGNORECASE)
_REVERSED = re.compile(r"\b(?:away|deducted|subtracted) from\b", re.IGNORECASE)
_SUBTRACT = re.compile(r"\b(?:subtract(?:ing)?|deduct(?:ing)?|remov(?:e|ing))\b", re.IGNORECASE)
_INFIX = re.compile(
    r"\b(?:minus|less|than|exceed(?:s|ed)?|subtract|deduct|remove|take off)\b|[−–]",
    re.IGNORECASE,
)
_BETWEEN = re.compile(r"\b(?:difference|gap|spread) between\b", re.IGNORECASE)
_BASIS = re.compile(
    r"\b(?P<adjusted>adjusted|normalized|non[- ]GAAP)\b|\b(?P<projected>forecast|projected|guidance)\b|"
    r"\b(?P<segment>segment|business unit|division)\b|\b(?P<quarterly>last-quarter|quarterly|Q[1-4])\b",
    re.IGNORECASE,
)
_STOP_WORDS = frozenset("a an as at by for from in of on the to under with was were".split())


def read_text_answer(question: str, hits: Sequence[tuple[str, str]], *, method: str) -> str:
    """Read a question and ranked (citation handle, raw snippet) pairs only."""
    request = _IGNORED_PREAMBLE.sub("", question)
    issuers = [_INTRO.sub("", match.group()) for match in _ISSUER.finditer(request)]
    issuer = (issuers[-1] if _LATTER_ISSUER.search(request) else issuers[0]) if issuers else ""
    period_match = _PERIOD.search(request)
    period = period_match.group() if period_match else ""
    unit_match = _UNIT.search(request)
    unit = f"usd_{unit_match[1].lower()}" if unit_match and unit_match[1] else "usd"
    clauses = _clauses(request)
    operands = [{"ticker": issuer, "period": period, "metric": str(index)} for index in range(len(clauses))]
    facts = []
    if issuer and period and unit_match:
        for evidence_id, snippet in hits:
            source = _SOURCE.search(snippet)
            if not source or issuer not in _ISSUER.findall(snippet) or period not in _PERIOD.findall(snippet):
                continue
            fact = next((match for pattern in _FACT if (match := pattern.search(snippet))), None)
            if fact is None:
                continue
            for operand, (clause, required_source) in zip(operands, clauses):
                if (required_source is None or source.lastgroup == required_source) and _matches_metric(fact["metric"], clause):
                    facts.append({
                        "evidence_id": evidence_id, "company_ticker": issuer, "fiscal_period": period,
                        "metric": operand["metric"], "source_type": source.lastgroup, "currency": "USD",
                        "unit": fact["scale"] or "USD", "numeric_value": fact["value"].replace(",", "").replace("−", "-"),
                    })
    return read_answer({
        "unit": unit, "operation": "difference" if len(clauses) == 2 else "lookup", "operands": operands,
        "allowed_source_types": list(_SOURCE.groupindex),
    }, facts, method=method)


def _clauses(question: str) -> list[tuple[str, str | None]]:
    sources = list(_SOURCE.finditer(question))
    if len(sources) != 2:
        return [(question, sources[0].lastgroup if len(sources) == 1 else None)]
    first, second = sources
    between = question[first.end():second.start()]
    separator = _REVERSED.search(between)
    reverse = separator is not None
    if not separator:
        separator = _INFIX.search(between)
    if not separator and _BETWEEN.search(question[:first.start()]):
        separator = re.search(r"\band\b", between, re.IGNORECASE)
    if not separator and _SUBTRACT.search(question[:first.start()]):
        separator = re.search(r"\bfrom\b", between, re.IGNORECASE)
        reverse = separator is not None
    if separator:
        offset = first.end()
    else:
        # Sources may be listed after the two measures in the same order as the operands.
        separator = _INFIX.search(question[:first.start()])
        if separator is None:
            return [("", None)]
        offset = 0
    clauses = [
        (question[:offset + separator.start()], first.lastgroup),
        (question[offset + separator.end():], second.lastgroup),
    ]
    return clauses[::-1] if reverse else clauses


def _terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z]+", text.lower())) - _STOP_WORDS
    return {re.sub(r"(?:ing|ed|s)$", "", word) if len(word) > 4 else word for word in terms}


def _matches_metric(metric: str, clause: str) -> bool:
    basis = _BASIS.search(metric)
    if basis and basis.lastgroup not in {match.lastgroup for match in _BASIS.finditer(clause)}:
        return False
    terms = _terms(metric)
    overlap = len(terms & _terms(clause))
    # Disjoint aliases abstain. Exact or majority term overlap can support a match.
    return bool(terms and (overlap == len(terms) or overlap >= 2 and 2 * overlap >= len(terms)))
