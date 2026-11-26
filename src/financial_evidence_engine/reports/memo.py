"""Auditable due-diligence memo generation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Tuple

from financial_evidence_engine.reasoning.models import (
    ClaimVerificationResult,
    EvidenceReference,
    SubclaimVerification,
    ValidatorCheck,
    Verdict,
)


SECTION_NAMES: Tuple[str, ...] = (
    "Executive summary",
    "Key claims",
    "Evidence table",
    "Numeric reconciliation",
    "Cross-document contradictions",
    "Risk flags",
    "Unsupported or weakly supported claims",
    "Confidence and limitations",
)


@dataclass(frozen=True)
class MemoClaim:
    """Claim-level memo row."""

    claim_id: str
    claim_text: str
    verdict: str
    confidence: Decimal

    def to_dict(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "verdict": self.verdict,
            "confidence": str(self.confidence),
        }


@dataclass(frozen=True)
class MemoConclusion:
    """Conclusion with explicit audit trace."""

    conclusion_id: str
    claim_id: str
    subclaim_id: str
    conclusion: str
    verdict: str
    citation: str
    source_document: str
    page_or_section: str
    metric: Optional[str]
    period: str
    validator_result: str
    evidence_summary: str
    inference: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "conclusion_id": self.conclusion_id,
            "claim_id": self.claim_id,
            "subclaim_id": self.subclaim_id,
            "conclusion": self.conclusion,
            "verdict": self.verdict,
            "citation": self.citation,
            "source_document": self.source_document,
            "page_or_section": self.page_or_section,
            "metric": self.metric,
            "period": self.period,
            "validator_result": self.validator_result,
            "evidence_summary": self.evidence_summary,
            "inference": self.inference,
        }


@dataclass(frozen=True)
class EvidenceTableRow:
    """Evidence table row traceable to a source span."""

    evidence_id: str
    citation: str
    source_document: str
    page_or_section: str
    company_ticker: str
    metric: Optional[str]
    period: str
    raw_text: str
    numeric_value: Optional[Decimal]
    currency: Optional[str]
    validator_results: Tuple[str, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "citation": self.citation,
            "source_document": self.source_document,
            "page_or_section": self.page_or_section,
            "company_ticker": self.company_ticker,
            "metric": self.metric,
            "period": self.period,
            "raw_text": self.raw_text,
            "numeric_value": str(self.numeric_value) if self.numeric_value is not None else None,
            "currency": self.currency,
            "validator_results": list(self.validator_results),
        }


@dataclass(frozen=True)
class NumericReconciliationRow:
    """Recomputable numeric reconciliation row."""

    claim_id: str
    subclaim_id: str
    metric: Optional[str]
    period: str
    expected_value: Optional[Decimal]
    observed_value: Optional[Decimal]
    difference: Optional[Decimal]
    currency: Optional[str]
    validator_result: str
    recomputable: bool
    citation: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim_id,
            "subclaim_id": self.subclaim_id,
            "metric": self.metric,
            "period": self.period,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
            "observed_value": str(self.observed_value) if self.observed_value is not None else None,
            "difference": str(self.difference) if self.difference is not None else None,
            "currency": self.currency,
            "validator_result": self.validator_result,
            "recomputable": self.recomputable,
            "citation": self.citation,
        }


@dataclass(frozen=True)
class MemoIssue:
    """Explicit issue or limitation row."""

    issue_id: str
    issue_type: str
    claim_id: str
    subclaim_id: str
    description: str
    validator_result: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "claim_id": self.claim_id,
            "subclaim_id": self.subclaim_id,
            "description": self.description,
            "validator_result": self.validator_result,
        }


@dataclass(frozen=True)
class DueDiligenceMemo:
    """Auditable due-diligence memo artifact."""

    memo_id: str
    title: str
    executive_summary: Mapping[str, object]
    key_claims: Tuple[MemoClaim, ...]
    evidence_table: Tuple[EvidenceTableRow, ...]
    numeric_reconciliation: Tuple[NumericReconciliationRow, ...]
    cross_document_contradictions: Tuple[MemoIssue, ...]
    risk_flags: Tuple[MemoIssue, ...]
    unsupported_or_weakly_supported_claims: Tuple[MemoIssue, ...]
    confidence_and_limitations: Tuple[str, ...]
    conclusions: Tuple[MemoConclusion, ...]
    section_names: Tuple[str, ...] = SECTION_NAMES

    def to_dict(self) -> Mapping[str, object]:
        return {
            "memo_id": self.memo_id,
            "title": self.title,
            "section_names": list(self.section_names),
            "executive_summary": dict(self.executive_summary),
            "key_claims": [claim.to_dict() for claim in self.key_claims],
            "evidence_table": [row.to_dict() for row in self.evidence_table],
            "numeric_reconciliation": [row.to_dict() for row in self.numeric_reconciliation],
            "cross_document_contradictions": [
                issue.to_dict() for issue in self.cross_document_contradictions
            ],
            "risk_flags": [issue.to_dict() for issue in self.risk_flags],
            "unsupported_or_weakly_supported_claims": [
                issue.to_dict() for issue in self.unsupported_or_weakly_supported_claims
            ],
            "confidence_and_limitations": list(self.confidence_and_limitations),
            "conclusions": [conclusion.to_dict() for conclusion in self.conclusions],
        }

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        lines.extend(
            [
                "## Executive summary",
                f"- Overall verdict: {self.executive_summary['overall_verdict']}",
                f"- Claim count: {self.executive_summary['claim_count']}",
                "",
                "## Key claims",
            ]
        )
        for claim in self.key_claims:
            lines.append(f"- {claim.claim_id}: {claim.verdict} ({claim.confidence})")
        lines.extend(["", "## Evidence table"])
        for row in self.evidence_table:
            lines.append(
                f"- {row.citation}: {row.metric} {row.period} "
                f"{_decimal_or_blank(row.numeric_value)} {row.currency or ''}".strip()
            )
        lines.extend(["", "## Numeric reconciliation"])
        for row in self.numeric_reconciliation:
            lines.append(
                f"- {row.metric} {row.period}: expected={_decimal_or_blank(row.expected_value)} "
                f"observed={_decimal_or_blank(row.observed_value)} difference={_decimal_or_blank(row.difference)} "
                f"validator={row.validator_result}"
            )
        lines.extend(["", "## Cross-document contradictions"])
        lines.extend(_issue_lines(self.cross_document_contradictions))
        lines.extend(["", "## Risk flags"])
        lines.extend(_issue_lines(self.risk_flags))
        lines.extend(["", "## Unsupported or weakly supported claims"])
        lines.extend(_issue_lines(self.unsupported_or_weakly_supported_claims))
        lines.extend(["", "## Confidence and limitations"])
        for limitation in self.confidence_and_limitations:
            lines.append(f"- {limitation}")
        lines.extend(["", "## Conclusions"])
        for conclusion in self.conclusions:
            lines.append(f"- {conclusion.conclusion}")
            lines.append(f"  Citation: {conclusion.citation}")
            lines.append(f"  Evidence summary: {conclusion.evidence_summary}")
            lines.append(f"  Inference: {conclusion.inference}")
        return "\n".join(lines).rstrip() + "\n"


def build_due_diligence_memo(
    memo_id: str,
    title: str,
    claim_results: Iterable[ClaimVerificationResult],
) -> DueDiligenceMemo:
    """Build an auditable memo from claim verification results."""

    results = tuple(claim_results)
    key_claims = tuple(_key_claim(result) for result in results)
    conclusions = tuple(
        conclusion
        for result in results
        for conclusion in _conclusions_for_result(result)
    )
    evidence_table = tuple(
        row
        for result in results
        for row in _evidence_rows_for_result(result)
    )
    numeric_reconciliation = tuple(
        row
        for result in results
        for row in _numeric_rows_for_result(result)
    )
    issues = tuple(
        issue
        for result in results
        for issue in _issues_for_result(result)
    )
    contradictions = tuple(issue for issue in issues if issue.issue_type == "contradiction")
    unsupported = tuple(
        issue
        for issue in issues
        if issue.issue_type in {"insufficient_evidence", "weak_support"}
    )
    risk_flags = tuple(issue for issue in issues if issue.issue_type in {"validator_failure", "contradiction"})
    overall_verdict = _roll_up_verdict(tuple(result.verdict for result in results))
    limitations = _limitations(results, unsupported)
    return DueDiligenceMemo(
        memo_id=memo_id,
        title=title,
        executive_summary={
            "overall_verdict": overall_verdict,
            "claim_count": len(results),
            "evidence_count": len(evidence_table),
            "unresolved_issue_count": len(unsupported),
        },
        key_claims=key_claims,
        evidence_table=evidence_table,
        numeric_reconciliation=numeric_reconciliation,
        cross_document_contradictions=contradictions,
        risk_flags=risk_flags,
        unsupported_or_weakly_supported_claims=unsupported,
        confidence_and_limitations=limitations,
        conclusions=conclusions,
    )


def _key_claim(result: ClaimVerificationResult) -> MemoClaim:
    return MemoClaim(
        claim_id=result.claim.claim_id,
        claim_text=result.claim.text,
        verdict=result.verdict,
        confidence=result.confidence,
    )


def _conclusions_for_result(result: ClaimVerificationResult) -> Tuple[MemoConclusion, ...]:
    conclusions = []
    for index, subclaim_result in enumerate(result.subclaim_results, start=1):
        evidence = _first_evidence(subclaim_result)
        citation = _citation_for_evidence(evidence)
        conclusions.append(
            MemoConclusion(
                conclusion_id=f"{result.claim.claim_id}:conclusion:{index}",
                claim_id=result.claim.claim_id,
                subclaim_id=subclaim_result.subclaim.subclaim_id,
                conclusion=f"{subclaim_result.subclaim.text} -> {subclaim_result.verdict}",
                verdict=subclaim_result.verdict,
                citation=citation,
                source_document=evidence.document_id if evidence else "",
                page_or_section=evidence.page_or_section if evidence else "",
                metric=subclaim_result.subclaim.metric or (evidence.normalized_metric if evidence else None),
                period=subclaim_result.subclaim.fiscal_period,
                validator_result=_validator_result(subclaim_result.checks),
                evidence_summary=evidence.raw_text if evidence else "No selected evidence.",
                inference=_inference_for_subclaim(subclaim_result),
            )
        )
    return tuple(conclusions)


def _evidence_rows_for_result(result: ClaimVerificationResult) -> Tuple[EvidenceTableRow, ...]:
    rows = []
    seen = set()
    for subclaim_result in result.subclaim_results:
        validator_results = _validator_results_for_rows(subclaim_result.checks)
        for evidence in subclaim_result.evidence:
            if evidence.evidence_id in seen:
                continue
            seen.add(evidence.evidence_id)
            rows.append(
                EvidenceTableRow(
                    evidence_id=evidence.evidence_id,
                    citation=_citation_for_evidence(evidence),
                    source_document=evidence.document_id,
                    page_or_section=evidence.page_or_section,
                    company_ticker=evidence.company_ticker,
                    metric=evidence.normalized_metric,
                    period=evidence.fiscal_period,
                    raw_text=evidence.raw_text,
                    numeric_value=evidence.numeric_value,
                    currency=evidence.currency,
                    validator_results=validator_results,
                )
            )
    return tuple(rows)


def _numeric_rows_for_result(result: ClaimVerificationResult) -> Tuple[NumericReconciliationRow, ...]:
    rows = []
    for subclaim_result in result.subclaim_results:
        evidence = _first_evidence(subclaim_result)
        observed_value = evidence.numeric_value if evidence else None
        expected_value = subclaim_result.subclaim.expected_value
        difference = (
            observed_value - expected_value
            if observed_value is not None and expected_value is not None
            else None
        )
        validator_result = _check_status(subclaim_result.checks, "numeric_reconciliation")
        rows.append(
            NumericReconciliationRow(
                claim_id=result.claim.claim_id,
                subclaim_id=subclaim_result.subclaim.subclaim_id,
                metric=subclaim_result.subclaim.metric or (evidence.normalized_metric if evidence else None),
                period=subclaim_result.subclaim.fiscal_period,
                expected_value=expected_value,
                observed_value=observed_value,
                difference=difference,
                currency=subclaim_result.subclaim.expected_currency or (evidence.currency if evidence else None),
                validator_result=validator_result,
                recomputable=expected_value is not None and observed_value is not None,
                citation=_citation_for_evidence(evidence),
            )
        )
    return tuple(rows)


def _issues_for_result(result: ClaimVerificationResult) -> Tuple[MemoIssue, ...]:
    issues = []
    for index, subclaim_result in enumerate(result.subclaim_results, start=1):
        if not subclaim_result.evidence:
            issues.append(
                MemoIssue(
                    issue_id=f"{subclaim_result.subclaim.subclaim_id}:insufficient",
                    issue_type="insufficient_evidence",
                    claim_id=result.claim.claim_id,
                    subclaim_id=subclaim_result.subclaim.subclaim_id,
                    description="No selected evidence was available for this subclaim.",
                    validator_result=_validator_result(subclaim_result.checks),
                )
            )
        if subclaim_result.verdict == Verdict.CONTRADICT:
            issues.append(
                MemoIssue(
                    issue_id=f"{subclaim_result.subclaim.subclaim_id}:contradiction:{index}",
                    issue_type="contradiction",
                    claim_id=result.claim.claim_id,
                    subclaim_id=subclaim_result.subclaim.subclaim_id,
                    description="Validator results contradict the claim.",
                    validator_result=_validator_result(subclaim_result.checks),
                )
            )
        for check in subclaim_result.checks:
            if check.status == "fail" and check.name not in {"evidence_selection", "numeric_reconciliation"}:
                issues.append(
                    MemoIssue(
                        issue_id=f"{subclaim_result.subclaim.subclaim_id}:{check.name}",
                        issue_type="validator_failure",
                        claim_id=result.claim.claim_id,
                        subclaim_id=subclaim_result.subclaim.subclaim_id,
                        description=check.message,
                        validator_result=f"{check.name}:{check.status}",
                    )
                )
    return tuple(issues)


def _limitations(
    results: Tuple[ClaimVerificationResult, ...],
    unsupported: Tuple[MemoIssue, ...],
) -> Tuple[str, ...]:
    limitations = [
        "Evidence and inference are separated; conclusions depend on validator-readable evidence rows.",
        "Numeric conclusions are recomputable only when both expected and observed values are present.",
    ]
    if unsupported:
        limitations.append("Unresolved issues remain for claims with insufficient selected evidence.")
    if any(result.verdict == Verdict.CONTRADICT for result in results):
        limitations.append("Contradictions are reported from failed validator checks and should be reviewed.")
    return tuple(limitations)


def _first_evidence(subclaim_result: SubclaimVerification) -> Optional[EvidenceReference]:
    if not subclaim_result.evidence:
        return None
    return subclaim_result.evidence[0]


def _citation_for_evidence(evidence: Optional[EvidenceReference]) -> str:
    if evidence is None:
        return ""
    return f"{evidence.document_id}#{evidence.source_span_label}"


def _validator_results_for_rows(checks: Tuple[ValidatorCheck, ...]) -> Tuple[str, ...]:
    return tuple(f"{check.name}:{check.status}" for check in checks)


def _validator_result(checks: Tuple[ValidatorCheck, ...]) -> str:
    return "; ".join(_validator_results_for_rows(checks))


def _check_status(checks: Tuple[ValidatorCheck, ...], name: str) -> str:
    for check in checks:
        if check.name == name:
            return f"{check.name}:{check.status}"
    return f"{name}:skip"


def _inference_for_subclaim(subclaim_result: SubclaimVerification) -> str:
    if subclaim_result.verdict == Verdict.SUPPORT:
        return "Inference follows from passing citation, period, source, and numeric validator checks."
    if subclaim_result.verdict == Verdict.CONTRADICT:
        return "Inference follows from one or more failed validator checks."
    return "Inference is limited because required evidence was not selected."


def _roll_up_verdict(verdicts: Tuple[str, ...]) -> str:
    if any(verdict == Verdict.CONTRADICT for verdict in verdicts):
        return Verdict.CONTRADICT
    if any(verdict == Verdict.INSUFFICIENT for verdict in verdicts):
        return Verdict.INSUFFICIENT
    return Verdict.SUPPORT


def _issue_lines(issues: Tuple[MemoIssue, ...]) -> list:
    if not issues:
        return ["- None"]
    return [f"- {issue.issue_type}: {issue.description}" for issue in issues]


def _decimal_or_blank(value: Optional[Decimal]) -> str:
    return str(value) if value is not None else ""
