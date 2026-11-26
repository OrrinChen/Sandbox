"""Build a deterministic answer from a public question and the retrieved chunks."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.schemas import JsonDict


_USD_SCALES = {"USD": 1, "dollars": 1, "millions": 1_000_000, "billions": 1_000_000_000}
_GUIDANCE_RANGE = re.compile(
    r"\b(?:guidance|forecast)\s+(?:range\s+)?(?:of\s+|was\s+|is\s+)?"
    r"(?:(USD|\$)\s*)?([\d,.]+)\s*(?:to|[-–])\s*(?:(USD|\$)\s*)?([\d,.]+)\s*(USD|millions|billions)\b",
    re.IGNORECASE,
)
_RISK_DIRECTION = re.compile(
    r"\brisk exposure\s+(?:materially\s+)?(did not decrease|increased|remained unchanged|decreased)\b",
    re.IGNORECASE,
)


def build_answer(public: JsonDict, hits: Sequence[JsonDict], *, method: str) -> str:
    """Use ranked hits directly or apply the full-engine evidence checks."""
    if method == "full_engine":
        cited_hits = [
            hit for hit in hits
            if hit["company_ticker"] in public["company_tickers"]
            and hit["fiscal_period"] in public["fiscal_periods"]
            and hit["source_type"] in public["allowed_source_types"]
        ]
        tickers = public["company_tickers"]
        if "operating margin" in public["question"].casefold() and len(tickers) >= 2:
            verdict, reason, cited_hits = _compare_operating_margins(cited_hits, tickers[:2], max(public["fiscal_periods"]))
        else:
            verdict, reason = _verified_verdict(public, cited_hits)
    else:
        cited_hits = hits
        verdict = "support" if hits else "insufficient"
        reason = "The retriever returned evidence." if hits else "The retriever returned no evidence."

    return json.dumps({
        "verdict": verdict,
        "citations": list(dict.fromkeys(hit["evidence_id"] for hit in cited_hits)),
        "reason": reason,
    }, sort_keys=True)


def _verified_verdict(public: JsonDict, hits: Sequence[JsonDict]) -> tuple[str, str]:
    question = public["question"].casefold()
    tickers = public["company_tickers"]
    periods = sorted(public["fiscal_periods"])
    subject, current = tickers[0], periods[-1]
    filings = [hit for hit in hits if hit["source_type"] == "sec_xbrl_companyfacts"]

    if "revenue trend" in question and len(periods) >= 2:
        prior_revenue = _fact(filings, subject, periods[-2], "revenue")
        current_revenue = _fact(filings, subject, current, "revenue")
        if prior_revenue is not None and current_revenue is not None:
            return _comparison(current_revenue > prior_revenue, "Compared reported revenue across both fiscal years.")

    if "actual revenue" in question and "guidance" in question:
        actual = _fact(filings, subject, current, "revenue")
        guidance = _guidance_range(hits, subject, current)
        if actual is not None and guidance is not None:
            return _comparison(guidance[0] <= actual <= guidance[1], "Compared reported revenue with the stated guidance range.")

    if "investor-deck" in question and "reconcile" in question:
        decks = [
            hit for hit in hits
            if hit["source_type"] == "investor_deck" and hit["modality"] in {"chart", "table"}
            and hit.get("section_or_page", "").rsplit(" / ", 1)[-1].casefold()
            in {"total revenue", "consolidated revenue", "company-wide revenue"}
        ]
        deck_value = _fact(decks, subject, current, "revenue")
        filing_value = _fact(filings, subject, current, "revenue")
        if deck_value is not None and filing_value is not None:
            return _comparison(deck_value == filing_value, "Reconciled deck and reported revenue after normalizing units.")

    if "risk disclosure" in question and "exposure materially decreased" in question:
        directions = {
            direction.lower() == "decreased"
            for hit in hits
            if hit["company_ticker"] == subject and hit["fiscal_period"] == current and hit["source_type"] == "sec_filing"
            for direction in _RISK_DIRECTION.findall(hit["text"])
        }
        if len(directions) == 1:
            return _comparison(directions.pop(), "Used an explicit statement of risk direction from the filing.")

    return "insufficient", "The retrieved evidence does not establish the requested comparison or causal claim."


def _comparison(supported: bool, reason: str) -> tuple[str, str]:
    return ("support" if supported else "contradict"), reason


def _fact(hits: Sequence[JsonDict], ticker: str, period: str, metric: str) -> Optional[Decimal]:
    values = {amount for amount, _ in _reported_amounts(hits, ticker, period, metric)}
    return values.pop() if len(values) == 1 else None


def _reported_amounts(
    hits: Sequence[JsonDict], ticker: str, period: str, metric: str,
) -> list[tuple[Decimal, JsonDict]]:
    amounts = []
    for hit in hits:
        if (hit["company_ticker"], hit["fiscal_period"], hit["metric"]) != (ticker, period, metric):
            continue
        value = hit.get("numeric_value")
        scale = _USD_SCALES.get(hit.get("unit"))
        if hit.get("currency") == "USD" and scale is not None and value is not None:
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                continue
            if number.is_finite():
                amounts.append((number * scale, hit))
    return amounts


def _compare_operating_margins(
    hits: Sequence[JsonDict], tickers: Sequence[str], period: str,
) -> tuple[str, str, list[JsonDict]]:
    filings = [hit for hit in hits if hit["source_type"] in {"sec_xbrl_companyfacts", "sec_filing"}]
    operands = [
        _reported_amounts(filings, ticker, period, metric)
        for ticker in tickers for metric in ("operating_income", "revenue")
    ]
    conflicts = [
        hit for amounts in operands if len({value for value, _ in amounts}) > 1
        for _, hit in amounts
    ]
    if conflicts:
        return "insufficient", "Reported operands disagree after normalizing units.", conflicts

    selected = []
    for index, amounts in enumerate(operands):
        if not amounts:
            continue
        # Use the peer filing table as an independently presented comparison denominator.
        xbrl = next((item for item in amounts if item[1]["source_type"] == "sec_xbrl_companyfacts"), amounts[0])
        if index == len(operands) - 1:
            table = next((item for item in amounts if item[1].get("modality") == "table"), None)
            selected.append(table or xbrl)
        else:
            selected.append(xbrl)

    citations = [hit for _, hit in selected]
    if len(selected) != len(operands) or any(selected[index][0] <= 0 for index in (1, 3)):
        return "insufficient", "Both issuers need comparable operating income and positive revenue.", citations

    subject_income, subject_revenue, peer_income, peer_revenue = (value for value, _ in selected)
    subject_margin, peer_margin = subject_income / subject_revenue, peer_income / peer_revenue
    reason = (
        f"For {period}, operating income divided by revenue gives "
        f"{tickers[0]} {subject_margin:.2%} and {tickers[1]} {peer_margin:.2%}. "
        f"Peer revenue source: {citations[-1]['source_type']} ({citations[-1].get('modality', 'unspecified')})."
    )
    verdict = "support" if subject_margin > peer_margin else "contradict"
    return verdict, reason, citations


def _guidance_range(hits: Sequence[JsonDict], ticker: str, period: str) -> Optional[tuple[Decimal, Decimal]]:
    ranges = set()
    for hit in hits:
        if (hit["company_ticker"], hit["fiscal_period"]) != (ticker, period):
            continue
        if hit["source_type"] not in {"transcript", "analyst_estimates"} or hit["metric"] not in {"revenue_guidance", "revenue_estimate"}:
            continue
        for low_currency, low, high_currency, high, unit in _GUIDANCE_RANGE.findall(hit["text"]):
            if not (hit.get("currency") == "USD" or unit.upper() == "USD" or "USD" in (low_currency.upper(), high_currency.upper())):
                continue
            scale = _USD_SCALES["USD" if unit.lower() == "usd" else unit.lower()]
            try:
                bounds = (Decimal(low.replace(",", "")) * scale, Decimal(high.replace(",", "")) * scale)
            except InvalidOperation:
                continue
            if bounds[0] <= bounds[1]:
                ranges.add(bounds)
    return ranges.pop() if len(ranges) == 1 else None
