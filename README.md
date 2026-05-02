# Sandboxed Tool-Use Agent Evaluation Harness

An evaluation harness for answering a practical reliability question:

```text
Can tool-using agents complete real workflows reliably, repeatably, and safely?
```

This is not an agent demo. The goal is to expose silent failures where the final answer looks plausible but tool choice, tool arguments, state mutation, numeric values, citations, constraints, or business rules failed.

## Core Pipeline

```text
task definition
-> tool registry
-> sandboxed execution
-> trace capture
-> deterministic validators
-> failure classification
-> trace replay
-> regression report/dashboard
```

## Current Status

The repository has completed Phase 23 public portfolio report generation. It now has workflow documents, Python package metadata, runtime-validated config files, a `src/` package layout, skeletal tests, typed schema contracts, a `ToolSpec`-backed registry, a minimal local sandbox, executable local fixture tools, JSONL trace logging, trace replay execution from fixture state, deterministic validators, local fixture-backed finance/data-analysis/coding/optimization/file-workflow/citation tasks, deterministic agent baselines, recorded model-output adapters, optional OpenAI Responses and generic HTTP live adapters, smoke and benchmark evaluation runner presets, report generation from evaluation artifacts, normalized root-cause taxonomy, replay divergence summaries, configurable regression gates that can fail a run, project-level gate presets, summary-driven trace discovery for replay gates, local `make` reproducibility commands, a GitHub Actions CI workflow scoped to this project subdirectory, an offline recorded model matrix that compares distinct failure signatures, a manual live workflow that fails closed unless `--live` and credentials are supplied, workspace/Docker sandbox backend selection for evaluation isolation, a dependency-free config validation command wired into reproducibility checks, and a static portfolio report with CSV tables and replayable failure case studies.

Current evidence snapshot:

```text
Domains: finance, data_analysis, coding, optimization, file_workflow, citation
Default deterministic tasks: 8
Benchmark deterministic tasks: 64
Validators: schema, tool_sequence, argument, state, numeric, citation, constraint, unit_test, policy, cost_latency
Recorded smoke study: final-answer pass rate 1.000 vs validator pass rate 0.500
Recorded smoke silent failures caught: 4
Recorded benchmark study: final-answer pass rate 1.000 vs validator pass rate 0.500
Recorded benchmark silent failures caught: 32
Strict oracle smoke replay: 8 traces, 0 divergences
Strict oracle benchmark replay: 64 traces, 0 divergences
Root-cause report: validator gap, silent failure rate, answer overclaim rate, and breakdowns by domain/tool/model/validator
Recorded model matrix: 5 offline profiles, 320 benchmark runs, 5 distinct failure signatures
Matrix key finding: final-answer-only grading overestimated validated correctness by 56.2 percentage points; deterministic validators caught 180 silent failures
Live workflow: opt-in only, fails closed without --live, skips without credentials, converts live outputs into recorded fixture candidates
Sandbox backends: default workspace backend plus optional Docker command envelope with network disabled, read-only fixture mount, resource limits, and deterministic artifact export
Runtime config validation: tools=7, validators=10, task_suites=2, eval_runs=1
Portfolio report: reports/portfolio_report.md with model matrix, failure taxonomy, domain breakdown, and 3 replayable failure case studies
```

Start by reading:

- `AGENTS.md`
- `ROADMAP.md`
- `TASK_MEMORY.md`
- `VALIDATION.md`
- `RUNBOOK.md`

## First MVP Target

Build a small vertical slice before expanding:

- Typed task schema
- Typed tool registry
- Sandboxed execution
- Trace logger
- Deterministic validators
- Fixture-backed finance tasks
- Fixture-backed data analysis tasks
- Basic report

Live network APIs, paid services, and full dashboards are deferred until deterministic local behavior works.

## Quick Validation

For the current package:

```bash
make ci
git diff --check -- .
```

For later phases, follow `VALIDATION.md`.

Reproducibility commands:

```bash
make test
make smoke
make gate
make model-study
make report
make validate-config
make portfolio-report
make ci
```

## Public Portfolio Report

Generate the recruiter/interviewer-facing static report with:

```bash
make portfolio-report
```

The command writes:

