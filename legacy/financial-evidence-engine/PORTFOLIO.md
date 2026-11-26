# Financial Evidence Engine

Claim-level financial evidence verification for auditable due-diligence workflows.

| Claim verification | Case-study replay | Memo and trace view |
| --- | --- | --- |
| ![Claim verification demo](docs/assets/claim_verification_demo.png) | ![Case study replay](docs/assets/case_study_replay.png) | ![Memo and trace view](docs/assets/memo_trace_demo.png) |

![Killer metrics](docs/assets/killer_metrics.png)

## Core Results

| Result | Value | Why It Matters |
| --- | ---: | --- |
| Full engine accuracy | 83.3% | Validator-augmented retrieval beats retrieval-only baselines on local due-diligence tasks. |
| Surfaced failure cases | 346 | The system exposes period, entity, citation, numeric, contradiction, and unsupported-claim errors instead of hiding them. |
| Adversarial detection | 75.0% | Red-team failures remain explainable rather than being presented as perfect accuracy. |

## Benchmark Framing

Ordinary RAG can find text that looks relevant but does not actually support a financial claim.
This project reframes the task as claim verification:

```text
ordinary RAG answer
vs
claim decomposition -> evidence graph -> numeric reconciliation -> validator gate -> auditable memo
```

The system verifies company, fiscal period, metric, unit, currency, citation support, contradictions, and unsupported narrative claims before issuing a final verdict.

## Data Platform View

For AI data platform interviews, the same system can be described as a local
unstructured financial-document pipeline: document metadata -> raw chunks ->
evidence units -> claim labels -> citation coverage -> fiscal-period and unit
normalization quality checks.

Artifacts:

- [Data platform framing](docs/data_platform_framing.md)
- `reports/tables/document_metadata.csv`
- `reports/tables/chunks.csv`
- `reports/tables/evidence_units.csv`
- `reports/tables/claims.csv`
- `reports/tables/citation_coverage.csv`
- `reports/tables/normalization_quality_checks.csv`

## 30-minute reproduction

```bash
python3 -m pytest
python3 scripts/build_portfolio_screenshots.py
python3 scripts/build_portfolio_report.py
python3 scripts/smoke_cli_workflow.py
python3 scripts/smoke_interview_packaging.py
```

Fast path:

```bash
make portfolio-demo
```

Expected output includes:

```text
screenshots=3
commands=6
verify_verdict=support
docs=6
api_key_required=False
```

## Resume Bullets

AI infra:

> Built a local, reproducible financial evidence engine with CLI workflows, artifact manifests, deterministic screenshots, PDF report generation, and offline validation over retrieval, trace, and packaging smoke tests.

Financial AI:

> Built a claim-level due-diligence evidence engine over SEC/XBRL-style filings, transcripts, and investor-deck evidence, generating auditable memos with numeric reconciliation, citation validation, fiscal-period checks, and contradiction detection.

RAG/eval:

> Benchmarked BM25, dense-proxy, hybrid, graph, and validator-augmented retrieval on due-diligence and adversarial tasks, surfacing failure cases where ordinary RAG retrieves plausible but unsupported evidence.

## Public Freeze Note

`portfolio-v1` is the stable portfolio artifact.
The roadmap is complete through Phase 20, and future work should be driven by recruiter or interviewer feedback rather than generic feature expansion.

Boundaries:

- Investor-deck evidence extraction is a narrow text-extractable slice, not broad visual chart understanding.
- Dense retrieval defaults to a deterministic token-vector proxy unless an optional backend is explicitly configured.
- The raw corpus is a local reproducible fixture, not broad SEC-scale ingestion.
