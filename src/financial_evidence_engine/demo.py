"""Local demo state and claim-verification helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional, Tuple

from financial_evidence_engine.bundled import RESOURCES
from financial_evidence_engine.data.models import DocumentMetadata
from financial_evidence_engine.evidence_graph import build_evidence_graph
from financial_evidence_engine.extraction.models import EvidenceUnit, SourceSpan
from financial_evidence_engine.reasoning import ClaimDecomposer, ClaimVerifier
from financial_evidence_engine.reports import build_due_diligence_memo


DEMO_PAGES: Tuple[str, ...] = (
    "Claim verification demo",
    "Case study browser",
    "Retrieval method comparison",
    "Memo view",
)


@dataclass(frozen=True)
class DemoState:
    """All local artifacts needed by the lightweight demo UI."""

    pages: Tuple[str, ...]
    case_studies: Mapping[str, Mapping[str, object]]
    retrieval_methods: Tuple[str, ...]
    method_comparison: Mapping[str, object]
    memo_markdown: str
    api_key_required: bool = False


@dataclass(frozen=True)
class CaseStudyReplay:
    """Replay-ready view of one portfolio case study."""

    case_id: str
    claim: str
    expected_verdict: str
    final_verdict: str
    methods: Tuple[str, ...]
    retrieved_evidence_by_method: Mapping[str, Tuple[str, ...]]
    validator_checks_by_method: Mapping[str, Tuple[str, ...]]
    failure_reasons_by_method: Mapping[str, Tuple[str, ...]]


@dataclass(frozen=True)
class DemoClaimResult:
    """Local claim verification result for the demo UI."""

    claim_text: str
    company_ticker: str
    fiscal_period: str
    verdict: str
    evidence_count: int
    numeric_reconciliation_rows: int
    memo_markdown: str
    api_key_required: bool = False


def load_demo_state(project_root: Optional[Path] = None) -> DemoState:
    """Load demo state from checked-in local artifacts."""

    if project_root is None:
        local = Path.cwd()
        project_root = local if (local / "experiments/case_studies").is_dir() else RESOURCES

    case_studies = _load_case_studies(project_root / "experiments" / "case_studies")
    method_comparison = _load_json(
        project_root / "reports" / "figures" / "method_comparison.json",
        default={"values": {}},
    )
    retrieval_methods = tuple(method_comparison.get("values", {}).keys())
    memo_markdown = _local_demo_memo().to_markdown()
    return DemoState(
        pages=DEMO_PAGES,
        case_studies=case_studies,
        retrieval_methods=retrieval_methods,
        method_comparison=method_comparison,
        memo_markdown=memo_markdown,
        api_key_required=False,
    )


def replay_case_study(state: DemoState, case_id: str) -> CaseStudyReplay:
    """Return a replayable case-study view for Streamlit or fallback rendering."""

    case = state.case_studies[case_id]
    method_results = case["method_results"]
    methods = tuple(method_results.keys())
    return CaseStudyReplay(
        case_id=case_id,
        claim=str(case["claim"]),
        expected_verdict=str(case["expected_verdict"]),
        final_verdict=str(case["final_full_engine_verdict"]),
        methods=methods,
        retrieved_evidence_by_method={
            method: tuple(
                str(evidence["evidence_key"])
                for evidence in result["retrieved_evidence"]
            )
            for method, result in method_results.items()
        },
        validator_checks_by_method={
            method: tuple(
                f"{check['validator']}={check['status']}"
                for check in result["validator_checks"]
            )
            for method, result in method_results.items()
        },
        failure_reasons_by_method={
            method: tuple(str(reason) for reason in result["failure_reasons"])
            for method, result in method_results.items()
        },
    )


def run_local_claim_demo(
    claim_text: str,
    company_ticker: str = "AAPL",
    fiscal_period: str = "2024-FY",
) -> DemoClaimResult:
    """Run one local claim through deterministic decomposition, graph verification, and memo."""

    document = _demo_document(company_ticker)
    evidence = _demo_evidence(document)
    graph = build_evidence_graph(documents=(document,), evidence_units=(evidence,))
    claim = ClaimDecomposer().decompose(
        claim_id=f"claim:{company_ticker.lower()}_local_demo",
        text=claim_text,
        company_ticker=company_ticker,
        fiscal_period=fiscal_period,
    )
    verification = ClaimVerifier().verify(claim, graph)
    memo = build_due_diligence_memo(
        memo_id=f"memo:{company_ticker.lower()}_local_demo",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(verification,),
    )
    return DemoClaimResult(
        claim_text=claim_text,
        company_ticker=company_ticker,
        fiscal_period=fiscal_period,
        verdict=verification.verdict,
        evidence_count=sum(len(result.evidence) for result in verification.subclaim_results),
        numeric_reconciliation_rows=len(memo.numeric_reconciliation),
        memo_markdown=memo.to_markdown(),
        api_key_required=False,
    )


def render_demo_markdown(state: DemoState) -> str:
    """Render a compact fallback view when Streamlit is not available."""

    lines = ["# Financial Evidence Demo", ""]
    for page in state.pages:
        lines.extend([f"## {page}", ""])
        if page == "Case study browser":
            for case_id, case in state.case_studies.items():
                lines.append(f"- `{case_id}`: `{case['final_full_engine_verdict']}`")
        elif page == "Retrieval method comparison":
            for method in state.retrieval_methods:
                lines.append(f"- `{method}`")
        elif page == "Memo view":
            lines.append(state.memo_markdown.splitlines()[0])
        else:
            lines.append("Local claim verification uses deterministic fixtures only.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_case_studies(case_studies_dir: Path) -> Mapping[str, Mapping[str, object]]:
    case_studies = {}
    for path in sorted(case_studies_dir.glob("*.json")):
        payload = _load_json(path, default={})
        case_id = str(payload.get("case_id", path.stem))
        case_studies[case_id] = payload
    return case_studies


def _load_json(path: Path, default: Mapping[str, object]) -> Mapping[str, object]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _local_demo_memo():
    return build_due_diligence_memo(
        memo_id="memo:aapl_revenue_demo",
        title="Apple FY2024 Revenue Due-Diligence Memo",
        claim_results=(
            ClaimVerifier().verify(
                ClaimDecomposer().decompose(
                    claim_id="claim:aapl_fy2024_revenue_demo",
                    text="Apple FY2024 revenue was $391.035 billion.",
                    company_ticker="AAPL",
                    fiscal_period="2024-FY",
                ),
                build_evidence_graph(
                    documents=(_demo_document("AAPL"),),
                    evidence_units=(_demo_evidence(_demo_document("AAPL")),),
                ),
            ),
        ),
    )


def _demo_document(company_ticker: str) -> DocumentMetadata:
    if company_ticker != "AAPL":
        company_ticker = "AAPL"
    return DocumentMetadata(
        document_id="AAPL:sec_xbrl_companyfacts:2024:FY",
        company="Apple Inc.",
        ticker=company_ticker,
        cik="0000320193",
        source_type="sec_xbrl_companyfacts",
        filing_type="XBRL company facts",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 9, 28),
        publication_date=date(2024, 11, 1),
        filing_date=date(2024, 11, 1),
        source_url="fixture://aapl-companyfacts-2024.json",
        retrieved_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def _demo_evidence(document: DocumentMetadata) -> EvidenceUnit:
    return EvidenceUnit.from_document(
        document=document,
        modality="xbrl",
        page_or_section="us-gaap:Revenues",
        raw_text="revenue 2024 FY = 391035000000 USD",
        source_span=SourceSpan(start=3, end=4, label="us-gaap:Revenues:USD:0"),
        normalized_metric="revenue",
        numeric_value=Decimal("391035000000"),
        unit="USD",
        currency="USD",
    )
