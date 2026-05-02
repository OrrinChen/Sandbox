# Sandboxed Tool-Use Agent Evaluation Harness

## Problem
The harness evaluates whether tool-using agents used the right tools, arguments, state mutations, numeric outputs, citations, and constraints, not just whether the final answer sounds plausible.

## System
Pipeline: typed task schema -> typed tool registry -> workspace/container evaluation isolation -> JSONL trace capture -> deterministic validators -> trace replay -> regression gates -> static reports

Validators: schema, tool_sequence, argument, state, numeric, citation, constraint, unit_test, policy, cost_latency

## Evidence
Final-answer-only grading overestimated validated correctness by 56.2 percentage points; deterministic validators caught 180 silent failures.

- Recorded offline runs: 320
- Final-answer pass rate: 1.000
- Validator pass rate: 0.438
- Silent failures: 180
- Model profiles: 5
- Distinct failure signatures: 5

## Benchmark
- Suite: benchmark
- Tasks: 64
- Domains: citation, coding, data_analysis, file_workflow, finance, optimization
- Fixture-backed deterministic benchmark; not a live-provider benchmark.

## Failure Taxonomy
- CITATION_UNSUPPORTED: 40
- CONSTRAINT_VIOLATION: 12
- FINAL_ANSWER_OVERCLAIM: 180
- NUMERIC_MISMATCH: 52
- STATE_MUTATION_ERROR: 76
- TOOL_RESULT_MISUSE: 24
- TOOL_SELECTION_ERROR: 64

## Case Studies
- [replayable_failure_01](examples/replayable_failure_01_citation-nvda-datacenter-evidence-01.md): recorded_overconfident_model / citation-nvda-datacenter-evidence-01 (CITATION_UNSUPPORTED, FINAL_ANSWER_OVERCLAIM, NUMERIC_MISMATCH)
- [replayable_failure_02](examples/replayable_failure_02_optimization-newsvendor-order-benchmark-01.md): recorded_overconfident_model / optimization-newsvendor-order-benchmark-01 (CONSTRAINT_VIOLATION, FINAL_ANSWER_OVERCLAIM, NUMERIC_MISMATCH)
- [replayable_failure_03](examples/replayable_failure_03_data-churn-plan-rate-benchmark-01.md): recorded_overconfident_model / data-churn-plan-rate-benchmark-01 (FINAL_ANSWER_OVERCLAIM, NUMERIC_MISMATCH)

## Reproducibility
- Generate this report: `make portfolio-report`
- Run deterministic CI: `make ci`
- Default report generation is key-free and network-free.

## Limitations
- This report is generated from recorded offline model profiles; it is not a live-provider benchmark.
- Benchmark tasks are deterministic and fixture-backed; they are evidence for harness behavior, not broad production claims.
- Docker support is evaluation isolation and reproducibility support, not a security product.
- Live provider runs remain opt-in and credentials-gated; default validation does not call external APIs.
