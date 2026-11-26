# Data Platform View

This project can also be read as a local unstructured financial-document data
pipeline. The core system still verifies claims; this view exposes the same
evidence chain as versioned, inspectable data artifacts for AI data platform,
retrieval infrastructure, and document intelligence interviews.

## Artifact Tables

| Table | Role |
| --- | --- |
| `reports/tables/document_metadata.csv` | Source document inventory with company, source type, fiscal period, chunk counts, modalities, and corpus version hash. |
| `reports/tables/chunks.csv` | Searchable raw corpus chunks with provenance, source spans, text length, metric, unit, currency, and stable chunk hash. |
| `reports/tables/evidence_units.csv` | Gold evidence requirements used to ground claims during evaluation. |
| `reports/tables/claims.csv` | Due-diligence claim/task table with families, entities, fiscal periods, expected verdicts, and label counts. |
| `reports/tables/citation_coverage.csv` | Retrieval-method coverage report with citation exactness and evidence recall. |
| `reports/tables/normalization_quality_checks.csv` | Fiscal-period, entity, metric, unit, citation, and numeric-reconciliation quality checks. |

## Pipeline Framing

```text
raw SEC/XBRL-style filings, transcripts, and deck fixtures
-> source document metadata
-> raw chunks with provenance and hashes
-> evidence requirements and claim labels
-> retrieval/citation coverage report
-> fiscal-period, metric, unit, entity, and numeric quality checks
-> auditable claim verification and memo generation
```

This is deliberately a local reproducible fixture. It is not broad SEC-scale
ingestion, not a trained retrieval model, and not broad visual chart
understanding. The value is the data contract: every claim, chunk, citation,
and normalization check remains auditable.

## Build

```bash
python3 scripts/build_data_platform_artifacts.py
```

The build is offline and deterministic. It uses the existing local raw corpus,
task set, and real retrieval evaluation slice; no API key is required.
