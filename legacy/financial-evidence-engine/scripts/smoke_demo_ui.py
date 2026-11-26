"""Smoke check for Phase 18 lightweight local demo UI."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.demo import load_demo_state, run_local_claim_demo


def main() -> None:
    state = load_demo_state()
    result = run_local_claim_demo(
        claim_text="Apple FY2024 revenue was $391.035 billion.",
        company_ticker="AAPL",
        fiscal_period="2024-FY",
    )
    print(
        f"pages={len(state.pages)} "
        f"case_studies={len(state.case_studies)} "
        f"methods={len(state.retrieval_methods)} "
        f"local_claim_verdict={result.verdict} "
        f"api_key_required={state.api_key_required} "
        "app=app.py"
    )


if __name__ == "__main__":
    main()