- `reports/portfolio_report.md`
- `reports/portfolio_report.json`
- `reports/tables/model_matrix.csv`
- `reports/tables/failure_taxonomy.csv`
- `reports/tables/domain_breakdown.csv`
- `reports/examples/replayable_failure_*.md`

The report is generated from recorded offline model profiles and fixture-backed benchmark tasks. It is key-free and network-free by default; it is not a live-provider benchmark.

## Runtime Config Validation

Runtime config utilities live in `sandboxed_agent_eval_harness.config`.

They provide:

- `load_tools_config()`
- `load_validators_config()`
- `load_task_suites_config()`
- `load_eval_runs_config()`
- `validate_project_config()`

The validation command checks the versioned config files against runtime surfaces: default tool names, validator names, task-suite manifests and task ids, eval-run baselines, and required metrics. It uses a project-specific dependency-free parser for the current controlled config format; it is not a general YAML parser.

```bash
make validate-config
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate --json
```

Bad config fails deterministically, and `make ci` runs config validation before the smoke, gate, model-study, and report steps.

## Core Schemas

The first typed contracts live in `sandboxed_agent_eval_harness.schemas`:

- `TaskSpec`
- `ToolSpec`
- `TraceEvent`
- `ValidatorResult`
- `RunResult`

They provide plain-dict serialization and deterministic validation errors for missing fields, invalid limits, invalid tool arguments, trace sequence errors, failed validator metadata, and inconsistent run status.

## Tool Registry

The first registry implementation lives in `sandboxed_agent_eval_harness.tools.registry`.

It provides:

- `ToolRegistry`
- `UnknownToolError`
- `DuplicateToolError`
- `default_tool_specs()`
- `default_tool_registry()`

The default registry declares fixture-backed finance tools and local CSV/data-analysis tools:

- `financial_statement.lookup`
- `transcript.search`
- `csv.read`
- `csv.group_metrics`
- `code.patch`
- `python.unit_tests`
- `optimization.solve_newsvendor`

The registry handles lookup, unknown-tool rejection, duplicate-tool rejection, input validation before execution, output validation after execution, and metadata access for permissions, side effects, state mutation, and failure modes. Runtime execution is provided by the fixture-backed executor.

## Executable Fixture Tool Adapters

The local executor lives in `sandboxed_agent_eval_harness.tools`.

It provides:

- `FixtureToolExecutor`
- `ToolExecutionError`

The executor runs the default fixture-backed finance, transcript, CSV, coding, and optimization tools without network access. It copies visible fixture files into a per-run `FileSystemSandbox`, validates tool inputs and outputs through the registry, applies code patches, runs sandboxed fixture unit tests, writes CSV/optimization outputs into the run workspace, and lets the runner capture state diffs from real workspace snapshots.

## Sandbox

The sandbox utilities live in `sandboxed_agent_eval_harness.sandbox`.

They provide:

- `FileSystemSandbox`
- `LocalWorkspaceBackend`
- `DockerSandboxBackend`
- `SandboxBackendConfig`
- `StateSnapshot`
- `StateDiff`
- `run_python_subprocess()`
- `SandboxPathError`
- `SandboxTimeoutError`

The workspace backend constrains path operations to a task workspace, supports an optional read allowlist, resets to deterministic initial files, exports artifacts deterministically, and captures added/modified/deleted file diffs. The subprocess helper runs Python snippets in the workspace with a timeout.

The optional Docker backend builds a container command envelope with network disabled, memory/CPU/PID limits, a read-only fixture mount, a writable workspace mount, a read-only container root, and tmpfs for `/tmp`. It is for evaluation isolation and reproducibility, not a security product.

Runner command with explicit workspace backend:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --sandbox-backend workspace \
  --output-dir artifacts/eval_runs/smoke
```

Optional Docker backend command, only when Docker is intentionally available:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --sandbox-backend docker \
  --output-dir /tmp/sandboxed-agent-eval-docker-smoke
```

## Trace Logging And Replay

The first trace utilities live in `sandboxed_agent_eval_harness.tracing`.

They provide:

- `TraceLogger`
- `TraceReplay`
- `TraceReplayError`
- `load_trace_events()`

The logger appends ordered JSONL events for user messages, agent messages, tool calls, tool results, state diffs, validator results, timeout events, and error events. Each event carries pinned run metadata where available, including task, tool, prompt, model, and fixture versions.

