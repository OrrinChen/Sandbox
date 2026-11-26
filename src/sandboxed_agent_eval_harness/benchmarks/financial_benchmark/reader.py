"""Read financial facts from the retrieved evidence and the public question."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from typing import Sequence

from sandboxed_agent_eval_harness.schemas import JsonDict


_SOURCE_SCALE = {"USD": 1, "thousands": 1_000, "millions": 1_000_000}
_OUTPUT_SCALE = {"usd": 1, "usd_thousands": 1_000, "usd_millions": 1_000_000}
_OPERAND_COUNT = {"lookup": 1, "difference": 2}


def read_answer(question: JsonDict, hits: Sequence[JsonDict], *, method: str) -> str:
    """Use the first matching fact per operand or reconcile facts in the full engine."""
    unit = question["unit"]
    operands = question["operands"]
    operation = question["operation"]
    if unit not in _OUTPUT_SCALE or len(operands) != _OPERAND_COUNT.get(operation):
        raise ValueError("invalid financial benchmark question")

    evidence = [
        _amounts(operand, hits, question["allowed_source_types"])
        for operand in operands
    ]
    if not all(evidence):
        return _response("insufficient", None, unit, [])

    if method == "full_engine":
        conflicts = [citation for amounts in evidence if len(amounts) > 1 for citation in amounts.values()]
        if conflicts:
            return _response("conflict", None, unit, conflicts)

    selected = [next(iter(amounts.items())) for amounts in evidence]
    amount = selected[0][0]
    if operation == "difference":
        amount -= selected[1][0]
    citations = [citation for _, citation in selected]
    return _response("answer", amount / _OUTPUT_SCALE[unit], unit, citations)


def _amounts(operand: JsonDict, hits: Sequence[JsonDict], allowed_sources: Sequence[str]) -> dict[Decimal, str]:
    amounts: dict[Decimal, str] = {}
    for hit in hits:
        source = hit.get("source_type")
        if (hit.get("company_ticker") != operand["ticker"] or hit.get("fiscal_period") != operand["period"]
                or hit.get("metric") != operand["metric"] or source not in allowed_sources
                or source != operand.get("source_type", source) or hit.get("currency") != "USD"):
            continue
        scale = _SOURCE_SCALE.get(hit.get("unit"))
        citation = hit.get("evidence_id")
        if scale is None or not isinstance(citation, str) or not citation:
            continue
        try:
            amount = Decimal(str(hit.get("numeric_value")))
        except InvalidOperation:
            continue
        if amount.is_finite():
            amounts.setdefault(amount * scale, citation)
    return amounts


def _response(verdict: str, amount: Decimal | None, unit: str, citations: Sequence[str]) -> str:
    return json.dumps({
        "verdict": verdict,
        "answer_value": format(amount, "f") if amount is not None else None,
        "unit": unit,
        "citations": list(dict.fromkeys(citations)),
    }, sort_keys=True)
