# Demo Script

## 2-Minute Flow

1. Open the portfolio report:

```bash
open reports/final_report.pdf
```

2. Start the local UI:

```bash
python3 -m streamlit run app.py
```

3. Show the claim verification view with:

```text
Apple FY2024 revenue was $391.035 billion.
```

4. Open the case study browser and show:

```text
fiscal_period_confusion
numeric_unit_mismatch
unsupported_narrative_claim
```

5. Show the local CLI:

```bash
PYTHONPATH=src python3 -m financial_evidence_engine.cli verify-claim --claim "Apple FY2024 revenue was $391.035 billion."
```

This uses `financial_evidence_engine.cli` and does not require an API key.

## 30-Minute Reproduction

```bash
python3 -m pytest
python3 scripts/smoke_trace_reproducibility.py
python3 scripts/build_portfolio_report.py
python3 scripts/smoke_demo_ui.py
python3 scripts/smoke_cli_workflow.py
```