The replay helper loads persisted JSONL traces, rejects malformed or non-contiguous event sequences, preserves original event order, and carries fixture state needed to inspect a failed run. Trace execution support can re-run persisted tool calls for supported fixture-backed tasks.

## Trace Replay Execution

Trace replay execution lives in `sandboxed_agent_eval_harness.tracing`.

It provides:

- `TraceReplayExecutor`
- `TraceReplayExecutionResult`
- `TraceReplayExecutionError`

The replay executor reads persisted tool calls from a JSONL trace, identifies the pinned task from trace metadata, re-executes supported fixture-backed tools in a fresh workspace, compares recorded and replayed tool results, compares recorded and replayed state diffs, and returns deterministic divergence records.

## Regression Threshold Gates

Regression gates live in `sandboxed_agent_eval_harness.evaluation.gates`.

They provide:

- `RegressionGateResult`
- `RegressionGateReport`
- `RegressionGatePreset`
- `evaluate_regression_gates()`
- `load_threshold_preset()`
- `discover_trace_paths()`

The gate evaluator can enforce minimum task success rate, minimum pass@k, maximum task success drop against a previous summary, maximum pass@k drop, maximum failure taxonomy counts, and maximum replay divergence count. Replay divergence summaries are also included in reports when replay execution results are supplied.

Project presets live in `configs/regression_gates.json`. The `strict_smoke` preset is intended for deterministic oracle smoke runs and can discover trace paths from `summary.json`.

Smoke command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates \
  --summary artifacts/eval_runs/smoke/summary.json \
  --threshold-preset strict_smoke \
  --discover-traces \
  --replay-workspace /tmp/sandboxed-agent-eval-gates-replay
```

The command prints a structured gate report and exits non-zero when any configured threshold fails.

## Deterministic Validators

The first validator utilities live in `sandboxed_agent_eval_harness.validators`.

They provide:

- `validate_schema()`
- `validate_tool_sequence()`
- `validate_tool_arguments()`
- `validate_state()`
- `validate_numeric()`
- `validate_citations()`
- `validate_constraints()`
- `validate_unit_tests()`
- `validate_policy()`
- `validate_cost_latency()`
- `default_validator_names()`

Each validator returns the existing `ValidatorResult` schema. The validators catch malformed schema payloads, wrong or missing tool sequences, invalid tool-call arguments, state-diff mismatches, numeric mismatches with explicit tolerance, unsupported or missing citations, optimization constraint violations, missing or failing sandboxed unit tests, deterministic policy-term violations, and cost/latency/turn/timeout limit regressions. They are deterministic and fixture-friendly; they do not call live APIs or LLM judges.

## Initial Task Suites

The first task suite utilities live in `sandboxed_agent_eval_harness.tasks`.

They provide:

- `TaskSuite`
- `TaskSuiteValidationError`
- `load_task_suite()`
- `default_task_suite()`
- `default_task_suite_path()`
- `benchmark_task_suite()`
- `benchmark_task_suite_path()`
- `task_suite_by_name()`

The default suite manifest is `fixtures/tasks/initial_suite.json`. It contains eight deterministic tasks: three fixture-backed finance tasks, three local CSV/data-analysis tasks, one sandboxed coding task, and one small optimization task. Every task is represented as a `TaskSpec`, has non-empty hidden expected state, declares fixture paths, includes gold numeric/file/unit-test outputs, and records known traps where final-answer-only scoring can look successful while validators should fail.

The benchmark suite manifest is `fixtures/tasks/benchmark_suite.json`. It contains 64 deterministic fixture-backed tasks across finance, data analysis, coding, optimization, file workflow, and citation domains. Each task declares explicit failure-taxonomy traps while reusing local fixtures and executable tool adapters, so benchmark runs stay network-free and replayable.

## Agent Baselines And Evaluation Runner

The first deterministic baselines live in `sandboxed_agent_eval_harness.agents`:

- `single_shot_tool_agent`
- `react_style_agent`
- `planner_executor_agent`
- `oracle_tool_selection_agent`
- `ModelAdapterAgent`

The smoke and benchmark runner lives in `sandboxed_agent_eval_harness.evaluation.runner`. It can run repeated trials over the default or benchmark task suite, execute fixture-backed tool adapters, write JSONL traces and a `summary.json`, execute deterministic validators, aggregate per-validator metrics, calculate pass@k, report a failure taxonomy, track correctness for constraints, unit tests, deterministic policy terms, and cost/latency limits, and preserve a separate final-answer-only pass signal for silent-failure studies.

Smoke command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --trials 1 --output-dir artifacts/eval_runs/smoke
```

