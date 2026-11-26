"""Seed gold task builder for multimodal due-diligence evaluation."""

from __future__ import annotations

from typing import List, Tuple

from .task_set import (
    DueDiligenceTask,
    DueDiligenceTaskSet,
    EvidenceRequirement,
    KnownDistractor,
    NumericCheckSpec,
)


COMPANIES: Tuple[Tuple[str, str], ...] = (
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("NVDA", "NVIDIA"),
    ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"),
    ("META", "Meta"),
    ("JPM", "JPMorgan Chase"),
    ("WMT", "Walmart"),
    ("TSLA", "Tesla"),
    ("NFLX", "Netflix"),
)


TASK_SET_ID = "phase6_seed_multimodal_due_diligence"
TASK_SET_VERSION = "2026-05-01"


def build_seed_task_set() -> DueDiligenceTaskSet:
    """Build the Phase 6 seed task set.

    The set intentionally covers the full 10-company FMP snapshot universe with
    six task families per company. The labels are source/validator specs rather
    than raw paid payloads, so the task set is safe to commit.
    """

    tasks: List[DueDiligenceTask] = []
    for index, (ticker, name) in enumerate(COMPANIES):
        peer_ticker, peer_name = COMPANIES[(index + 1) % len(COMPANIES)]
        tasks.extend(
            [
                _single_company_trend(ticker, name),
                _cross_company_comparison(ticker, name, peer_ticker, peer_name),
                _management_claim_verification(ticker, name),
                _risk_contradiction(ticker, name),
                _guidance_vs_actuals(ticker, name),
                _chart_table_reconciliation(ticker, name),
            ]
        )

    return DueDiligenceTaskSet(
        task_set_id=TASK_SET_ID,
        version=TASK_SET_VERSION,
        tasks=tuple(tasks),
    )


