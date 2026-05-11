# Sandboxed Tool-Use Agent Evaluation Harness

[![CI](https://github.com/OrrinChen/Sandbox/actions/workflows/sandboxed-agent-eval-harness-ci.yml/badge.svg)](https://github.com/OrrinChen/Sandbox/actions/workflows/sandboxed-agent-eval-harness-ci.yml)
![Evidence](https://img.shields.io/badge/evidence-offline_recorded%20%7C%20fixture--backed%20%7C%20no_live_API_by_default-blue)

**Final-answer-only grading overestimated validated correctness by 56.2 percentage points; deterministic validators caught 180 silent failures.**

Evidence: offline recorded, fixture-backed, no live API by default.

| Signal | Value |
| --- | ---: |
| Validator gap | 56.2pp validator gap |
| Silent failures | 180 silent failures |
| Benchmark size | 64 tasks |
| Domains | 6 domains |
| Validators | 10 deterministic validators |
| Failure taxonomy | 7 failure categories |
| Recorded runs | 320 runs |
| Model profiles | 5 recorded profiles |

The model profiles are recorded behavior profiles, not a real-time model benchmark.

Evaluation infrastructure for tool-using agents. The project is not an agent product; it measures whether a tool-use run is actually correct when the final answer looks plausible.

## Problem

Final-answer-only grading misses silent failures: wrong tool choice, wrong arguments, wrong state mutation, wrong numeric values, unsupported citations, constraint violations, non-replayable traces, timeouts, and cost regressions.

This harness makes those failures visible with typed tools, isolated fixture execution, JSONL traces, deterministic validators, replay, regression gates, and static evidence reports.

## Final-answer Grading vs Deterministic Tool-use Validation

| Evaluation mode | What it can see | What it misses |
| --- | --- | --- |
| Final-answer grading | Plausible final answer | tool choice, arguments, state, numbers, citations, constraints, replay |
| Deterministic tool-use validation | tool choice, arguments, state, numbers, citations, constraints, replay | Broader semantic judgment outside the fixture-backed task oracle |

## Architecture

```text
task spec
-> typed tool registry
-> workspace or optional Docker evaluation isolation
-> executable fixture tools
-> JSONL trace capture
-> deterministic validators
-> trace replay
-> regression gates
-> portfolio report
```

Core runtime surfaces:

- Typed schemas: tasks, tools, traces, validators, run results
- Tool registry: input/output validation, permissions, side effects
- Sandbox backends: local workspace by default; optional Docker command envelope
- Validators: schema, tool sequence, arguments, state, numeric, citation, constraint, unit tests, policy, cost/latency
- Reports: root-cause taxonomy, model matrix, domain breakdown, replayable failure case studies

Docker support is evaluation isolation and reproducibility support, not a security product.

## Quickstart

```bash
make reproduce-report
make ci
```

Useful outputs:

```text
reports/portfolio_report.md
reports/portfolio_report.json
reports/tables/model_matrix.csv
reports/tables/failure_taxonomy.csv
reports/tables/domain_breakdown.csv
reports/examples/replayable_failure_*.md
```

## Key Result

Recorded offline study over 64 fixture-backed benchmark tasks and 5 recorded offline model profiles:

```text
Final-answer-only grading overestimated validated correctness by 56.2 percentage points;
deterministic validators caught 180 silent failures.
```

Evidence snapshot:

| Item | Value |
| --- | ---: |
| Benchmark tasks | 64 |
| Domains | 6 |
| Recorded model profiles | 5 |
| Runs | 320 |
| Final-answer pass rate | 1.000 |
| Validator pass rate | 0.438 |
| Silent failures | 180 |
| Distinct failure signatures | 5 |

Failure categories caught include tool selection errors, state mutation errors, numeric mismatches, unsupported citations, constraint violations, and final-answer overclaims.

## Reproducibility

```bash
make validate-config
make optional-integrations-smoke
make ci
make portfolio-report
```

`make ci` runs:

- full pytest
- config validation
- oracle smoke evaluation
- strict regression gate with replay
- recorded model silent-failure study
- report generation

Default validation is credential-free and network-free. Live provider runs are opt-in only and require explicit `--live` plus credentials.

## Optional Integrations

The LangChain, LangGraph, LangSmith, and MCP layer is optional adapter infrastructure. It does not replace the harness runner, recorded benchmark evidence, replay gates, or deterministic validators.

```bash
pip install -e ".[ai-integrations]"
make optional-integrations-smoke
```

- LangChain: wraps fixture-backed harness tools as adapter tools while preserving JSONL trace events.
- LangGraph: `backend="local"` maps `plan -> tool_call -> tool_result -> validate -> retry_or_finish` transitions into trace events; `backend="langgraph"` compiles a real optional `StateGraph` workflow with `InMemorySaver` checkpointing when LangGraph is installed.
- LangSmith: writes a local export by default; upload requires explicit opt-in credentials and is excluded from default CI.
- MCP: exposes a fixture-backed MCP `tools/list` and `tools/call` JSON-RPC adapter, maps MCP tool calls into the same harness JSONL traces, requires no MCP SDK for local smoke checks, and keeps no live MCP server by default.

## Portfolio Materials

- Public report: `reports/portfolio_report.md`
- Replay walkthrough: `docs/replayable_failure_walkthrough.md`
- Architecture notes: `docs/architecture.md`
- Interview notes: `docs/interview_notes.md`
- Limitations: `docs/limitations.md`
- Failure case studies: `docs/failure_case_studies.md`

Resume bullet:

> Built a replayable LLM tool-use evaluation harness with typed tool specs, workspace/container-backed evaluation isolation, deterministic validators, JSONL trace replay, root-cause failure reports, and CI regression gates; offline recorded model-matrix studies over 64 deterministic tasks exposed distinct silent-failure signatures hidden by final-answer-only grading.

## Limitations

- The benchmark is fixture-backed and deterministic; it is not a live-provider benchmark.
- Recorded model profiles are controlled offline behavior profiles, not claims about specific public providers.
- The final-answer pass metric is a harness proxy, not semantic LLM judging.
- Optional Docker backend is not a security product.
- Live provider workflow is available but excluded from default CI and portfolio evidence unless manually run with credentials.

Roadmap status: frozen after Phase 24. Future work should be maintenance, bug fixes, refreshed recorded evidence, or documentation polish only.