Benchmark command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite benchmark \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir artifacts/eval_runs/benchmark
```

## Model Adapters And Silent Failure Study

Model adapter primitives live in `sandboxed_agent_eval_harness.models`.

They provide:

- `RecordedModelAdapter`
- `OpenAIResponsesAdapter`
- `GenericHTTPModelAdapter`
- `load_recorded_model_adapters()`
- `ModelAdapterAgent`

The recorded adapter replays fixture-safe model plans from `fixtures/model_outputs/silent_failure_study.json`, so local validation can show model-style silent failures without network access, credentials, or paid APIs. The optional OpenAI Responses and generic HTTP adapters build live requests through injectable transports; tests use injected transports and missing-credential skip paths, so default validation never calls the network.

Silent failure study command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir artifacts/eval_runs/silent_failure_study
```

The fixture-backed study currently records a `recorded-gpt-style-v1` model trace set where final-answer-only scoring passes 8/8 tasks, while deterministic validators pass 4/8 and catch four silent failures across unsupported citation, missing unit tests, missing state mutation, tool sequence mismatch, numeric mismatch, and constraint violation.

Benchmark recorded study command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir artifacts/eval_runs/benchmark_model_study
```

On the benchmark fixture suite, the recorded model trace set passes final-answer-only scoring on 64/64 tasks while deterministic validators pass 32/64 and catch 32 silent failures. This is fixture-backed evidence, not a live-provider benchmark.

## Recorded Model Matrix

The recorded model matrix runner lives in `sandboxed_agent_eval_harness.evaluation.model_matrix`.

It compares fixture-safe behavior profiles from `fixtures/model_outputs/model_matrix.json`:

- `recorded-good-fixture-v1`
- `recorded-overconfident-fixture-v1`
- `recorded-tool-sloppy-fixture-v1`
- `recorded-citation-sloppy-fixture-v1`
- `recorded-state-sloppy-fixture-v1`

Model matrix command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_matrix \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/model_matrix.json \
  --output-dir artifacts/eval_runs/model_matrix
```

The command writes `model_matrix_summary.json`, `model_comparison_report.md`, `silent_failure_by_model.csv`, the raw runner `summary.json`, and standard report artifacts. The default matrix is recorded and offline; it makes no live provider calls and should not be described as a public live-model benchmark.

## Credentials-Gated Live Provider Workflow

The live workflow CLI lives in `sandboxed_agent_eval_harness.evaluation.live_provider`.

It is intentionally opt-in:

- Running without `--live` fails closed.
- Running with `--live` but without credentials writes a skipped `summary.json` and exits successfully.
- Default tests and CI do not set credentials and do not run live provider calls.
- `--record-output` converts generated records into `recorded_fixture_candidate.json` for later deterministic replay.

Missing-credential skip smoke:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --live \
  --model-provider openai \
  --api-key-env SANDBOXED_AGENT_EVAL_MISSING_OPENAI_KEY \
  --output-dir /tmp/sandboxed-agent-eval-live-skip
```

Manual OpenAI live smoke, only when credentials are intentionally supplied:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --live \
  --model-provider openai \
  --model "$OPENAI_MODEL" \
  --max-tasks 1 \
  --max-cost-usd 0.25 \
  --record-output \
  --output-dir artifacts/live_runs/manual
```

Do not commit generated live artifacts, credentials, raw private prompts, or provider secrets.

## Report And Regression View

The report generator lives in `sandboxed_agent_eval_harness.evaluation.report`.

It reads a `summary.json` artifact plus trace metadata and writes:

- `report.json`
- `report.md`

The report includes an executive summary, domain success rates, final-answer-only vs validator pass rates, validator gap, silent failure rate, answer overclaim rate, normalized root-cause categories, failure breakdowns by domain/tool/model/validator, top replayable failure traces, pass@k curves, cost and latency summaries, worst trace paths, version metadata, and optional previous-run comparisons.

Smoke command:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.report \
  --summary artifacts/eval_runs/smoke/summary.json \
  --output-dir artifacts/reports/latest
```
