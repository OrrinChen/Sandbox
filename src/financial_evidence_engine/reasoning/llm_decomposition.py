"""Validator-gated claim decomposition providers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping, Optional, Protocol, Sequence, Tuple

from financial_evidence_engine.bundled import RESOURCES
from financial_evidence_engine.reasoning.claim_decomposer import ClaimDecomposer
from financial_evidence_engine.reasoning.models import CheckStatus, Claim, Subclaim, ValidatorCheck


DEFAULT_RECORDED_LLM_FIXTURE = RESOURCES / "fixtures/llm_decompositions/recorded_claim_decompositions.json"

ALLOWED_TICKERS = {
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "JPM",
    "WMT",
    "TSLA",
    "NFLX",
}

ALLOWED_PERIODS = {
    "FY2022",
    "FY2023",
    "FY2024",
    "FY2025",
    "Q4 FY2024",
    "2024-FY",
}

ALLOWED_METRICS = {
    "revenue",
    "operating_income",
    "operating_expense",
    "operating_margin",
    "net_income",
    "risk_exposure",
    "revenue_guidance",
    "revenue_estimate",
    "cloud_revenue",
    "data_center_revenue",
    "segment_revenue",
    "segment_weakness",
    "segment_contribution",
    "offset_relationship",
    "causal_attribution",
    "one_time_item",
    "net_interest_income",
    "credit_loss_provision",
}


class DecompositionSchemaError(ValueError):
    """Raised when recorded LLM decomposition output does not match schema."""


class LiveLLMUnavailable(RuntimeError):
    """Raised when a live LLM decomposer is requested but unavailable."""


class ClaimDecompositionProvider(Protocol):
    """Provider interface for claim decomposition."""

    provider: str

    def decompose(
        self,
        claim_id: str,
        text: str,
        company_ticker: str,
        fiscal_period: str,
    ) -> "DecompositionTrace":
        """Return a validator-gated decomposition trace."""


@dataclass(frozen=True)
class DecompositionCandidate:
    """One candidate subclaim produced before validator gating."""

    text: str
    company_ticker: str
    fiscal_period: str
    metric: Optional[str] = None
    required_evidence_type: Optional[str] = None
    required_terms: Tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "DecompositionCandidate":
        required = ("text", "company_ticker", "fiscal_period")
        missing = [field for field in required if field not in payload]
        if missing:
            raise DecompositionSchemaError(f"subclaim missing required fields: {', '.join(missing)}")
        required_terms = payload.get("required_terms", ())
        if not isinstance(required_terms, list):
            raise DecompositionSchemaError("subclaim required_terms must be a list")
        return cls(
            text=_required_string(payload, "text"),
            company_ticker=_required_string(payload, "company_ticker"),
            fiscal_period=_required_string(payload, "fiscal_period"),
            metric=_optional_string(payload, "metric"),
            required_evidence_type=_optional_string(payload, "required_evidence_type"),
            required_terms=tuple(str(term) for term in required_terms),
        )

    def to_subclaim(self, claim_id: str, index: int) -> Subclaim:
        return Subclaim(
            subclaim_id=f"{claim_id}:{index + 1}",
            text=self.text,
            company_ticker=self.company_ticker,
            fiscal_period=self.fiscal_period,
            metric=self.metric,
            required_evidence_type=self.required_evidence_type,
            required_terms=self.required_terms,
        )

    def to_dict(self) -> Mapping[str, object]:
        return {
            "text": self.text,
            "company_ticker": self.company_ticker,
            "fiscal_period": self.fiscal_period,
            "metric": self.metric,
            "required_evidence_type": self.required_evidence_type,
            "required_terms": list(self.required_terms),
        }


@dataclass(frozen=True)
class DecompositionTrace:
    """Trace for schema validation, gating, and final claim decomposition."""

    provider: str
    claim: Claim
    schema_valid: bool
    accepted: bool
    candidate_count: int
    rejected_candidates: Tuple[DecompositionCandidate, ...]
    validator_checks: Tuple[ValidatorCheck, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "provider": self.provider,
            "claim": self.claim.to_dict(),
            "schema_valid": self.schema_valid,
            "accepted": self.accepted,
            "candidate_count": self.candidate_count,
            "rejected_candidates": [candidate.to_dict() for candidate in self.rejected_candidates],
            "validator_checks": [check.to_dict() for check in self.validator_checks],
        }


class ValidatorGate:
    """Reject LLM subclaims with hallucinated entity, period, or metric."""

    def __init__(
        self,
        allowed_tickers: Iterable[str] = ALLOWED_TICKERS,
        allowed_periods: Iterable[str] = ALLOWED_PERIODS,
        allowed_metrics: Iterable[str] = ALLOWED_METRICS,
    ) -> None:
        self.allowed_tickers = frozenset(allowed_tickers)
        self.allowed_periods = frozenset(allowed_periods)
        self.allowed_metrics = frozenset(allowed_metrics)

    def validate(
        self,
        claim_id: str,
        text: str,
        candidates: Sequence[DecompositionCandidate],
        provider: str = "validator_gate",
    ) -> DecompositionTrace:
        accepted_candidates = []
        rejected_candidates = []
        checks = []
        for candidate in candidates:
            candidate_checks = self._checks_for_candidate(candidate)
            checks.extend(candidate_checks)
            if all(check.status == CheckStatus.PASS for check in candidate_checks):
                accepted_candidates.append(candidate)
            else:
                rejected_candidates.append(candidate)

        claim = Claim(
            claim_id=claim_id,
            text=text,
            subclaims=tuple(
                candidate.to_subclaim(claim_id, index)
                for index, candidate in enumerate(accepted_candidates)
            ),
        )
        return DecompositionTrace(
            provider=provider,
            claim=claim,
            schema_valid=True,
            accepted=bool(accepted_candidates) and not rejected_candidates,
            candidate_count=len(candidates),
            rejected_candidates=tuple(rejected_candidates),
            validator_checks=tuple(checks),
        )

    def _checks_for_candidate(self, candidate: DecompositionCandidate) -> Tuple[ValidatorCheck, ...]:
        return (
            _check(
                name="entity_validation",
                passed=candidate.company_ticker in self.allowed_tickers,
                message=f"company_ticker={candidate.company_ticker}",
            ),
            _check(
                name="period_validation",
                passed=candidate.fiscal_period in self.allowed_periods,
                message=f"fiscal_period={candidate.fiscal_period}",
            ),
            _check(
                name="metric_validation",
                passed=candidate.metric is None or candidate.metric in self.allowed_metrics,
                message=f"metric={candidate.metric}",
            ),
        )


class RuleBasedClaimDecomposer:
    """Provider wrapper around the existing deterministic ClaimDecomposer."""

    provider = "rule_based"

    def __init__(self, gate: Optional[ValidatorGate] = None, decomposer: Optional[ClaimDecomposer] = None) -> None:
        self._gate = gate or ValidatorGate()
        self._decomposer = decomposer or ClaimDecomposer()

    def decompose(
        self,
        claim_id: str,
        text: str,
        company_ticker: str,
        fiscal_period: str,
    ) -> DecompositionTrace:
        claim = self._decomposer.decompose(claim_id, text, company_ticker, fiscal_period)
        candidates = tuple(
            DecompositionCandidate(
                text=subclaim.text,
                company_ticker=subclaim.company_ticker,
                fiscal_period=subclaim.fiscal_period,
                metric=subclaim.metric,
                required_evidence_type=subclaim.required_evidence_type,
                required_terms=subclaim.required_terms,
            )
            for subclaim in claim.subclaims
        )
        return self._gate.validate(claim_id, text, candidates, provider=self.provider)


class RecordedLLMClaimDecomposer:
    """Recorded LLM decomposition provider using local JSON fixtures."""

    provider = "recorded_llm"

    def __init__(self, fixture_path: Path = DEFAULT_RECORDED_LLM_FIXTURE, gate: Optional[ValidatorGate] = None) -> None:
        self.fixture_path = fixture_path
        self._gate = gate or ValidatorGate()

    def decompose_all(self) -> Tuple[DecompositionTrace, ...]:
        return tuple(self._trace_from_payload(payload) for payload in self._load_payloads())

    def decompose(
        self,
        claim_id: str,
        text: str,
        company_ticker: str,
        fiscal_period: str,
    ) -> DecompositionTrace:
        for payload in self._load_payloads():
            if (
                payload["claim_id"] == claim_id
                or (
                    payload["text"] == text
                    and payload["company_ticker"] == company_ticker
                    and payload["fiscal_period"] == fiscal_period
                )
            ):
                return self._trace_from_payload(payload)
        raise KeyError(f"recorded decomposition not found for {claim_id}")

    def _load_payloads(self) -> Tuple[Mapping[str, object], ...]:
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise DecompositionSchemaError("recorded LLM fixture must be a list")
        payloads = tuple(_validate_claim_payload(item) for item in raw)
        return payloads

    def _trace_from_payload(self, payload: Mapping[str, object]) -> DecompositionTrace:
        candidates = tuple(DecompositionCandidate.from_mapping(item) for item in payload["subclaims"])
        return self._gate.validate(
            claim_id=str(payload["claim_id"]),
            text=str(payload["text"]),
            candidates=candidates,
            provider=self.provider,
        )


class OptionalLiveLLMClaimDecomposer:
    """Optional live LLM decomposer placeholder, disabled by default."""

    provider = "live_llm"

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def is_available(self) -> bool:
        return False

    def unavailable_reason(self) -> str:
        if not self.enabled:
            return "Live LLM decomposer is disabled by default."
        return "No live LLM backend is configured."

    def decompose(
        self,
        claim_id: str,
        text: str,
        company_ticker: str,
        fiscal_period: str,
    ) -> DecompositionTrace:
        raise LiveLLMUnavailable(self.unavailable_reason())


@dataclass(frozen=True)
class DecompositionComparisonExample:
    """One rule-vs-recorded-LLM decomposition comparison row."""

    claim_id: str
    text: str
    rule_based_subclaims: int
    llm_subclaims: int
    rejected_subclaims: int

    def to_dict(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "rule_based_subclaims": self.rule_based_subclaims,
            "llm_subclaims": self.llm_subclaims,
            "rejected_subclaims": self.rejected_subclaims,
        }


@dataclass(frozen=True)
class DecompositionComparisonReport:
    """Report comparing deterministic and recorded LLM decomposition."""

    complex_claim_count: int
    rule_based_provider: str
    recorded_llm_provider: str
    rule_based_subclaim_count: int
    llm_subclaim_count: int
    rejected_subclaim_count: int
    examples: Tuple[DecompositionComparisonExample, ...]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "complex_claim_count": self.complex_claim_count,
            "rule_based_provider": self.rule_based_provider,
            "recorded_llm_provider": self.recorded_llm_provider,
            "rule_based_subclaim_count": self.rule_based_subclaim_count,
            "llm_subclaim_count": self.llm_subclaim_count,
            "rejected_subclaim_count": self.rejected_subclaim_count,
            "examples": [example.to_dict() for example in self.examples],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Validator-Gated LLM Claim Decomposition",
            "",
            f"- Complex claims: `{self.complex_claim_count}`",
            f"- Rule-based provider: `{self.rule_based_provider}`",
            f"- Recorded LLM provider: `{self.recorded_llm_provider}`",
            f"- Rule-based subclaims: `{self.rule_based_subclaim_count}`",
            f"- Recorded LLM subclaims: `{self.llm_subclaim_count}`",
            f"- Rejected recorded LLM subclaims: `{self.rejected_subclaim_count}`",
            "",
            "| Claim | Rule-based subclaims | Recorded LLM subclaims | Rejected subclaims |",
            "| --- | ---: | ---: | ---: |",
        ]
        for example in self.examples:
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"`{example.claim_id}`",
                        str(example.rule_based_subclaims),
                        str(example.llm_subclaims),
                        str(example.rejected_subclaims),
                    )
                )
                + " |"
            )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class DecompositionArtifactManifest:
    """Files written for the Phase 13 decomposition comparison report."""

    json_artifact: Path
    markdown_artifact: Path

    def to_dict(self) -> Mapping[str, str]:
        return {
            "json_artifact": str(self.json_artifact),
            "markdown_artifact": str(self.markdown_artifact),
        }


def build_decomposition_comparison_report(
    fixture_path: Path = DEFAULT_RECORDED_LLM_FIXTURE,
) -> DecompositionComparisonReport:
    """Compare rule-based and recorded-LLM decomposition over complex claims."""

    llm = RecordedLLMClaimDecomposer(fixture_path)
    rule_based = RuleBasedClaimDecomposer()
    llm_traces = llm.decompose_all()
    examples = []
    rule_total = 0
    llm_total = 0
    rejected_total = 0
    for llm_trace in llm_traces:
        rule_trace = rule_based.decompose(
            claim_id=llm_trace.claim.claim_id,
            text=llm_trace.claim.text,
            company_ticker=llm_trace.claim.subclaims[0].company_ticker,
            fiscal_period=llm_trace.claim.subclaims[0].fiscal_period,
        )
        rule_count = len(rule_trace.claim.subclaims)
        llm_count = len(llm_trace.claim.subclaims)
        rejected_count = len(llm_trace.rejected_candidates)
        rule_total += rule_count
        llm_total += llm_count
        rejected_total += rejected_count
        examples.append(
            DecompositionComparisonExample(
                claim_id=llm_trace.claim.claim_id,
                text=llm_trace.claim.text,
                rule_based_subclaims=rule_count,
                llm_subclaims=llm_count,
                rejected_subclaims=rejected_count,
            )
        )
    return DecompositionComparisonReport(
        complex_claim_count=len(llm_traces),
        rule_based_provider=rule_based.provider,
        recorded_llm_provider=llm.provider,
        rule_based_subclaim_count=rule_total,
        llm_subclaim_count=llm_total,
        rejected_subclaim_count=rejected_total,
        examples=tuple(examples),
    )


def write_decomposition_comparison_artifacts(
    report: DecompositionComparisonReport,
    experiments_dir: Path = Path("experiments/llm_decomposition"),
    reports_dir: Path = Path("reports/llm_decomposition"),
) -> DecompositionArtifactManifest:
    """Write Phase 13 JSON and Markdown decomposition comparison artifacts."""

    experiments_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = experiments_dir / "phase13_decomposition_comparison.json"
    markdown_path = reports_dir / "phase13_decomposition_comparison.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")
    return DecompositionArtifactManifest(
        json_artifact=json_path,
        markdown_artifact=markdown_path,
    )


def _validate_claim_payload(payload: object) -> Mapping[str, object]:
    if not isinstance(payload, dict):
        raise DecompositionSchemaError("recorded claim payload must be a mapping")
    required = ("claim_id", "text", "company_ticker", "fiscal_period", "subclaims")
    missing = [field for field in required if field not in payload]
    if missing:
        raise DecompositionSchemaError(f"recorded claim missing required fields: {', '.join(missing)}")
    _required_string(payload, "claim_id")
    _required_string(payload, "text")
    _required_string(payload, "company_ticker")
    _required_string(payload, "fiscal_period")
    subclaims = payload["subclaims"]
    if not isinstance(subclaims, list) or not subclaims:
        raise DecompositionSchemaError("recorded claim subclaims must be a non-empty list")
    for subclaim in subclaims:
        DecompositionCandidate.from_mapping(subclaim)
    return payload


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DecompositionSchemaError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_string(payload: Mapping[str, object], field: str) -> Optional[str]:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DecompositionSchemaError(f"{field} must be a string when present")
    return value.strip() or None


def _check(name: str, passed: bool, message: str) -> ValidatorCheck:
    return ValidatorCheck(
        name=name,
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        message=message,
    )
