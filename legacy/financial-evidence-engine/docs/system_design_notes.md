# System Design Notes

## Core Components

1. Claim decomposition turns a financial statement into subclaims.
2. Retrieval collects candidate evidence from benchmark and raw local corpora.
3. Evidence graph links companies, fiscal periods, documents, metrics, evidence units, and claims.
4. Validators check citation support, fiscal period, source consistency, entity, numeric reconciliation, unsupported claims, and contradictions.
5. Memo generation writes an auditable due-diligence artifact.

## Evidence Graph

Evidence graph nodes represent documents, evidence units, metrics, fiscal periods, companies, claims, and risk themes. Edges preserve why a source supports or contradicts a claim.

## Reproducibility

Phase 16 adds trace manifests and a local SQLite store. Each run records config hash, corpus version, method, task id, retrieved chunks, validator outputs, final verdict, runtime, and artifact paths.

## Local Production Boundary

Phase 19 exposes the workflow through `financial-evidence` CLI commands. Profiles are offline by default; missing files return stable error codes instead of tracebacks.
