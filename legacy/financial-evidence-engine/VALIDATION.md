# VALIDATION.md

Run these commands from `legacy/financial-evidence-engine/` after installing the unified distribution. The [migration guide](MIGRATION.md) includes setup and links to the recorded runs.

## Always Run

Run these commands before reporting completion:

```bash
git status --short --branch
```

```bash
test -f README.md && test -f LICENSE && test -f VALIDATION.md && test -f ../../pyproject.toml
test ! -f AGENTS.md && test ! -f TASK_MEMORY.md && test ! -f RUNBOOK.md && test ! -f ROADMAP.md
```

```bash
git diff --check
```

```bash
awk '/[ \t]$/ {print FILENAME ":" FNR ": trailing whitespace"; bad=1} END {exit bad}' *.md
```

## Python Validation

Run these once Python source or tests exist:

```bash
if [ -d src ]; then python3 -m compileall src/financial_evidence_engine scripts; else echo "SKIP compileall: src/ not created yet"; fi
```

```bash
if [ -d tests ]; then python3 -m pytest tests; else echo "SKIP pytest: tests/ not created yet"; fi
```

## Config Smoke Checks

Run this once `configs/companies.yaml` and the Python package exist:

```bash
python3 - <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, "src")
from financial_evidence_engine.config import load_company_universe

companies = load_company_universe(Path("configs/companies.yaml"))
print([company.ticker for company in companies])
PY
```

## Phase 1 Registry Smoke Check

Run this once the SEC/XBRL document registry exists:

```bash
python3 scripts/smoke_phase1_registry.py
```

## Phase 2 Extraction Smoke Check

Run this once extraction modules exist:

```bash
python3 scripts/smoke_phase2_extraction.py
```

## Phase 3 Normalization Smoke Check

Run this once normalization modules exist:

```bash
python3 scripts/smoke_phase3_normalization.py
```

## Phase 4 Evidence Graph Smoke Check

Run this once evidence graph modules exist:

```bash
python3 scripts/smoke_phase4_evidence_graph.py
```

## Phase 5 Claim Verification Smoke Check

Run this once claim verification modules exist:

```bash
python3 scripts/smoke_phase5_claim_verification.py
```

## Phase 6 Due-Diligence Task Set Smoke Check

Run this once the evaluation task set exists:

```bash
python3 scripts/smoke_phase6_task_set.py
```

## Phase 7 Evaluation and Ablation Smoke Check

Run this once evaluation metrics and baselines exist:

```bash
python3 scripts/smoke_phase7_evaluation.py
```

## Real Retrieval Evaluation Smoke Check

Run this once real local retrieval baselines exist:

```bash
python3 scripts/smoke_real_retrieval_evaluation.py
```

## Data Platform Artifact Smoke Check

Run this for the AI data platform framing layer:

```bash
python3 scripts/build_data_platform_artifacts.py
python3 scripts/smoke_data_platform_artifacts.py
```

## Phase 9 Portfolio Case Studies Smoke Check

Run this once case-study artifacts exist:

```bash
python3 scripts/smoke_case_studies.py
```

## Phase 10 Investor Deck Chart Extraction Smoke Check

Run this once deck PDF/chart extraction exists:

```bash
python3 scripts/smoke_deck_chart_extraction.py
```

## Phase 11 Raw Corpus Smoke Check

Run this once raw financial document corpus indexing exists:

```bash
python3 scripts/smoke_raw_corpus.py
```

```bash
python3 scripts/smoke_real_retrieval_evaluation.py --corpus raw
```

## Phase 12 Embedding Backend Smoke Check

Run this once pluggable embedding and reranking backend exists:

```bash
python3 scripts/smoke_embedding_backend.py
```

## Phase 13 LLM Decomposition Smoke Check

Run this once validator-gated LLM claim decomposition exists:

```bash
python3 scripts/smoke_llm_decomposition.py
```

## Phase 14 Narrative / Causal Verification Smoke Check

Run this once narrative and causal claim verification exists:

```bash
python3 scripts/smoke_narrative_causal.py
```

## Phase 15 Adversarial / Red-Team Evaluation Smoke Check

Run this once adversarial financial evidence evaluation exists:

```bash
python3 scripts/smoke_adversarial_evaluation.py
```

## Phase 16 Trace / Reproducibility Smoke Check

Run this once reproducible evidence trace manifests exist:

```bash
python3 scripts/smoke_trace_reproducibility.py
```

## Phase 17 Portfolio Report Build Check

Run this once portfolio report artifacts exist:

```bash
python3 scripts/build_portfolio_report.py
```

## Phase 18 Demo UI Smoke Checks

Run these once the lightweight local demo UI exists:

```bash
python3 scripts/smoke_demo_ui.py
```

```bash
python3 scripts/smoke_streamlit_start.py
```

## Phase 19 CLI Workflow Smoke Check

Run this once local production CLI commands exist:

```bash
python3 scripts/smoke_cli_workflow.py
```

## Phase 20 Interview Packaging Smoke Check

Run this once final resume and interview packaging exists:

```bash
python3 scripts/smoke_interview_packaging.py
```

## Portfolio Screenshot Build Check

Run this before refreshing README screenshots:

```bash
python3 scripts/build_portfolio_screenshots.py
```

## Portfolio Demo Entry Point

Run this before using the repository for applications:

```bash
make portfolio-demo
```

## Public Portfolio Freeze Audit

Run this before publishing the repository or using the project for applications:

```bash
python3 -m pytest tests/test_public_portfolio_packaging.py -q
```

## Phase 8 Due-Diligence Memo Smoke Check

Run this once auditable memo generation exists:

```bash
python3 scripts/smoke_phase8_memo.py
```

## Final Report Package Smoke Check

Run this once final report packaging exists:

```bash
python3 scripts/smoke_final_report_package.py
```

## CPU dense retrieval experiments

TF-IDF SVD baseline and metadata-rerank ablation. This run does not use a neural model:

```bash
python3 scripts/run_dense_lsa_experiment.py --config configs/dense_lsa.yaml
```

Optional CPU MiniLM baseline. Without the environment variable, an existing artifact is left in place and the script prints `not yet run`:

```bash
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python3 -m pip install "sentence-transformers==6.2.0"
FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1 python3 scripts/run_sentence_transformer_baseline.py --config configs/dense_sentence_transformer.yaml
```

## Hard benchmark

Synthetic labeled set, separate from the 60-task verdict numbers:

```bash
python3 scripts/run_hard_benchmark.py
```

MiniLM on that set:

```bash
FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1 python3 scripts/run_hard_benchmark.py
```

## Phase-Specific Validation

Run the smoke checks above when the corresponding entry point exists.

Required smoke checks should be added here when new entry points are created:

- CLI commands
- data ingestion commands
- extraction scripts
- evaluation scripts
- report generation scripts

When a check is skipped, record the command and the reason next to the result you are reporting. Do not replace a skipped run with an estimated number.