def _single_company_trend(ticker: str, name: str) -> DueDiligenceTask:
    family = "single_company_trend"
    task_id = _task_id(ticker, family)
    return DueDiligenceTask(
        task_id=task_id,
        family=family,
        question=(
            f"Did {name}'s FY2024 revenue trend improve versus FY2023, and is the "
            "trend backed by filing facts rather than narrative-only evidence?"
        ),
        claim_text=f"{name}'s FY2024 revenue grew versus FY2023.",
        company_tickers=(ticker,),
        fiscal_periods=("FY2023", "FY2024"),
        allowed_source_types=("sec_xbrl_companyfacts", "sec_filing"),
        expected_evidence=(
            _evidence(task_id, "ev1", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "current revenue fact", "revenue"),
            _evidence(task_id, "ev2", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2023", "prior revenue fact", "revenue"),
            _evidence(task_id, "ev3", "sec_filing", "text", ticker, "FY2024", "MD&A revenue discussion", "revenue"),
        ),
        numeric_checks=(
            _numeric_check(task_id, "num1", ticker, "FY2024", "revenue", "year_over_year_growth"),
        ),
        expected_verdict="support",
        known_distractors=(
            _distractor(task_id, "dist1", "quarterly revenue value", "Quarterly figures cannot validate an annual trend."),
            _distractor(task_id, "dist2", "peer company revenue", "Peer-company facts do not support this single-company claim."),
        ),
    )


def _cross_company_comparison(ticker: str, name: str, peer_ticker: str, peer_name: str) -> DueDiligenceTask:
    family = "cross_company_comparison"
    task_id = _task_id(ticker, family)
    return DueDiligenceTask(
        task_id=task_id,
        family=family,
        question=(
            f"Was {name}'s FY2024 operating margin higher than {peer_name}'s after "
            "normalizing company, period, metric, and unit?"
        ),
        claim_text=f"{name}'s FY2024 operating margin exceeded {peer_name}'s FY2024 operating margin.",
        company_tickers=(ticker, peer_ticker),
        fiscal_periods=("FY2024",),
        allowed_source_types=("sec_xbrl_companyfacts", "sec_filing"),
        expected_evidence=(
            _evidence(task_id, "ev1", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "subject operating income fact", "operating_income"),
            _evidence(task_id, "ev2", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "subject revenue fact", "revenue"),
            _evidence(task_id, "ev3", "sec_xbrl_companyfacts", "xbrl", peer_ticker, "FY2024", "peer operating income fact", "operating_income"),
            _evidence(task_id, "ev4", "sec_filing", "table", peer_ticker, "FY2024", "peer income statement table", "revenue"),
        ),
        numeric_checks=(
            _numeric_check(task_id, "num1", ticker, "FY2024", "operating_margin", "compare_against_peer"),
            _numeric_check(task_id, "num2", peer_ticker, "FY2024", "operating_margin", "peer_denominator_check"),
        ),
        expected_verdict="support",
        known_distractors=(
            _distractor(task_id, "dist1", "net margin instead of operating margin", "Metric substitution changes the claim being tested."),
            _distractor(task_id, "dist2", "different fiscal year for the peer", "Cross-company comparison requires aligned fiscal periods."),
        ),
    )


def _management_claim_verification(ticker: str, name: str) -> DueDiligenceTask:
    family = "management_claim_verification"
    task_id = _task_id(ticker, family)
    return DueDiligenceTask(
        task_id=task_id,
        family=family,
        question=(
            f"Can {name}'s management claim that FY2024 margin expansion was driven "
            "by durable operating leverage be fully verified from cited documents?"
        ),
        claim_text=f"{name}'s FY2024 margin expansion was driven by durable operating leverage.",
        company_tickers=(ticker,),
        fiscal_periods=("FY2023", "FY2024"),
        allowed_source_types=("transcript", "sec_xbrl_companyfacts", "sec_filing"),
        expected_evidence=(
            _evidence(task_id, "ev1", "transcript", "transcript", ticker, "FY2024", "management operating leverage statement", "operating_margin"),
            _evidence(task_id, "ev2", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "current margin numerator and denominator", "operating_margin"),
            _evidence(task_id, "ev3", "sec_filing", "text", ticker, "FY2024", "cost structure disclosure", "operating_expense"),
        ),
        numeric_checks=(
            _numeric_check(task_id, "num1", ticker, "FY2024", "operating_margin", "margin_expansion"),
            _numeric_check(task_id, "num2", ticker, "FY2024", "operating_expense", "expense_growth_vs_revenue_growth"),
        ),
        expected_verdict="insufficient",
        known_distractors=(
            _distractor(task_id, "dist1", "management quote without numeric support", "Narrative alone cannot verify the margin driver."),
            _distractor(task_id, "dist2", "one-time charge discussion", "One-time items can explain margin movement without proving durable leverage."),
        ),
    )


def _risk_contradiction(ticker: str, name: str) -> DueDiligenceTask:
    family = "risk_contradiction"
    task_id = _task_id(ticker, family)
    return DueDiligenceTask(
        task_id=task_id,
        family=family,
        question=(
            f"Does {name}'s FY2024 risk disclosure contradict the claim that its key "
            "supply-chain or demand exposure materially decreased?"
        ),
        claim_text=f"{name}'s FY2024 risk exposure materially decreased.",
        company_tickers=(ticker,),
        fiscal_periods=("FY2023", "FY2024"),
        allowed_source_types=("sec_filing", "transcript", "sec_xbrl_companyfacts"),
        expected_evidence=(
            _evidence(task_id, "ev1", "sec_filing", "text", ticker, "FY2024", "risk factor disclosure", "risk_exposure"),
            _evidence(task_id, "ev2", "sec_filing", "text", ticker, "FY2023", "prior-year risk factor disclosure", "risk_exposure"),
            _evidence(task_id, "ev3", "transcript", "transcript", ticker, "FY2024", "management risk commentary", "risk_exposure"),
            _evidence(task_id, "ev4", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "exposure-related financial fact", "revenue"),
        ),
        numeric_checks=(
            _numeric_check(task_id, "num1", ticker, "FY2024", "risk_exposure", "risk_disclosure_change"),
        ),
        expected_verdict="contradict",
        known_distractors=(
            _distractor(task_id, "dist1", "boilerplate risk factor from another issuer", "Risk contradiction must use the same company."),
            _distractor(task_id, "dist2", "current transcript optimism", "Optimistic commentary does not override filed risk disclosure."),
        ),
    )


def _guidance_vs_actuals(ticker: str, name: str) -> DueDiligenceTask:
    family = "guidance_vs_actuals"
    task_id = _task_id(ticker, family)
    return DueDiligenceTask(
        task_id=task_id,
        family=family,
        question=(
            f"Did {name}'s FY2024 actual revenue fall within the cited management "
            "guidance or analyst-estimate range?"
        ),
        claim_text=f"{name}'s FY2024 actual revenue was within the cited guidance range.",
        company_tickers=(ticker,),
        fiscal_periods=("FY2024",),
        allowed_source_types=("transcript", "analyst_estimates", "sec_xbrl_companyfacts"),
        expected_evidence=(
            _evidence(task_id, "ev1", "transcript", "transcript", ticker, "FY2024", "management guidance statement", "revenue_guidance"),
            _evidence(task_id, "ev2", "analyst_estimates", "estimate", ticker, "FY2024", "consensus range cross-check", "revenue_estimate"),
            _evidence(task_id, "ev3", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "reported revenue actual", "revenue"),
        ),
        numeric_checks=(
            _numeric_check(task_id, "num1", ticker, "FY2024", "revenue", "actual_within_guidance_range"),
        ),
        expected_verdict="support",
        known_distractors=(
            _distractor(task_id, "dist1", "EPS guidance", "EPS guidance cannot validate a revenue guidance claim."),
            _distractor(task_id, "dist2", "post-period analyst revision", "Estimates after actual results are not contemporaneous guidance evidence."),
        ),
    )


def _chart_table_reconciliation(ticker: str, name: str) -> DueDiligenceTask:
    family = "chart_table_reconciliation"
    task_id = _task_id(ticker, family)
    return DueDiligenceTask(
        task_id=task_id,
        family=family,
        question=(
            f"Does {name}'s FY2024 investor-deck chart or table reconcile to the "
            "corresponding SEC/XBRL reported metric?"
        ),
        claim_text=f"{name}'s FY2024 deck chart reconciles to its reported financial metric.",
        company_tickers=(ticker,),
        fiscal_periods=("FY2024",),
        allowed_source_types=("investor_deck", "sec_xbrl_companyfacts", "sec_filing"),
        expected_evidence=(
            _evidence(task_id, "ev1", "investor_deck", "chart", ticker, "FY2024", "deck chart value", "revenue"),
            _evidence(task_id, "ev2", "sec_xbrl_companyfacts", "xbrl", ticker, "FY2024", "reported XBRL fact", "revenue"),
            _evidence(task_id, "ev3", "sec_filing", "table", ticker, "FY2024", "filing table value", "revenue"),
        ),
        numeric_checks=(
            _numeric_check(task_id, "num1", ticker, "FY2024", "revenue", "reconcile_chart_to_xbrl"),
        ),
        expected_verdict="support",
        known_distractors=(
            _distractor(task_id, "dist1", "non-GAAP chart without bridge", "Non-GAAP chart values need an explicit bridge before reconciliation."),
            _distractor(task_id, "dist2", "axis label in millions vs XBRL dollars", "Scale must be normalized before comparing chart and filing facts."),
        ),
    )


def _task_id(ticker: str, family: str) -> str:
    return f"phase6:{ticker.lower()}:{family}"


def _evidence(
    task_id: str,
    suffix: str,
    source_type: str,
    modality: str,
    ticker: str,
    fiscal_period: str,
    role: str,
    metric: str,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        requirement_id=f"{task_id}:{suffix}",
        source_type=source_type,
        modality=modality,
        company_ticker=ticker,
        fiscal_period=fiscal_period,
        role=role,
        metric=metric,
    )


def _numeric_check(
    task_id: str,
    suffix: str,
    ticker: str,
    fiscal_period: str,
    metric: str,
    relation: str,
) -> NumericCheckSpec:
    return NumericCheckSpec(
        check_id=f"{task_id}:{suffix}",
        company_ticker=ticker,
        fiscal_period=fiscal_period,
        metric=metric,
        relation=relation,
    )


def _distractor(task_id: str, suffix: str, description: str, reason: str) -> KnownDistractor:
    return KnownDistractor(
        distractor_id=f"{task_id}:{suffix}",
        description=description,
        reason=reason,
    )
