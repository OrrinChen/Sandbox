"""Narrative and causal claim verification for financial due diligence."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Optional, Tuple

from financial_evidence_engine.reasoning.models import CheckStatus, ValidatorCheck


class ClaimType:
    """Phase 14 narrative/causal claim type labels."""

    NUMERIC_TREND = "numeric_trend_claim"
    SEGMENT_CONTRIBUTION = "segment_contribution_claim"
    CAUSAL_ATTRIBUTION = "causal_attribution_claim"
    MANAGEMENT_GUIDANCE = "management_guidance_claim"
    RISK_FACTOR_CHANGE = "risk_factor_change_claim"
    DECK_NARRATIVE = "deck_narrative_claim"


class PartialVerdict:
    """Partial verdict labels for narrative and causal verification."""

    SUPPORT_NUMERIC_ONLY = "support_numeric_only"
    SUPPORT_NARRATIVE = "support_narrative"
    CONTRADICT_NUMERIC = "contradict_numeric"
    CONTRADICT_NARRATIVE = "contradict_narrative"
    INSUFFICIENT_CAUSAL_SUPPORT = "insufficient_causal_support"


@dataclass(frozen=True)
class NarrativeEvidenceFinding:
    """One validator-readable finding used by Phase 14 checks."""

    finding_id: str
    category: str
    text: str
    status: str
    source_type: str
    metric: Optional[str] = None

    def to_dict(self) -> Mapping[str, object]:
        return {
            "finding_id": self.finding_id,
            "category": self.category,
            "text": self.text,
            "status": self.status,
            "source_type": self.source_type,
            "metric": self.metric,
        }


@dataclass(frozen=True)
class NarrativeCausalTask:
    """One Phase 14 narrative or causal due-diligence task."""

    task_id: str
    claim_type: str
    claim_text: str
    company_ticker: str
    fiscal_period: str
    expected_partial_verdict: str
    findings: Tuple[NarrativeEvidenceFinding, ...]
    supported_inferences: Tuple[str, ...]
    unsupported_causal_attributions: Tuple[str, ...]
    ordinary_rag_verdict: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "claim_type": self.claim_type,
            "claim_text": self.claim_text,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "expected_partial_verdict": self.expected_partial_verdict,
            "findings": [finding.to_dict() for finding in self.findings],
            "supported_inferences": list(self.supported_inferences),
            "unsupported_causal_attributions": list(self.unsupported_causal_attributions),
            "ordinary_rag_verdict": self.ordinary_rag_verdict,
        }


@dataclass(frozen=True)
class NarrativeCausalTaskSet:
    """A deterministic Phase 14 task set."""

    task_set_id: str
    version: str
    tasks: Tuple[NarrativeCausalTask, ...]

    def task_by_id(self, task_id: str) -> NarrativeCausalTask:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(f"narrative causal task not found: {task_id}")

    def summary(self) -> Mapping[str, object]:
        return {
            "task_set_id": self.task_set_id,
            "version": self.version,
            "task_count": len(self.tasks),
            "claim_types": dict(sorted(Counter(task.claim_type for task in self.tasks).items())),
            "expected_partial_verdicts": dict(
                sorted(Counter(task.expected_partial_verdict for task in self.tasks).items())
            ),
        }

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_set_id": self.task_set_id,
            "version": self.version,
            "summary": self.summary(),
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class NarrativeCausalVerificationResult:
    """Phase 14 result with facts, inference, and causal support separated."""

    task: NarrativeCausalTask
    final_verdict: str
    numeric_verdict: str
    evidence_supported_facts: Tuple[str, ...]
    inferences: Tuple[str, ...]
    unsupported_causal_attributions: Tuple[str, ...]
    validator_checks: Tuple[ValidatorCheck, ...]
    ordinary_rag_verdict: str

    def validator_status(self, check_name: str) -> str:
        for check in self.validator_checks:
            if check.name == check_name:
                return check.status
        return CheckStatus.SKIP

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task": self.task.to_dict(),
            "final_verdict": self.final_verdict,
            "numeric_verdict": self.numeric_verdict,
            "evidence_supported_facts": list(self.evidence_supported_facts),
            "inferences": list(self.inferences),
            "unsupported_causal_attributions": list(self.unsupported_causal_attributions),
            "validator_checks": [check.to_dict() for check in self.validator_checks],
            "ordinary_rag_verdict": self.ordinary_rag_verdict,
        }


class NarrativeCausalVerifier:
    """Verify narrative and causal claims with explicit partial verdicts."""

    def verify(self, task: NarrativeCausalTask) -> NarrativeCausalVerificationResult:
        checks = _validator_checks(task.findings)
        numeric_verdict = _numeric_verdict(checks)
        final_verdict = _final_verdict(checks)
        supported_facts = tuple(
            finding.text
            for finding in task.findings
            if finding.category in {"numeric_trend", "segment_contribution", "guidance", "risk_factor", "deck_metric"}
            and finding.status == CheckStatus.PASS
        )
        unsupported_causal = tuple(task.unsupported_causal_attributions)
        if _status(checks, "causal_support") == CheckStatus.FAIL and not unsupported_causal:
            unsupported_causal = ("Causal wording lacks direct validator-readable evidence.",)
        return NarrativeCausalVerificationResult(
            task=task,
            final_verdict=final_verdict,
            numeric_verdict=numeric_verdict,
            evidence_supported_facts=supported_facts,
            inferences=tuple(task.supported_inferences),
            unsupported_causal_attributions=unsupported_causal,
            validator_checks=checks,
            ordinary_rag_verdict=task.ordinary_rag_verdict,
        )


@dataclass(frozen=True)
class NarrativeCausalMemo:
    """Memo section that separates facts, inference, and unsupported causality."""

    memo_id: str
    title: str
    evidence_supported_numeric_trends: Tuple[str, ...]
    inferences: Tuple[str, ...]
    unsupported_causal_attributions: Tuple[str, ...]
    section_names: Tuple[str, ...] = (
        "Evidence-supported numeric trend",
        "Inference",
        "Unsupported causal attribution",
    )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "memo_id": self.memo_id,
            "title": self.title,
            "section_names": list(self.section_names),
            "evidence_supported_numeric_trends": list(self.evidence_supported_numeric_trends),
            "inferences": list(self.inferences),
            "unsupported_causal_attributions": list(self.unsupported_causal_attributions),
        }

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        lines.extend(["## Evidence-supported numeric trend"])
        lines.extend(_bullet_lines(self.evidence_supported_numeric_trends))
        lines.extend(["", "## Inference"])
        lines.extend(_bullet_lines(self.inferences))
        lines.extend(["", "## Unsupported causal attribution"])
        lines.extend(_bullet_lines(self.unsupported_causal_attributions))
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class NarrativeOverclaimExample:
    """One case where ordinary RAG over-supports narrative or causal wording."""

    task_id: str
    claim_text: str
    ordinary_rag_verdict: str
    validator_gated_verdict: str
    failure_reason: str

    def to_dict(self) -> Mapping[str, str]:
        return {
            "task_id": self.task_id,
            "claim_text": self.claim_text,
            "ordinary_rag_verdict": self.ordinary_rag_verdict,
            "validator_gated_verdict": self.validator_gated_verdict,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class NarrativeCausalReport:
    """Phase 14 report for partial verdicts and RAG overclaim failures."""

    task_count: int
    partial_verdict_counts: Mapping[str, int]
    ordinary_rag_overclaim_cases: int
    ordinary_rag_overclaim_rate: Decimal
    overclaim_examples: Tuple[NarrativeOverclaimExample, ...]
    memo: NarrativeCausalMemo

    def to_dict(self) -> Mapping[str, object]:
        return {
            "task_count": self.task_count,
            "partial_verdict_counts": dict(self.partial_verdict_counts),
            "ordinary_rag_overclaim_cases": self.ordinary_rag_overclaim_cases,
            "ordinary_rag_overclaim_rate": str(self.ordinary_rag_overclaim_rate),
            "overclaim_examples": [example.to_dict() for example in self.overclaim_examples],
            "memo": self.memo.to_dict(),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Narrative and Causal Claim Verification",
            "",
            "This report shows why ordinary RAG overclaims causal narratives: it treats numeric support or management language as enough to support causal wording.",
            "",
            f"- Tasks: `{self.task_count}`",
            f"- Ordinary RAG overclaim cases: `{self.ordinary_rag_overclaim_cases}`",
            f"- Ordinary RAG overclaim rate: `{self.ordinary_rag_overclaim_rate}`",
            "",
            "## Partial Verdict Counts",
            "",
            "| Verdict | Count |",
            "| --- | ---: |",
        ]
        for verdict, count in sorted(self.partial_verdict_counts.items()):
            lines.append(f"| `{verdict}` | {count} |")
        lines.extend(["", "## Overclaim Examples", "", "| Task | Ordinary RAG | Validator-gated | Failure reason |", "| --- | --- | --- | --- |"])
        for example in self.overclaim_examples:
            lines.append(
                f"| `{example.task_id}` | `{example.ordinary_rag_verdict}` | "
                f"`{example.validator_gated_verdict}` | {example.failure_reason} |"
            )
        lines.extend(["", "## Memo Separation", "", self.memo.to_markdown().rstrip()])
        return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True)
class NarrativeCausalArtifactManifest:
    """Files written for Phase 14 narrative/causal artifacts."""

    json_artifact: Path
    markdown_artifact: Path

    def to_dict(self) -> Mapping[str, str]:
        return {
            "json_artifact": str(self.json_artifact),
            "markdown_artifact": str(self.markdown_artifact),
        }


def build_narrative_causal_task_set() -> NarrativeCausalTaskSet:
    """Build the deterministic Phase 14 narrative/causal task set."""

    return NarrativeCausalTaskSet(
        task_set_id="phase14_narrative_causal_due_diligence",
        version="2026-05-02",
        tasks=(
            _task(
                "phase14:nvda:data_center_driver",
                ClaimType.CAUSAL_ATTRIBUTION,
                "NVIDIA's FY2024 revenue growth was mainly driven by data center demand.",
                "NVDA",
                PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT,
                (
                    _finding("numeric_trend", "NVIDIA FY2024 total revenue grew.", "pass", "sec_xbrl_companyfacts", "revenue"),
                    _finding("segment_contribution", "Data center revenue accounted for the dominant growth contribution.", "pass", "sec_filing", "data_center_revenue"),
                    _finding("causal_support", "No direct demand evidence ties customer demand to the full revenue increase.", "fail", "transcript"),
                ),
                ("Data center contribution is a supported inference from segment share evidence.",),
                ("Demand was the primary causal driver, but no direct demand evidence is present.",),
            ),
            _task(
                "phase14:msft:cloud_offset",
                ClaimType.SEGMENT_CONTRIBUTION,
                "Microsoft's FY2024 cloud growth offset weakness in other segments.",
                "MSFT",
                PartialVerdict.SUPPORT_NARRATIVE,
                (
                    _finding("numeric_trend", "Microsoft cloud revenue grew in FY2024.", "pass", "sec_filing", "cloud_revenue"),
                    _finding("segment_contribution", "Cloud growth exceeded the reported drag from weaker segments.", "pass", "sec_filing", "segment_contribution"),
                    _finding("narrative_support", "Management discussion explicitly frames cloud as the offsetting segment.", "pass", "transcript"),
                ),
                ("Cloud offset is supported by segment contribution and management discussion.",),
                (),
            ),
            _task(
                "phase14:aapl:services_margin",
                ClaimType.CAUSAL_ATTRIBUTION,
                "Apple's FY2024 margin improvement came from Services mix rather than one-time cost cuts.",
                "AAPL",
                PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT,
                (
                    _finding("numeric_trend", "Apple FY2024 operating margin improved.", "pass", "sec_xbrl_companyfacts", "operating_margin"),
                    _finding("segment_contribution", "Services revenue mix increased.", "pass", "sec_filing", "segment_revenue"),
                    _finding("causal_support", "No filing bridge proves Services mix, rather than one-time costs, caused the improvement.", "fail", "sec_filing"),
                ),
                ("Services mix is a plausible inference, but not a fully supported causal conclusion.",),
                ("Services mix causality is not directly supported against the one-time cost-cut alternative.",),
            ),
            _task(
                "phase14:amzn:aws_offset",
                ClaimType.NUMERIC_TREND,
                "Amazon's FY2024 AWS growth was strong while retail margins remained pressured.",
                "AMZN",
                PartialVerdict.SUPPORT_NUMERIC_ONLY,
                (
                    _finding("numeric_trend", "AWS revenue grew in FY2024.", "pass", "sec_filing", "cloud_revenue"),
                    _finding("numeric_trend", "Retail margin pressure remained visible.", "pass", "sec_filing", "operating_margin"),
                    _finding("narrative_support", "No cited narrative establishes a full offset relationship.", "skip", "transcript"),
                ),
                ("AWS growth and retail pressure are both supported numeric facts.",),
                (),
                ordinary_rag_verdict=PartialVerdict.SUPPORT_NARRATIVE,
            ),
            _task(
                "phase14:jpm:rate_benefit",
                ClaimType.CAUSAL_ATTRIBUTION,
                "JPMorgan's FY2024 earnings strength was primarily caused by net interest income rather than credit releases.",
                "JPM",
                PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT,
                (
                    _finding("numeric_trend", "JPMorgan FY2024 net income was strong.", "pass", "sec_xbrl_companyfacts", "net_income"),
                    _finding("segment_contribution", "Net interest income increased.", "pass", "sec_filing", "net_interest_income"),
                    _finding("causal_support", "The record does not isolate net interest income as the primary cause over credit releases.", "fail", "sec_filing"),
                ),
                ("Net interest income contribution is supported as a component of earnings strength.",),
                ("Primary-cause wording is unsupported without a driver attribution bridge.",),
            ),
            _task(
                "phase14:tsla:margin_improvement",
                ClaimType.NUMERIC_TREND,
                "Tesla's FY2024 operating margin improved versus FY2023.",
                "TSLA",
                PartialVerdict.CONTRADICT_NUMERIC,
                (
                    _finding("numeric_trend", "Tesla FY2024 operating margin declined versus FY2023.", "fail", "sec_xbrl_companyfacts", "operating_margin"),
                    _finding("narrative_support", "Management language discusses efficiency, but numeric margin trend contradicts the claim.", "fail", "transcript"),
                ),
                (),
                (),
            ),
            _task(
                "phase14:meta:risk_reduced",
                ClaimType.RISK_FACTOR_CHANGE,
                "Meta's FY2024 AI infrastructure risk exposure materially decreased.",
                "META",
                PartialVerdict.CONTRADICT_NARRATIVE,
                (
                    _finding("risk_factor", "FY2024 risk factors expanded AI infrastructure and capex exposure language.", "fail", "sec_filing", "risk_exposure"),
                    _finding("narrative_support", "Transcript optimism does not override expanded filed risk language.", "fail", "transcript"),
                ),
                (),
                (),
            ),
            _task(
                "phase14:nflx:guidance_actuals",
                ClaimType.MANAGEMENT_GUIDANCE,
                "Netflix's FY2024 revenue landed within management's cited guidance range.",
                "NFLX",
                PartialVerdict.SUPPORT_NARRATIVE,
                (
                    _finding("numeric_trend", "Reported FY2024 revenue is inside the cited range.", "pass", "sec_xbrl_companyfacts", "revenue"),
                    _finding("guidance", "Management guidance range is contemporaneous with the period.", "pass", "transcript", "revenue_guidance"),
                    _finding("narrative_support", "Guidance-to-actual comparison is directly supported.", "pass", "analyst_estimates", "revenue_estimate"),
                ),
                ("The guidance narrative is supported because actuals reconcile to the cited range.",),
                (),
            ),
            _task(
                "phase14:wmt:deck_margin",
                ClaimType.DECK_NARRATIVE,
                "Walmart's FY2024 investor deck showed margin progress driven by automation.",
                "WMT",
                PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT,
                (
                    _finding("deck_metric", "Deck margin chart shows margin progress.", "pass", "investor_deck", "operating_margin"),
                    _finding("numeric_trend", "Filing operating margin reconciles to the deck direction.", "pass", "sec_xbrl_companyfacts", "operating_margin"),
                    _finding("causal_support", "Automation driver is not directly tied to the margin change.", "fail", "investor_deck"),
                ),
                ("Deck chart and filing metric support margin progress.",),
                ("Automation-driven causality is unsupported by the extracted deck evidence.",),
            ),
            _task(
                "phase14:googl:guidance_ai",
                ClaimType.MANAGEMENT_GUIDANCE,
                "Alphabet's FY2024 cloud guidance improved because AI demand accelerated.",
                "GOOGL",
                PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT,
                (
                    _finding("guidance", "Cloud guidance improved in management commentary.", "pass", "transcript", "revenue_guidance"),
                    _finding("numeric_trend", "Cloud revenue grew in FY2024.", "pass", "sec_filing", "cloud_revenue"),
                    _finding("causal_support", "AI demand acceleration is discussed but not reconciled as the cause of guidance improvement.", "fail", "transcript"),
                ),
                ("Cloud guidance and cloud revenue growth are supported.",),
                ("AI demand as the cause of guidance improvement remains insufficiently supported.",),
            ),
        ),
    )


def build_narrative_causal_memo(
    results: Iterable[NarrativeCausalVerificationResult],
) -> NarrativeCausalMemo:
    """Build a memo view that separates facts, inference, and causal gaps."""

    result_tuple = tuple(results)
    return NarrativeCausalMemo(
        memo_id="memo:phase14_narrative_causal",
        title="Narrative and Causal Claim Verification Memo",
        evidence_supported_numeric_trends=_unique(
            fact
            for result in result_tuple
            for fact in result.evidence_supported_facts
        ),
        inferences=_unique(
            inference
            for result in result_tuple
            for inference in result.inferences
        ),
        unsupported_causal_attributions=_unique(
            attribution
            for result in result_tuple
            for attribution in result.unsupported_causal_attributions
        ),
    )


def build_narrative_causal_report(
    task_set: Optional[NarrativeCausalTaskSet] = None,
) -> NarrativeCausalReport:
    """Build the Phase 14 narrative/causal verification report."""

    task_set = task_set or build_narrative_causal_task_set()
    verifier = NarrativeCausalVerifier()
    results = tuple(verifier.verify(task) for task in task_set.tasks)
    overclaim_examples = tuple(_overclaim_example(result) for result in results if _is_overclaim(result))
    return NarrativeCausalReport(
        task_count=len(results),
        partial_verdict_counts=dict(sorted(Counter(result.final_verdict for result in results).items())),
        ordinary_rag_overclaim_cases=len(overclaim_examples),
        ordinary_rag_overclaim_rate=(
            Decimal(len(overclaim_examples)) / Decimal(len(results))
            if results
            else Decimal("0")
        ),
        overclaim_examples=overclaim_examples,
        memo=build_narrative_causal_memo(results),
    )


def write_narrative_causal_artifacts(
    report: NarrativeCausalReport,
    experiments_dir: Path = Path("experiments/narrative_causal"),
    reports_dir: Path = Path("reports/narrative_causal"),
) -> NarrativeCausalArtifactManifest:
    """Write Phase 14 narrative/causal JSON and Markdown artifacts."""

    experiments_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = experiments_dir / "phase14_narrative_causal_report.json"
    markdown_path = reports_dir / "phase14_narrative_causal_report.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")
    return NarrativeCausalArtifactManifest(json_artifact=json_path, markdown_artifact=markdown_path)


def _task(
    task_id: str,
    claim_type: str,
    claim_text: str,
    company_ticker: str,
    expected_partial_verdict: str,
    findings: Tuple[NarrativeEvidenceFinding, ...],
    supported_inferences: Tuple[str, ...],
    unsupported_causal_attributions: Tuple[str, ...],
    ordinary_rag_verdict: str = PartialVerdict.SUPPORT_NARRATIVE,
) -> NarrativeCausalTask:
    return NarrativeCausalTask(
        task_id=task_id,
        claim_type=claim_type,
        claim_text=claim_text,
        company_ticker=company_ticker,
        fiscal_period="FY2024",
        expected_partial_verdict=expected_partial_verdict,
        findings=findings,
        supported_inferences=supported_inferences,
        unsupported_causal_attributions=unsupported_causal_attributions,
        ordinary_rag_verdict=ordinary_rag_verdict,
    )


def _finding(
    category: str,
    text: str,
    status: str,
    source_type: str,
    metric: Optional[str] = None,
) -> NarrativeEvidenceFinding:
    normalized_status = _normalize_status(status)
    return NarrativeEvidenceFinding(
        finding_id=f"{category}:{_stable_hash(text, source_type)}",
        category=category,
        text=text,
        status=normalized_status,
        source_type=source_type,
        metric=metric,
    )


def _validator_checks(findings: Tuple[NarrativeEvidenceFinding, ...]) -> Tuple[ValidatorCheck, ...]:
    check_names = (
        "numeric_trend",
        "segment_contribution",
        "guidance",
        "risk_factor",
        "deck_metric",
        "narrative_support",
        "causal_support",
    )
    checks = []
    for name in check_names:
        matching = tuple(finding for finding in findings if finding.category == name)
        if not matching:
            checks.append(_check(name, CheckStatus.SKIP, "No evidence finding required for this check."))
            continue
        statuses = {finding.status for finding in matching}
        if CheckStatus.FAIL in statuses:
            status = CheckStatus.FAIL
        elif statuses == {CheckStatus.SKIP}:
            status = CheckStatus.SKIP
        else:
            status = CheckStatus.PASS
        checks.append(_check(name, status, "; ".join(finding.text for finding in matching)))
    return tuple(checks)


def _numeric_verdict(checks: Tuple[ValidatorCheck, ...]) -> str:
    if _status(checks, "numeric_trend") == CheckStatus.FAIL:
        return PartialVerdict.CONTRADICT_NUMERIC
    if _status(checks, "numeric_trend") == CheckStatus.PASS:
        return PartialVerdict.SUPPORT_NUMERIC_ONLY
    return PartialVerdict.SUPPORT_NUMERIC_ONLY


def _final_verdict(checks: Tuple[ValidatorCheck, ...]) -> str:
    if _status(checks, "numeric_trend") == CheckStatus.FAIL:
        return PartialVerdict.CONTRADICT_NUMERIC
    if _status(checks, "risk_factor") == CheckStatus.FAIL or _status(checks, "narrative_support") == CheckStatus.FAIL:
        return PartialVerdict.CONTRADICT_NARRATIVE
    if _status(checks, "causal_support") == CheckStatus.FAIL:
        numeric_or_deck_supported = any(
            _status(checks, name) == CheckStatus.PASS
            for name in ("numeric_trend", "segment_contribution", "deck_metric", "guidance")
        )
        if numeric_or_deck_supported:
            return PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT
    if any(
        _status(checks, name) == CheckStatus.PASS
        for name in ("segment_contribution", "guidance", "deck_metric", "narrative_support")
    ):
        return PartialVerdict.SUPPORT_NARRATIVE
    return PartialVerdict.SUPPORT_NUMERIC_ONLY


def _status(checks: Tuple[ValidatorCheck, ...], name: str) -> str:
    for check in checks:
        if check.name == name:
            return check.status
    return CheckStatus.SKIP


def _check(name: str, status: str, message: str) -> ValidatorCheck:
    return ValidatorCheck(name=name, status=status, message=message)


def _normalize_status(status: str) -> str:
    if status == "pass":
        return CheckStatus.PASS
    if status == "fail":
        return CheckStatus.FAIL
    if status == "skip":
        return CheckStatus.SKIP
    raise ValueError(f"unsupported narrative finding status: {status}")


def _is_overclaim(result: NarrativeCausalVerificationResult) -> bool:
    return (
        result.ordinary_rag_verdict == PartialVerdict.SUPPORT_NARRATIVE
        and result.final_verdict != PartialVerdict.SUPPORT_NARRATIVE
    )


def _overclaim_example(result: NarrativeCausalVerificationResult) -> NarrativeOverclaimExample:
    if result.final_verdict == PartialVerdict.INSUFFICIENT_CAUSAL_SUPPORT:
        reason = "numeric or narrative evidence exists, but causal attribution is not directly supported"
    elif result.final_verdict == PartialVerdict.CONTRADICT_NUMERIC:
        reason = "ordinary RAG accepts narrative language despite a numeric contradiction"
    elif result.final_verdict == PartialVerdict.CONTRADICT_NARRATIVE:
        reason = "ordinary RAG accepts optimistic language despite contradictory filed narrative evidence"
    else:
        reason = "ordinary RAG overstates the level of support"
    return NarrativeOverclaimExample(
        task_id=result.task.task_id,
        claim_text=result.task.claim_text,
        ordinary_rag_verdict=result.ordinary_rag_verdict,
        validator_gated_verdict=result.final_verdict,
        failure_reason=reason,
    )


def _unique(values: Iterable[str]) -> Tuple[str, ...]:
    seen = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return tuple(unique_values)


def _bullet_lines(values: Tuple[str, ...]) -> list:
    if not values:
        return ["- None"]
    return [f"- {value}" for value in values]


def _stable_hash(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]
