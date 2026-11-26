"""Streamlit entry point for the local due-diligence evidence demo."""

from __future__ import annotations

import sys

from financial_evidence_engine.demo import (
    load_demo_state,
    render_demo_markdown,
    replay_case_study,
    run_local_claim_demo,
)


try:
    import streamlit as st
except Exception:  # pragma: no cover - exercised when optional dependency is absent.
    st = None


def main() -> None:
    if "--smoke" in sys.argv:
        _smoke()
        return
    state = load_demo_state()
    if st is None:
        print(render_demo_markdown(state))
        return

    st.set_page_config(page_title="Financial Evidence Engine", layout="wide")
    st.title("Financial Evidence Engine")

    claim_tab, case_tab, retrieval_tab, memo_tab = st.tabs(state.pages)
    with claim_tab:
        left, middle, right = st.columns((1, 1.2, 1))
        with left:
            claim_text = st.text_area(
                "Claim",
                value="Apple FY2024 revenue was $391.035 billion.",
                height=120,
            )
            company_ticker = st.selectbox("Company", ("AAPL",), index=0)
            fiscal_period = st.selectbox("Fiscal period", ("2024-FY",), index=0)
        result = run_local_claim_demo(claim_text, company_ticker, fiscal_period)
        with middle:
            st.subheader("Evidence")
            st.metric("Evidence rows", result.evidence_count)
            st.metric("Numeric rows", result.numeric_reconciliation_rows)
        with right:
            st.subheader("Verdict")
            st.metric("Final verdict", result.verdict)
            st.markdown(result.memo_markdown)

    with case_tab:
        case_id = st.selectbox("Case", tuple(state.case_studies.keys()))
        replay = replay_case_study(state, case_id)
        st.subheader(replay.case_id)
        st.write(replay.claim)
        st.metric("Final verdict", replay.final_verdict)
        method = st.selectbox("Method", replay.methods)
        st.markdown("#### Retrieved evidence")
        st.write(list(replay.retrieved_evidence_by_method[method]))
        st.markdown("#### Validator checks")
        st.write(list(replay.validator_checks_by_method[method]))
        st.markdown("#### Failure reasons")
        st.write(list(replay.failure_reasons_by_method[method]))

    with retrieval_tab:
        st.subheader("Method comparison")
        st.json(state.method_comparison)

    with memo_tab:
        st.markdown(state.memo_markdown)


def _smoke() -> None:
    state = load_demo_state()
    result = run_local_claim_demo(
        "Apple FY2024 revenue was $391.035 billion.",
        "AAPL",
        "2024-FY",
    )
    print(
        f"pages={len(state.pages)} "
        f"case_studies={len(state.case_studies)} "
        f"methods={len(state.retrieval_methods)} "
        f"local_claim_verdict={result.verdict} "
        f"api_key_required={state.api_key_required} "
        f"streamlit_optional={st is not None} "
        "app=app.py"
    )


if __name__ == "__main__":
    main()
