# Multimodal Financial Due-Diligence Evidence Engine

## 1. Problem: ordinary RAG is unsafe for financial due diligence

Ordinary RAG can return fluent financial answers while mixing fiscal periods, units, sources, or unsupported management narratives.
This project frames due diligence as claim-level evidence verification rather than chatbot answer generation.

## 2. System overview

Pipeline: claim decomposition -> retrieval -> evidence graph linking -> financial normalization -> validator gates -> auditable memo.
The local corpus covers SEC/XBRL facts, filings, transcripts, tables, raw chunks, investor-deck pages, and chart evidence fixtures.

## 3. Evidence graph and validators

Evidence nodes are tied to company, period, source type, modality, metric, and provenance.
Validators check citation support, fiscal periods, entity/source consistency, numeric reconciliation, unsupported claims, contradictions, and red-team failure modes.

## 4. Real retrieval benchmark

Real retrieval benchmark: `60` tasks over `320` benchmark documents.
BM25 verdict accuracy: `0.6666666666666666666666666667`.
Full engine verdict accuracy: `0.8333333333333333333333333333` with `346` surfaced failure cases.

## 5. Three failure case studies

- `fiscal_period_confusion`: `period_confusion`, verdict `support`
- `numeric_unit_mismatch`: `numeric_validation_gap`, verdict `support`
- `unsupported_narrative_claim`: `unsupported_claim`, verdict `insufficient`

## 6. Investor deck and chart extraction case

Claim: NVIDIA FY2024 Data Center revenue was $47.5 billion.
Deck pages: `1`, chart evidence: `1`, reconciliation rows: `1`.
Verdict: `support` for NVIDIA FY2024 Data Center revenue after chart-to-XBRL reconciliation.

## 7. Ablation results

- `without_graph` verdict accuracy `1`
- `without_numeric_validator` verdict accuracy `0.6666666666666666666666666667`
- `without_fiscal_period_validator` verdict accuracy `1`
- `without_chart_table_extraction` verdict accuracy `1`
- `without_contradiction_detector` verdict accuracy `0.8333333333333333333333333333`
- `without_reranker` verdict accuracy `1`

## 8. Limitations

The raw corpus is still a deterministic local fixture, not a broad live SEC paragraph index.
Dense retrieval defaults to an offline deterministic proxy; optional real embedding providers are skipped unless available.
The chart extraction slice is narrow and text-extractable; broad chart parsing remains future work.
Red-team detection accuracy is `0.75`, not perfect by design.

## 9. Reproducibility

One-command portfolio report generation: `python3 scripts/build_portfolio_report.py`.
Trace reproduction: `python3 scripts/smoke_trace_reproducibility.py`.
Full local validation remains offline and deterministic; no API key is required.

## 10. Resume bullet

Built a multimodal financial due-diligence evidence engine for claim-level verification over SEC/XBRL filings, earnings transcripts, and investor-deck evidence; benchmarked BM25, dense-proxy, hybrid, graph, and validator-augmented retrieval on 60 due-diligence tasks and 120 adversarial cases, generating auditable memos with numeric reconciliation, citation validation, fiscal-period checks, contradiction detection, and reproducible evidence traces.
