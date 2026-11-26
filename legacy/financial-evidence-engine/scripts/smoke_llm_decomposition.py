"""Smoke check for Phase 13 validator-gated LLM claim decomposition."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.reasoning import (
    OptionalLiveLLMClaimDecomposer,
    build_decomposition_comparison_report,
    write_decomposition_comparison_artifacts,
)


def main() -> None:
    report = build_decomposition_comparison_report()
    manifest = write_decomposition_comparison_artifacts(report)
    live_decomposer = OptionalLiveLLMClaimDecomposer()
    print(
        f"complex_claims={report.complex_claim_count} "
        f"providers={report.rule_based_provider},{report.recorded_llm_provider} "
        f"rule_based_subclaims={report.rule_based_subclaim_count} "
        f"llm_subclaims={report.llm_subclaim_count} "
        f"rejected={report.rejected_subclaim_count} "
        f"json_artifact={manifest.json_artifact} "
        f"markdown_artifact={manifest.markdown_artifact} "
        f"live_available={live_decomposer.is_available()}"
    )


if __name__ == "__main__":
    main()
