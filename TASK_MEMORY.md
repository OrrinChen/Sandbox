# Task Memory: Sandboxed Tool-Use Agent Evaluation Harness

## Latest Status

Current branch:
`codex/sandboxed-agent-eval-freeze`

Latest frozen phase commit:
`158ced7 docs: polish portfolio narrative and freeze roadmap`

Current phase:
Maintenance only. Roadmap is frozen after Phase 24.

Main blocker:
No implementation blocker. The benchmark suite is fixture-backed and default validation remains credential-free.

Next recommended action:
Maintain, fix bugs, refresh recorded evidence when needed, and keep claims tied to fixture-backed deterministic or recorded-offline evidence.

Latest maintenance update:
Phase 24 remains frozen. The S-level packaging polish improves the README first screen, adds a replayable failure walkthrough, and adds `make reproduce-report` without adding a new roadmap phase or changing the project from eval infrastructure into an agent product.

Verification:
- `python3 -m pytest tests/test_phase24_portfolio_freeze.py -v` passed with 4 tests.
- `make reproduce-report` passed and printed the expected 56.2 percentage point validator gap, 180 silent failures, and 320 recorded offline runs.
- `make ci` passed with 126 tests, oracle smoke 8/8, strict replay gate 8 traces replayed with 0 divergences, and recorded model study 4 silent failures.

Follow-up maintenance update:
The README first-screen benchmark card now includes validators and failure categories, keeps the 56.2 percentage point overestimate and 180 silent failures as the top result, and states that recorded model profiles are offline behavior profiles rather than a real-time model benchmark.

Optional integration update:
Added a LangChain/LangGraph/LangSmith adapter layer as optional AI infra integration, not a new roadmap phase. The layer keeps default validation credential-free and network-free: LangChain wraps fixture-backed tools, LangGraph-style runs emit graph node trace events and local checkpoints, and LangSmith writes local exports unless upload is explicitly requested with credentials.

Optional integration verification:
- `python3 -m pytest tests/test_optional_integrations.py -v` passed with 5 tests.
- `make optional-integrations-smoke` passed and wrote local LangChain descriptors, LangGraph trace/checkpoint artifacts, and a LangSmith local export with `upload=disabled`.
- `python3 -m pytest` passed with 131 tests.
- `make ci` passed with 131 tests, oracle smoke 8/8, strict replay gate 8 traces replayed with 0 divergences, and recorded model study 4 silent failures.

Compiled LangGraph workflow update:
`LangGraphRunner(backend="langgraph")` now builds a real compiled `StateGraph` with `InMemorySaver` checkpointing when optional LangGraph dependencies are installed. The default `local` backend remains dependency-free and `make ci` still avoids optional framework imports.

Compiled LangGraph workflow verification:
- `python3 -m pytest tests/test_optional_integrations.py -v` passed with 7 tests, including a fake LangGraph module check proving `StateGraph`, `compile(checkpointer=...)`, and `invoke(config={"configurable": {"thread_id": ...}})` are used.
- `make optional-integrations-smoke` passed with the default local backend and `upload=disabled`.
- `python3 -m pytest` passed with 133 tests.
- `make ci` passed with 133 tests, oracle smoke 8/8, strict replay gate 8 traces replayed with 0 divergences, and recorded model study 4 silent failures.

MCP maintenance integration update:
Added an optional fixture-backed MCP evaluation adapter after the Phase 24 freeze without adding a new roadmap phase. The adapter exposes harness tools through MCP-shaped `tools/list` descriptors and `tools/call` JSON-RPC requests, maps MCP calls/results into the existing JSONL trace format, and converts recorded MCP JSON-RPC exchanges back into deterministic harness trace events. It does not start a live MCP server, require credentials, or replace deterministic validators.

MCP maintenance verification:
- Initial TDD red run for `tests/test_mcp_integration.py -v` failed because `sandboxed_agent_eval_harness.integrations.mcp` and MCP documentation did not exist.
- `python3 -m pytest tests/test_mcp_integration.py -v` passed with 5 tests.
- `python3 -m pytest tests/test_optional_integrations.py tests/test_mcp_integration.py -v` passed with 12 tests.
- `make optional-integrations-smoke` passed and printed `mcp_fixture_trace=artifacts/integrations/mcp/fixture_tool_trace.jsonl` with `upload=disabled`.
- `python3 -m pytest` passed with 138 tests.
- `make ci` passed with 138 tests, oracle smoke 8/8, strict replay gate 8 traces replayed with 0 divergences, and recorded model study 4 silent failures.
- The GitHub Actions workflow is now included at the sandbox-only repo root `.github/workflows/sandboxed-agent-eval-harness-ci.yml`; it no longer assumes a parent monorepo working directory.

## Current State

Project folder:

```text
/Users/orynwilder/Documents/New project 2/sandboxed-agent-eval-harness
```

Git root:

```text
/Users/orynwilder/Documents/New project 2
```

Important note:
The git repository root contains multiple sibling projects. Treat `sandboxed-agent-eval-harness/` as the working project scope unless the user explicitly asks to touch other folders.

## Completed Phases

### Phase 0: Project Framing and Autonomous Workflow Scaffold

Commit:
Included in the Phase 1 skeleton commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Defined the project as an evaluation harness for exposing silent tool-use failures.
- Added a phase-based roadmap.
- Added project-level autonomous Codex instructions.
- Added validation and runbook documents.
- Kept the scope focused on typed tools, sandboxed execution, deterministic validators, trace replay, pass@k, and regression reporting.

Validation:
- `for f in README.md AGENTS.md ROADMAP.md TASK_MEMORY.md VALIDATION.md RUNBOOK.md; do test -s "$f" || exit 1; done` passed on 2026-04-30.
- `git diff --check -- .` passed on 2026-04-30.

Known limitations:
- Superseded by Phase 1. Package metadata, skeletal tests, and source layout now exist.

### Phase 1: Planning and Repository Skeleton

Commit:
Included in the Phase 1 skeleton commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `pyproject.toml` with setuptools metadata, pytest configuration, and a CLI entry point.
- Added initial config stubs under `configs/`.
- Added `src/sandboxed_agent_eval_harness/` package layout.
- Added subpackage placeholders for agents, tools, sandbox, tasks, validators, tracing, evaluation, and dashboard.
- Added a minimal CLI stub at `src/sandboxed_agent_eval_harness/cli.py`.
- Added Phase 1 skeleton tests in `tests/test_phase1_skeleton.py`.
- Updated `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md` to reflect the package skeleton and local `python3` commands.

Validation:
- Initial TDD red run failed because the package, `pyproject.toml`, configs, and source layout did not exist.
- `python3 -m pytest` passed with 5 tests.
- `PYTHONPATH=src python3 - <<'PY' ... import sandboxed_agent_eval_harness ... PY` passed.
- `PYTHONPATH=src python3 -m sandboxed_agent_eval_harness` passed and printed `sandboxed-agent-eval-harness 0.1.0`.
- `git diff --check -- .` passed.

Known limitations:
- Core schemas do not exist yet.
- Tool registry does not exist yet.
- Sandbox execution and trace replay do not exist yet.
- Config files are intentionally stubs.

### Phase 2: Core Schemas

Commit:
Included in the Phase 2 core schemas commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/schemas.py`.
- Implemented `TaskSpec`, `ToolSpec`, `TraceEvent`, `ValidatorResult`, and `RunResult`.
- Added deterministic `SchemaValidationError` failures for missing fields, invalid limits, invalid tool arguments, trace sequence errors, failed validator metadata, and inconsistent run status.
- Added plain-dict serialization for all core schemas.
- Added JSONL-compatible serialization for `TraceEvent`.
- Added nested run result serialization for trace events and validator results.
- Added schema tests in `tests/test_tool_schemas.py` and `tests/test_trace_schema.py`.
- Updated `ROADMAP.md` and `README.md` for the completed phase.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.schemas` did not exist.
- Additional red run confirmed non-object tool arguments raised `TypeError`; implementation was tightened to raise `SchemaValidationError`.
- `python3 -m pytest tests/test_tool_schemas.py tests/test_trace_schema.py -v` passed with 13 tests.
- `python3 -m pytest` passed with 18 tests.
- `PYTHONPATH=src python3 - <<'PY' ... import schema classes ... PY` passed.
- `git diff --check -- .` passed.

Known limitations:
- JSON object schema support is intentionally minimal: only `type`, `required`, and `properties` are enforced.
- Tool registry does not exist yet.
- Schema classes do not load YAML config files yet.
- Sandbox execution and trace replay do not exist yet.

### Phase 3: Tool Registry

Commit:
Included in the Phase 3 tool registry commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/tools/registry.py`.
- Implemented `ToolRegistry`, `ToolRegistryError`, `UnknownToolError`, and `DuplicateToolError`.
- Added registry lookup by tool name.
- Added duplicate-name rejection.
- Added input validation and output validation through `ToolSpec`.
- Added metadata access for permissions, side effects, state mutation, and failure modes.
- Added default fixture-backed finance tool declarations: `financial_statement.lookup` and `transcript.search`.
- Added default local CSV/data-analysis tool declarations: `csv.read` and `csv.group_metrics`.
- Updated `configs/tools.yaml` to mirror the default tool names and metadata.
- Exported registry APIs from `sandboxed_agent_eval_harness.tools`.
- Added registry tests in `tests/test_tool_registry.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.tools.registry` did not exist.
- Config sync red run failed because `configs/tools.yaml` was still a stub.
- `python3 -m pytest tests/test_tool_registry.py -v` passed with 9 tests.
- `python3 -m pytest` passed with 27 tests.
- `PYTHONPATH=src python3 - <<'PY' ... default_tool_registry ... PY` passed.
- `git diff --check -- .` passed.

Known limitations:
- Registry stores declarations and validation paths only; it does not execute tools.
- `configs/tools.yaml` mirrors default declarations but is not parsed into runtime objects yet.
- No sandbox exists yet, so write permissions and state mutation metadata are declarative only.
- No real finance or CSV fixtures exist yet.

### Phase 4: Sandbox and State Tracking

Commit:
Included in the Phase 4 sandbox commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/sandbox/filesystem.py`.
- Added `src/sandboxed_agent_eval_harness/sandbox/subprocess.py`.
- Implemented `FileSystemSandbox` with workspace-only path resolution.
- Added optional read allowlist enforcement.
- Added deterministic workspace reset from initial files.
- Added `StateSnapshot` and `StateDiff` for added/modified/deleted file tracking.
- Added trace-compatible state diff serialization through existing `TraceEvent` payloads.
- Added `run_python_subprocess()` with workspace cwd and timeout enforcement.
- Exported sandbox APIs from `sandboxed_agent_eval_harness.sandbox`.
- Updated `configs/sandbox.yaml` to document task-workspace mode, read allowlist, state diff, and Python subprocess timeout support.
- Added sandbox tests in `tests/test_sandbox_limits.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `FileSystemSandbox` was not exported.
- Additional red run failed because `readable_paths` allowlist support did not exist.
- `python3 -m pytest tests/test_sandbox_limits.py -v` passed with 8 tests.
- `python3 -m pytest` passed with 35 tests.
- `PYTHONPATH=src python3 - <<'PY' ... FileSystemSandbox ... PY` passed.
- `git diff --check -- .` passed.

Known limitations:
- The subprocess helper provides cwd and timeout control, not OS-level sandbox isolation.
- File access constraints are enforced through the `FileSystemSandbox` API.
- Tool execution is still not wired into sandbox execution.

### Phase 5: Trace Logging and Replay

Commit:
Included in the Phase 5 trace logging and replay commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/tracing/jsonl.py`.
- Implemented `TraceLogger` for ordered JSONL trace persistence.
- Added trace events for user messages, agent messages, tool calls, tool results, state diffs, validator results, timeout events, and error events.
- Implemented `load_trace_events()` with malformed JSONL and schema error handling.
- Implemented `TraceReplay` with fixture-state capture and contiguous sequence validation.
- Exported tracing APIs from `sandboxed_agent_eval_harness.tracing`.
- Added trace/replay tests in `tests/test_trace_replay.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `TraceLogger` was not exported.
- `python3 -m pytest tests/test_trace_replay.py -v` passed with 5 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Replay reconstructs event order and fixture context for debugging; it does not execute tool calls.
- Trace capture is not yet wired into an evaluation runner because the runner does not exist yet.

### Phase 6: Deterministic Validators

Commit:
Included in the Phase 6 deterministic validators commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/validators/core.py`.
- Implemented schema, tool sequence, argument, state, numeric, and citation validators.
- Kept all validator outputs on the existing `ValidatorResult` schema.
- Added deterministic failure types for schema mismatches, wrong tool sequences, invalid tool arguments, state mismatches, numeric mismatches, and unsupported or missing citations.
- Exported validator APIs from `sandboxed_agent_eval_harness.validators`.
- Updated `configs/validators.yaml` with default validator names, purposes, and failure types.
- Added validator tests in `tests/test_validators.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `default_validator_names` was not exported.
- `python3 -m pytest tests/test_validators.py -v` passed with 7 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Validators are standalone deterministic functions; they are not wired into an evaluation runner yet.
- Citation parsing intentionally supports simple bracketed fixture source ids such as `[aapl-2023-10k]`.

### Phase 7: Initial Task Suites

Commit:
Included in the Phase 7 initial task suites commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/tasks/suites.py`.
- Implemented `TaskSuite`, `TaskSuiteValidationError`, `load_task_suite()`, `default_task_suite()`, and `default_task_suite_path()`.
- Added `fixtures/tasks/initial_suite.json` with three fixture-backed finance tasks and three local CSV/data-analysis tasks.
- Added finance fixtures for AAPL FY2023 revenue, MSFT FY2024 commercial cloud metrics, and NVDA FY2024 data center transcript evidence.
- Added CSV fixtures for regional sales, customer churn, and inventory stockout workflows.
- Updated `configs/task_suites.yaml` with the initial suite id, version, manifest path, domains, and task ids.
- Added task suite tests in `tests/test_task_suites.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `TaskSuiteValidationError` was not exported.
- `python3 -m pytest tests/test_task_suites.py -v` passed with 6 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Tasks are loadable and validator-mapped, but there is not yet an evaluation runner to execute them.
- Fixture contents are small synthetic examples intended for deterministic harness validation, not broad benchmark coverage.

### Phase 8: Agent Baselines and Evaluation Runner

Commit:
Included in the Phase 8 agent baselines and evaluation runner commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/agents/baselines.py`.
- Implemented deterministic single-shot, ReAct-style, planner-executor, and oracle-tool-selection baselines.
- Added `src/sandboxed_agent_eval_harness/evaluation/runner.py`.
- Implemented repeated trials over task suites and agent baselines.
- Wrote JSONL trace artifacts for each run and `summary.json` for the aggregate run.
- Executed deterministic validators for schema, tool sequence, arguments, state, numeric outputs, and citations.
- Aggregated task success rate, pass@k, per-validator metrics, failure taxonomy, tool selection accuracy, argument correctness, state correctness, numeric correctness, citation correctness, turns, latency, cost, and timeout rate.
- Ignored generated run artifacts under `artifacts/`.
- Updated `configs/eval_runs.yaml` with the smoke run preset.
- Added evaluation runner tests in `tests/test_eval_runner.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `default_agent_baselines` was not exported.
- `python3 -m pytest tests/test_eval_runner.py -v` passed with 4 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Baselines are deterministic fixture-compatible simulations; they do not call external models.
- Tool calls are planned and traced with fixture-shaped results; full tool execution is still shallow.
- The runner writes artifacts and summaries but does not yet generate a portfolio report or regression comparison view.

### Phase 9: Report and Regression View

Commit:
Included in the Phase 9 report and regression view commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/evaluation/report.py`.
- Implemented report generation from `summary.json` or in-memory `EvaluationSummary` objects.
- Generated domain success summaries.
- Compared final-answer-only pass rate with validator pass rate.
- Generated failure type distribution and failure insight summaries.
- Generated pass@k curves from repeated trials.
- Summarized cost, latency, turns, and timeout rate overall and by baseline.
- Listed worst failed traces with failure types, replay readiness, and version metadata.
- Compared current runs against a previous summary artifact.
- Wrote `report.json` and `report.md` artifacts.
- Added `final_answer_passed` to runner metrics for report comparison.
- Added report tests in `tests/test_report.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.evaluation.report` did not exist.
- `python3 -m pytest tests/test_report.py -v` passed with 3 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- The final-answer-only score is a deterministic harness proxy based on whether the baseline produced an answer, not semantic judging.
- Report generation relies on existing summary and trace artifacts; it does not execute replay itself.
- Previous-run comparison reports metric deltas and version metadata, but it does not enforce pass/fail regression thresholds yet.

### Phase 10: Executable Fixture Tool Adapters

Commit:
Included in the Phase 10 executable fixture-backed tool adapters commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/tools/execution.py`.
- Implemented `FixtureToolExecutor` and `ToolExecutionError`.
- Executed `financial_statement.lookup` from local JSON finance fixtures.
- Executed `transcript.search` from local transcript fixtures.
- Executed `csv.read` against visible CSV fixtures copied into a sandbox workspace.
- Executed `csv.group_metrics` by writing deterministic output CSV files in the sandbox workspace.
- Wired the evaluation runner to execute fixture-backed tool calls instead of trusting baseline-provided placeholder results.
- Captured state diffs from real sandbox snapshots.
- Added execution metadata and workspace paths to run metrics.
- Added executable tool adapter tests in `tests/test_tool_execution.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `FixtureToolExecutor` was not exported.
- First implementation run exposed an output-read allowlist issue; executor sandbox setup was adjusted to rely on workspace isolation while allowing generated outputs to be read.
- `python3 -m pytest tests/test_tool_execution.py -v` passed with 3 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Baselines still plan tool choices and arguments deterministically; only tool execution results now come from executable adapters.
- The executor covers the current default fixture tools only.
- Trace replay can inspect persisted tool results but still does not re-execute persisted tool calls.

### Phase 11: Trace Replay Execution

Commit:
Included in the Phase 11 trace replay execution commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/tracing/execution.py`.
- Implemented `TraceReplayExecutor`, `TraceReplayExecutionResult`, and `TraceReplayExecutionError`.
- Re-executed persisted `tool_call` events with `FixtureToolExecutor`.
- Compared recorded `tool_result` payloads with replayed tool outputs.
- Recomputed sandbox state diffs from replay execution.
- Compared recorded and replayed state diffs.
- Added deterministic divergence records for tool result and state diff mismatches.
- Exported replay execution APIs from `sandboxed_agent_eval_harness.tracing`.
- Added replay execution tests in `tests/test_trace_replay_execution.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `TraceReplayExecutor` was not exported.
- `python3 -m pytest tests/test_trace_replay_execution.py -v` passed with 3 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Replay execution covers the current default task suite and fixture-backed tools.
- Replay execution detects tool result and state diff divergence, but it does not yet enforce regression thresholds.
- Replay execution is not yet integrated into the report generator as a summarized section.

### Phase 12: Regression Threshold Gates

Commit:
Included in the Phase 12 regression threshold gates commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `src/sandboxed_agent_eval_harness/evaluation/gates.py`.
- Implemented `RegressionGateResult`, `RegressionGateReport`, and `evaluate_regression_gates()`.
- Added threshold support for minimum task success rate, minimum pass@k, maximum task success drop, maximum pass@k drop, maximum configured failure taxonomy counts, and maximum replay divergence count.
- Added a gate CLI that reads summary and threshold JSON artifacts, optionally replays trace JSONL files, prints a structured report, and exits non-zero when configured gates fail.
- Added replay divergence summaries to evaluation reports when replay execution results are supplied.
- Added regression gate tests in `tests/test_regression_gates.py`.
- Added report coverage for replay divergence summaries in `tests/test_report.py`.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.evaluation.gates` did not exist.
- Report red run failed because `build_evaluation_report()` did not yet accept `replay_results`.
- Final regression gate test run passed with 4 tests.
- Final report test run passed with 4 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Gate thresholds are supplied as JSON artifacts or in-memory mappings; project config files do not load them yet.
- The gate CLI can replay explicit trace paths, but it does not yet discover a run's trace set automatically.
- Replay divergence gates cover deterministic replay results only; new task domains need executable adapters before replay gates are meaningful.

### Phase 13: Config-backed Gate Presets and Trace Discovery

Commit:
Included in the Phase 13 config-backed gate presets commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `configs/regression_gates.json` with `strict_smoke` and `portfolio_regression` presets.
- Added `RegressionGatePreset`.
- Added `default_threshold_config_path()`.
- Added `load_threshold_preset()`.
- Added `discover_trace_paths()`.
- Extended the gate CLI with `--threshold-preset`, `--threshold-config`, and `--discover-traces`.
- Kept backward-compatible `--thresholds` JSON artifact support.
- Rejected ambiguous CLI calls that pass both `--thresholds` and `--threshold-preset`.
- Included preset metadata in structured gate reports.
- Added tests for config-backed presets, summary trace discovery, and preset CLI smoke.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because `default_threshold_config_path`, `load_threshold_preset`, and `discover_trace_paths` did not exist.
- Additional red run failed because the CLI allowed both direct threshold files and presets, which could make report metadata misleading.
- Final regression gate test run passed with 8 tests.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Gate presets are JSON-backed to avoid adding a YAML parser dependency.
- The CLI can discover traces from summary run records, but it does not yet filter trace discovery by task, baseline, or domain.
- Repository-root CI workflow files are still deferred because this project is scoped to `sandboxed-agent-eval-harness/` inside a larger git root.

### Phase 14: Portfolio-grade Deterministic Suite Expansion

Commit:
Included in the Phase 14 portfolio-grade deterministic suite expansion commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added a sandboxed coding fixture task: `coding-discount-total-fix`.
- Added a deterministic optimization fixture task: `optimization-newsvendor-order`.
- Added code fixtures under `fixtures/code/`.
- Added an optimization fixture under `fixtures/optimization/`.
- Added default tool specs for `code.patch`, `python.unit_tests`, and `optimization.solve_newsvendor`.
- Implemented executable adapters for code patching, sandboxed Python unit test execution, and a small newsvendor solver.
- Added deterministic validators for constraints, unit tests, policy terms, and cost/latency/turn/timeout limits; policy validation is exercised by the optimization fixture task.
- Wired the new validators into the evaluation runner and aggregate metrics.
- Updated deterministic baselines to plan coding and optimization tool calls.
- Updated task, tool, validator, and eval-run configs.
- Added tests for expanded domains, tools, validators, execution, runner behavior, and replay execution.
- Updated `ROADMAP.md`, `README.md`, and `VALIDATION.md` for the completed phase.

Validation:
- Initial TDD red run failed because the new validator APIs did not exist.
- Final focused portfolio-suite test run passed before commit and is recorded in the validation log.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Coding and optimization fixtures are intentionally small deterministic slices, not broad benchmarks.
- The sandboxed Python test runner executes local fixture tests only; it is not a general secure code execution product.
- Optimization coverage currently includes one small newsvendor instance; broader OR task families remain deferred.

### Phase 15: Real Model Adapter and Silent Failure Study

Commit:
Included in the Phase 15 real model adapter and silent failure study commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `sandboxed_agent_eval_harness.models` with `RecordedModelAdapter`, `OpenAIResponsesAdapter`, and recorded adapter loading.
- Added `ModelAdapterAgent` so recorded model plans can run through the existing evaluation runner.
- Added `final_answer_passed` to `AgentRunPlan` and runner metrics so final-answer-only scoring can be compared against validator pass rate.
- Added `fixtures/model_outputs/silent_failure_study.json` with eight recorded model-style outputs across the default suite.
- Added `sandboxed_agent_eval_harness.evaluation.model_study` CLI.
- The recorded study writes `summary.json`, report artifacts, and `silent_failure_study.json`.
- The current fixture demonstrates final-answer-only pass rate 1.000 versus validator pass rate 0.500, with four silent failures caught by deterministic validators.
- Updated `README.md`, `ROADMAP.md`, `VALIDATION.md`, `RUNBOOK.md`, and `configs/models.yaml`.

Validation:
- Initial TDD red run failed because `ModelAdapterAgent`, `sandboxed_agent_eval_harness.models`, and `evaluation.model_study` did not exist.
- Focused model adapter and model study tests passed before commit and are recorded in the validation log.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- `OpenAIResponsesAdapter` is opt-in and tested with injected transport only; default validation does not call live APIs.
- The recorded model fixture is evidence that the harness can expose model-style silent failures, not a benchmark-scale real provider result.
- Live provider cost accounting still needs credentials-gated experiments and provider-specific usage normalization.

### Phase 16: Reproducibility and CI

Commit:
Included in the Phase 16 reproducibility and CI commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added project `Makefile` targets: `test`, `smoke`, `gate`, `model-study`, `report`, and `ci`.
- Added GitHub Actions workflow at `.github/workflows/sandboxed-agent-eval-harness-ci.yml`.
- Scoped all workflow run steps to `working-directory: sandboxed-agent-eval-harness`.
- Kept CI default path credential-free and free of live model flags.
- Uploaded generated `artifacts/` from CI.
- Added tests that assert reproducibility targets, workflow working-directory, no live credential references, and ignored artifact outputs.
- Updated `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `Makefile` and GitHub Actions workflow did not exist.
- Focused Phase 16 CI tests passed before commit and are recorded in the validation log.
- `make ci` passed before commit and is recorded in the validation log.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Local validation can verify workflow file contents, but actual GitHub Actions execution still requires pushing to GitHub.
- The workflow uses GitHub-hosted actions and package installation infrastructure, but project tests and smoke runs do not call live model/data APIs.
- CI currently runs the default 8-task smoke suite; benchmark validation is available as a phase-specific command and is not part of default CI runtime.

### Phase 17: Benchmark-Scale Deterministic Suite Expansion

Commit:
Included in the Phase 17 benchmark-scale deterministic suite expansion commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `fixtures/tasks/benchmark_suite.json` with 64 deterministic fixture-backed tasks.
- Added named suite loading for `smoke` and `benchmark`.
- Added `benchmark_task_suite()`, `benchmark_task_suite_path()`, `task_suite_by_name()`, and `known_task_suites()`.
- Added `--suite benchmark` to the evaluation runner.
- Added `--suite benchmark` to the recorded model study CLI.
- Updated deterministic baselines to read explicit per-task tool arguments from hidden expected state instead of relying only on task-id heuristics.
- Updated trace replay execution to resolve traces against all known fixture-backed suites by default.
- Expanded `fixtures/model_outputs/silent_failure_study.json` so the recorded model fixture can run on the 64-task benchmark suite.
- Updated `configs/task_suites.yaml`, `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `benchmark_task_suite` was not exported.
- Focused Phase 17 tests passed before commit and are recorded in the validation log.
- Full pytest passed before commit and is recorded in the validation log.
- Oracle benchmark run passed with task success rate 1.000 and pass@k 1.000.
- Benchmark gate replay discovered and replayed all 64 oracle traces with zero divergences.
- Recorded benchmark model study produced 32 silent failures with final-answer pass rate 1.000 and validator pass rate 0.500.

Known limitations:
- The benchmark suite is deterministic and fixture-backed; it is not a live-provider or third-party public benchmark.
- The original recorded benchmark study uses one recorded model profile; Phase 19 adds a separate recorded model matrix for multiple behavior signatures.
- The expanded suite reuses current executable fixture tools instead of adding new tool families.

### Phase 18: Failure Taxonomy v2 and Root-Cause Report

Commit:
Included in the Phase 18 failure taxonomy v2 and root-cause report commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added normalized Phase 18 root-cause categories in `evaluation.report`.
- Added deterministic mapping from validator failure types to root-cause categories.
- Added final-answer validator gap, silent failure rate, and answer overclaim rate to report output.
- Added root-cause breakdowns by domain, tool, model, and validator.
- Added top replayable failure traces to root-cause summaries.
- Added machine-readable `root_cause_summary` and `executive_summary` to `report.json`.
- Added an executive summary section to `report.md`.
- Added `root_cause_breakdown` to `silent_failure_study.json`.
- Updated README, roadmap, validation, and runbook documentation for the new report surface.

Validation:
- Initial TDD red run failed because `ROOT_CAUSE_CATEGORIES` and root-cause report APIs did not exist.
- Focused Phase 18 tests passed before commit and are recorded in the validation log.
- Full pytest passed before commit and is recorded in the validation log.
- Benchmark root-cause model study wrote `silent_failure_study.json`, `report.json`, and `report.md` with root-cause fields.
- Default `make ci` passed before commit.

Known limitations:
- Root-cause categories are deterministic mappings from validators and traces; they are not subjective natural-language explanations.
- Tool-level breakdowns attribute a failed run to tools present in the trace, which is useful for debugging but not a causal proof for every tool in a multi-tool trace.
- Model-profile comparison is handled by the Phase 19 recorded matrix; portfolio packaging remains deferred to Phase 23.

### Phase 19: Recorded Model Matrix

Commit:
Included in the Phase 19 recorded model matrix commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `sandboxed_agent_eval_harness.evaluation.model_matrix`.
- Added offline recorded matrix fixture `fixtures/model_outputs/model_matrix.json`.
- Added five fixture-safe model behavior profiles: good, overconfident, tool sloppy, citation sloppy, and state sloppy.
- Added matrix artifact generation for `model_matrix_summary.json`, `model_comparison_report.md`, and `silent_failure_by_model.csv`.
- Reused the existing evaluation runner, deterministic validators, and root-cause report surface.
- Added model-matrix tests that verify profile coverage, artifact generation, CSV fields, markdown output, sorting, and distinct failure signatures.
- Updated `configs/models.yaml`, `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.evaluation.model_matrix` did not exist.
- Focused Phase 19 tests passed before commit and are recorded in the validation log.
- The benchmark recorded model matrix produced 5 models, 320 runs, 5 distinct failure signatures, and max validator gap 1.000.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- The model matrix uses controlled recorded behavior profiles, not live provider outputs.
- The profiles are designed to exercise failure signatures and should not be described as claims about specific public model providers.
- Portfolio-ready narrative and case-study packaging remain deferred to Phase 23 and Phase 24.

### Phase 20: Credentials-Gated Live Provider Workflow

Commit:
Included in the Phase 20 credentials-gated live provider workflow commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `sandboxed_agent_eval_harness.evaluation.live_provider`.
- Added `GenericHTTPModelAdapter` alongside the existing `OpenAIResponsesAdapter`.
- Added CLI flags for `--model-provider`, `--live`, `--max-cost-usd`, `--max-tasks`, and `--record-output`.
- Made live workflow fail closed without `--live`.
- Made live workflow skip cleanly without credentials and write a skipped `summary.json`.
- Added recorded fixture candidate conversion through `recorded_fixture_candidate.json`.
- Added `raw_outputs.jsonl` generation only when `--record-output` is used and records exist.
- Added tests that exercise OpenAI and generic HTTP paths through injected transports only.
- Updated `configs/models.yaml`, `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.evaluation.live_provider` did not exist.
- Focused Phase 20 tests passed before commit and are recorded in the validation log.
- Fail-closed CLI smoke returned exit code 2 without writing a summary artifact.
- Missing-credential CLI smoke skipped without a network call and wrote `summary.json`.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- No real live provider call was run in default validation because credentials are intentionally not required.
- Live artifacts are candidates for later recorded fixtures; they should be reviewed before committing any converted fixture.
- The default model name is only a convenience and should be overridden explicitly for manual live runs when provider model names change.

### Phase 21: Sandbox Backend Hardening

Commit:
Included in the Phase 21 sandbox backend hardening commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `sandboxed_agent_eval_harness.sandbox.backends`.
- Added `LocalWorkspaceBackend`, `DockerSandboxBackend`, `SandboxBackendConfig`, and backend factory loading.
- Kept the workspace backend as the default behavior.
- Added Docker command construction with `--network none`, memory/CPU/PID limits, read-only fixture mount, writable workspace mount, read-only root filesystem, and tmpfs for `/tmp`.
- Routed sandboxed Python unit-test execution through the selected backend.
- Added deterministic artifact export for workspace outputs.
- Added `--sandbox-backend workspace|docker` to the evaluation runner.
- Added run metadata for the selected sandbox backend.
- Added Phase 21 tests for workspace compatibility, Docker command policy, injected Docker unit-test execution, CLI backend selection, and documentation anti-overclaim wording.
- Updated `configs/sandbox.yaml`, `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `DockerSandboxBackend` was not exported.
- Documentation anti-overclaim test failed until README explicitly described Docker as evaluation isolation and not a security product.
- Focused Phase 21 tests passed before commit and are recorded in the validation log.
- Workspace backend smoke passed with the oracle smoke suite.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- Default validation does not require Docker and does not start real containers.
- Docker command execution is optional and depends on a local Docker daemon when used manually.
- The Docker backend is an evaluation isolation backend, not a general security sandbox.

### Phase 22: Config Loader and Suite Registry Cleanup

Commit:
Included in the Phase 22 runtime config loading and validation commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `sandboxed_agent_eval_harness.config`.
- Added `load_tools_config()`, `load_validators_config()`, `load_task_suites_config()`, and `load_eval_runs_config()`.
- Added `validate_project_config()` with a machine-readable report.
- Added `python3 -m sandboxed_agent_eval_harness.config.validate`.
- Added `make validate-config` and wired it into `make ci`.
- Added deterministic validation that config tool names, validator names, task-suite manifests, task ids, eval-run baselines, and required metrics match runtime surfaces.
- Added Phase 22 tests for loader/runtime alignment, bad-config failure behavior, CLI output, and Makefile integration.
- Updated `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.config` did not exist.
- Focused Phase 22 tests passed before commit and are recorded in the validation log.
- Config validation CLI and `make validate-config` were run before commit.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- The YAML loader is intentionally project-specific and supports the current controlled config subset; it is not a general YAML parser.
- Regression gate presets remain JSON-backed and continue to use the existing gate loader.

### Phase 23: Public Portfolio Report

Commit:
Included in the Phase 23 portfolio evidence report commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Added `sandboxed_agent_eval_harness.evaluation.portfolio`.
- Added `make portfolio-report`.
- Generated `reports/portfolio_report.md`.
- Generated `reports/portfolio_report.json`.
- Generated `reports/tables/model_matrix.csv`.
- Generated `reports/tables/failure_taxonomy.csv`.
- Generated `reports/tables/domain_breakdown.csv`.
- Generated three replayable failure case studies under `reports/examples/`.
- Reused the recorded offline model matrix and deterministic root-cause report outputs.
- Added tests for public artifacts, case-study trace pointers, CLI output, and Makefile integration.
- Updated `README.md`, `ROADMAP.md`, `VALIDATION.md`, and `RUNBOOK.md`.

Validation:
- Initial TDD red run failed because `sandboxed_agent_eval_harness.evaluation.portfolio` did not exist.
- Focused Phase 23 tests passed before commit and are recorded in the validation log.
- `make portfolio-report` generated the public report, CSV tables, and case studies without API keys.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- The portfolio report uses recorded offline model profiles and fixture-backed benchmark tasks, not live-provider benchmark evidence.
- Case studies point to generated artifact traces under `artifacts/eval_runs/portfolio_model_matrix`; rerun `make portfolio-report` to regenerate those traces.

### Phase 24: README, Resume, and Interview Polish Freeze

Commit:
Included in the Phase 24 portfolio polish and roadmap freeze commit. The exact commit hash is reported by git after commit; it is not embedded here because this file participates in that commit.

What changed:
- Rewrote `README.md` into a concise reviewer-facing portfolio page.
- Added `docs/interview_notes.md` with the final resume bullet and interview talking points.
- Added `docs/architecture.md`.
- Added `docs/limitations.md`.
- Added `docs/failure_case_studies.md`.
- Marked Phase 24 complete and the roadmap frozen.
- Added Phase 24 validation instructions to `VALIDATION.md` and `RUNBOOK.md`.
- Added Phase 24 tests for README shape, docs coverage, roadmap freeze state, and validation/runbook coverage.

Validation:
- Initial TDD red run failed because README was too long, Phase 24 docs were missing, the roadmap was not frozen, and validation/runbook docs did not include Phase 24 checks.
- Focused Phase 24 tests passed before commit and are recorded in the validation log.
- Full validation was run before commit and recorded in the validation log.

Known limitations:
- The project is frozen as a portfolio artifact; future work should be maintenance, bug fixes, refreshed recorded evidence, or documentation polish.
- The benchmark and portfolio evidence remain recorded/offline and fixture-backed, not live-provider benchmark claims.

## Validation Log

### 2026-04-30

Commands run:

```bash
for f in README.md AGENTS.md ROADMAP.md TASK_MEMORY.md VALIDATION.md RUNBOOK.md; do test -s "$f" || exit 1; done
git diff --check -- .
git status --short -- .
wc -l README.md AGENTS.md ROADMAP.md TASK_MEMORY.md VALIDATION.md RUNBOOK.md .gitignore
```

Results:
- Required workflow files are present and non-empty.
- Whitespace check passed.
- Current project directory appears as untracked because the git root is the parent directory and the current branch has no commits yet.
- Documentation footprint after setup: 955 lines across workflow files and `.gitignore`.

Commands run for Phase 1:

```bash
python3 -m pytest tests/test_phase1_skeleton.py -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
import sandboxed_agent_eval_harness
print(sandboxed_agent_eval_harness.__name__)
PY
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness
git diff --check -- .
```

Results:
- The first corrected TDD red run failed for the expected missing Phase 1 artifacts.
- Final full pytest run passed: 5 tests.
- Package import smoke check passed.
- CLI smoke check passed.
- Whitespace check passed.

Commands run for Phase 2:

```bash
python3 -m pytest tests/test_tool_schemas.py tests/test_trace_schema.py -v
python3 -m pytest tests/test_tool_schemas.py::test_tool_spec_rejects_non_object_arguments_deterministically -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
from sandboxed_agent_eval_harness.schemas import (
    RunResult,
    TaskSpec,
    ToolSpec,
    TraceEvent,
    ValidatorResult,
)
print(TaskSpec.__name__, ToolSpec.__name__, TraceEvent.__name__, ValidatorResult.__name__, RunResult.__name__)
PY
git diff --check -- .
```

Results:
- The first Phase 2 red run failed because `sandboxed_agent_eval_harness.schemas` did not exist.
- The non-object argument red run failed with `TypeError` before validation was tightened.
- Final schema test run passed: 13 tests.
- Final full pytest run passed: 18 tests.
- Core schema import smoke check passed.
- Whitespace check passed.

Commands run for Phase 3:

```bash
python3 -m pytest tests/test_tool_registry.py -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
from sandboxed_agent_eval_harness.tools import default_tool_registry
registry = default_tool_registry()
print(" ".join(registry.names()))
PY
git diff --check -- .
```

Results:
- The first Phase 3 red run failed because `sandboxed_agent_eval_harness.tools.registry` did not exist.
- The config sync red run failed because `configs/tools.yaml` did not list default tool names.
- Final registry test run passed: 9 tests.
- Final full pytest run passed: 27 tests.
- Default registry smoke check passed.
- Whitespace check passed.

Commands run for Phase 4:

```bash
python3 -m pytest tests/test_sandbox_limits.py -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from sandboxed_agent_eval_harness.sandbox import FileSystemSandbox
with TemporaryDirectory() as tmp:
    sandbox = FileSystemSandbox(Path(tmp) / "workspace", initial_files={"input.txt": "1"})
    before = sandbox.snapshot()
    sandbox.write_text("output.txt", "2")
    print(before.diff(sandbox.snapshot()).to_dict())
PY
git diff --check -- .
```

Results:
- The first Phase 4 red run failed because sandbox APIs were missing from package exports.
- The read allowlist red run failed because `readable_paths` did not exist yet.
- Final sandbox test run passed: 8 tests.
- Final full pytest run passed: 35 tests.
- Sandbox state-diff smoke check passed.
- Whitespace check passed.

Commands run for Phase 5:

```bash
python3 -m pytest tests/test_trace_replay.py -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from sandboxed_agent_eval_harness.tracing import TraceLogger, TraceReplay
with TemporaryDirectory() as tmp:
    trace_path = Path(tmp) / "trace.jsonl"
    logger = TraceLogger(
        trace_path,
        run_metadata={
            "run_id": "smoke-run",
            "task_id": "finance-smoke",
            "agent_id": "fixture-agent",
            "model": "fixture-model",
            "prompt_version": "prompt-v1",
            "tool_version": "tools-v1",
            "task_version": "task-v1",
            "fixture_version": "fixtures-v1",
        },
    )
    logger.log_user_message("Run smoke task.")
    logger.log_tool_call("csv.read", {"path": "fixtures/data/sales.csv"})
    logger.log_tool_result("csv.read", {"path": "fixtures/data/sales.csv", "rows": 1})
    replay = TraceReplay.from_jsonl(
        trace_path,
        fixture_state={"fixtures/data/sales.csv": "region,revenue\nwest,10\n"},
    )
    print([event.event_type for event in replay.events], replay.metadata["task_version"])
PY
git diff --check -- .
```

Results:
- The first Phase 5 red run failed because `TraceLogger` was not exported.
- Final trace/replay test run passed: 5 tests.
- Final full pytest run passed: 40 tests.
- Trace replay smoke check passed.
- Whitespace check passed.

Commands run for Phase 6:

```bash
python3 -m pytest tests/test_validators.py -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.tools import default_tool_registry
from sandboxed_agent_eval_harness.validators import (
    default_validator_names,
    validate_tool_arguments,
    validate_tool_sequence,
)
events = [
    TraceEvent(
        event_id="evt-001",
        event_type="tool_call",
        sequence=0,
        payload={
            "tool_name": "financial_statement.lookup",
            "arguments": {"ticker": "AAPL", "fiscal_year": 2023, "statement": "income"},
        },
    )
]
print(default_validator_names())
print(validate_tool_sequence(events, expected_sequence=["financial_statement.lookup"]).passed)
print(validate_tool_arguments(events, default_tool_registry()).passed)
PY
git diff --check -- .
```

Results:
- The first Phase 6 red run failed because `default_validator_names` was not exported.
- Final validator test run passed: 7 tests.
- Final full pytest run passed: 47 tests.
- Validator smoke check passed.
- Whitespace check passed.

Commands run for Phase 7:

```bash
python3 -m pytest tests/test_task_suites.py -v
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
from collections import Counter
from sandboxed_agent_eval_harness.tasks import default_task_suite
suite = default_task_suite()
domain_counts = Counter(task.domain for task in suite.tasks)
print(suite.suite_id, suite.version, len(suite.tasks), dict(domain_counts))
print(" ".join(suite.task_ids()))
PY
git diff --check -- .
```

Results:
- The first Phase 7 red run failed because `TaskSuiteValidationError` was not exported.
- Final task suite test run passed: 6 tests.
- Final full pytest run passed: 53 tests.
- Task suite smoke check passed.
- Whitespace check passed.

Commands run for Phase 8:

```bash
python3 -m pytest tests/test_eval_runner.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-smoke
git diff --check -- .
```

Results:
- The first Phase 8 red run failed because `default_agent_baselines` was not exported.
- Final evaluation runner test run passed: 4 tests.
- Final full pytest run passed: 57 tests.
- CLI smoke check passed and printed `runs=6 task_success_rate=1.000 pass_at_k=1.000`.
- Whitespace check passed.

### 2026-05-01

Commands run for Phase 9:

```bash
python3 -m pytest tests/test_report.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --trials 2 --output-dir /tmp/sandboxed-agent-eval-report-current
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 2 --output-dir /tmp/sandboxed-agent-eval-report-previous
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.report --summary /tmp/sandboxed-agent-eval-report-current/summary.json --previous-summary /tmp/sandboxed-agent-eval-report-previous/summary.json --output-dir /tmp/sandboxed-agent-eval-report
git diff --check -- .
```

Results:
- The first Phase 9 red run failed because `sandboxed_agent_eval_harness.evaluation.report` did not exist.
- Final report test run passed: 3 tests.
- Final full pytest run passed: 60 tests.
- Current-run smoke check passed and printed `runs=48 task_success_rate=0.625 pass_at_k=0.625`.
- Previous-run smoke check passed and printed `runs=12 task_success_rate=1.000 pass_at_k=1.000`.
- Report CLI smoke check passed and wrote `report.json` and `report.md`.
- Whitespace check passed.

Commands run for Phase 10:

```bash
python3 -m pytest tests/test_tool_execution.py -v
python3 -m pytest tests/test_eval_runner.py tests/test_report.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-tool-execution
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from sandboxed_agent_eval_harness.tracing import load_trace_events
trace = Path("/tmp/sandboxed-agent-eval-tool-execution/traces/oracle_tool_selection_agent-data-sales-region-summary-000.jsonl")
events = load_trace_events(trace)
csv_read = next(event.payload["result"] for event in events if event.event_type == "tool_result" and event.payload["tool_name"] == "csv.read")
state_diff = next(event.payload for event in events if event.event_type == "state_diff")
print(csv_read)
print(state_diff)
PY
git diff --check -- .
```

Results:
- The first Phase 10 red run failed because `FixtureToolExecutor` was not exported.
- Final executable tool adapter test run passed: 3 tests.
- Final evaluation/report regression test run passed: 7 tests.
- Final full pytest run passed: 63 tests.
- Runner smoke check passed and printed `runs=6 task_success_rate=1.000 pass_at_k=1.000`.
- Trace inspection smoke printed executed CSV columns/row count and actual state diff.
- Whitespace check passed.

Commands run for Phase 11:

```bash
python3 -m pytest tests/test_trace_replay_execution.py -v
python3 -m pytest tests/test_trace_replay.py tests/test_trace_replay_execution.py tests/test_tool_execution.py tests/test_eval_runner.py tests/test_report.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-replay-execution
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor
trace = Path("/tmp/sandboxed-agent-eval-replay-execution/traces/oracle_tool_selection_agent-data-sales-region-summary-000.jsonl")
result = TraceReplayExecutor().replay(trace, workspace="/tmp/sandboxed-agent-eval-replay-workspace")
print(result.to_dict())
PY
git diff --check -- .
```

Results:
- The first Phase 11 red run failed because `TraceReplayExecutor` was not exported.
- Final replay execution test run passed: 3 tests.
- Final trace/tool/eval/report regression test run passed: 18 tests.
- Final full pytest run passed: 66 tests.
- Runner smoke check passed and printed `runs=6 task_success_rate=1.000 pass_at_k=1.000`.
- Replay execution smoke printed a passing replay result with two re-executed tool calls and no divergences.
- Whitespace check passed.

Commands run for Phase 12:

```bash
python3 -m pytest tests/test_regression_gates.py -v
python3 -m pytest tests/test_report.py -v
python3 -m pytest tests/test_regression_gates.py tests/test_report.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-gates-current
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
thresholds = {
    "min_task_success_rate": 1.0,
    "min_pass_at_k": 1.0,
    "max_replay_divergences": 0,
}
Path("/tmp/sandboxed-agent-eval-gates-thresholds.json").write_text(json.dumps(thresholds) + "\n")
PY
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates --summary /tmp/sandboxed-agent-eval-gates-current/summary.json --thresholds /tmp/sandboxed-agent-eval-gates-thresholds.json --replay-trace /tmp/sandboxed-agent-eval-gates-current/traces/oracle_tool_selection_agent-data-sales-region-summary-000.jsonl --replay-workspace /tmp/sandboxed-agent-eval-gates-replay
git diff --check -- .
```

Results:
- The first Phase 12 red run failed because `sandboxed_agent_eval_harness.evaluation.gates` did not exist.
- The report red run failed because replay divergence summaries were not accepted yet.
- Final regression gate test run passed: 4 tests.
- Final report test run passed: 4 tests.
- Final focused regression/report test run passed: 8 tests.
- Final full pytest run passed after implementation.
- Runner smoke check passed and printed `runs=6 task_success_rate=1.000 pass_at_k=1.000`.
- Gate CLI smoke check passed, printed a structured passing report, and included `divergence_count: 0`.
- Whitespace check passed.

Commands run for Phase 13:

```bash
python3 -m pytest tests/test_regression_gates.py -v
python3 -m pytest tests/test_phase1_skeleton.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-gate-preset-current
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates --summary /tmp/sandboxed-agent-eval-gate-preset-current/summary.json --threshold-preset strict_smoke --discover-traces --replay-workspace /tmp/sandboxed-agent-eval-gate-preset-replay
git diff --check -- .
```

Results:
- The first Phase 13 red run failed because preset and trace discovery APIs were missing.
- The CLI mutual-exclusion red run failed before `--thresholds` and `--threshold-preset` were made mutually exclusive.
- Final regression gate test run passed: 8 tests.
- Phase 1 config-layout test still passed with the added JSON gate config.
- Final full pytest run passed: 75 tests.
- Runner smoke check passed and printed `runs=6 task_success_rate=1.000 pass_at_k=1.000`.
- Gate preset CLI smoke check passed, discovered all oracle run traces, replayed them, and reported zero divergences.
- Whitespace check passed.

Commands run for Phase 14:

```bash
python3 -m pytest tests/test_task_suites.py tests/test_tool_registry.py tests/test_tool_execution.py tests/test_validators.py tests/test_eval_runner.py tests/test_trace_replay_execution.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-portfolio-suite
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates --summary /tmp/sandboxed-agent-eval-portfolio-suite/summary.json --threshold-preset strict_smoke --discover-traces --replay-workspace /tmp/sandboxed-agent-eval-portfolio-suite-replay
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.report --summary /tmp/sandboxed-agent-eval-portfolio-suite/summary.json --output-dir /tmp/sandboxed-agent-eval-portfolio-report
git diff --check -- .
```

Results:
- The first Phase 14 red run failed because new validators and fixtures were not implemented yet.
- Final focused portfolio-suite test run passed after implementation.
- Final full pytest run passed after implementation.
- Runner smoke check passed and printed `runs=8 task_success_rate=1.000 pass_at_k=1.000`.
- Gate preset CLI smoke check passed, discovered and replayed all eight oracle traces, and reported zero divergences.
- Report CLI smoke check passed and wrote a four-domain report with zero worst traces for the oracle run.
- Whitespace check passed.

Commands run for Phase 15:

```bash
python3 -m pytest tests/test_model_adapters.py tests/test_model_study.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study --recorded-output fixtures/model_outputs/silent_failure_study.json --output-dir /tmp/sandboxed-agent-eval-model-study
python3 -m pytest
git diff --check -- .
```

Results:
- The first Phase 15 red run failed because `ModelAdapterAgent`, `sandboxed_agent_eval_harness.models`, and `evaluation.model_study` did not exist.
- Focused model adapter and model study tests passed after implementation.
- Model study smoke printed `models=1 final_answer_pass_rate=1.000 validator_pass_rate=0.500 silent_failures=4`.
- Final full pytest run passed after implementation.
- Whitespace check passed.

Commands run for Phase 16:

```bash
python3 -m pytest tests/test_phase16_ci.py -v
make -n ci
make ci
python3 -m pytest
git diff --check -- .
```

Results:
- The first Phase 16 red run failed because `Makefile` and `.github/workflows/sandboxed-agent-eval-harness-ci.yml` did not exist.
- Focused Phase 16 CI tests passed after implementation.
- `make -n ci` showed pytest, oracle smoke, strict gate, recorded model study, and report generation.
- `make ci` passed after implementation.
- Final full pytest run passed after implementation.
- Whitespace check passed.

Commands run for Phase 17:

```bash
python3 -m pytest tests/test_phase17_benchmark_suite.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite benchmark --baseline oracle_tool_selection_agent --trials 1 --output-dir /tmp/sandboxed-agent-eval-benchmark
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates --summary /tmp/sandboxed-agent-eval-benchmark/summary.json --threshold-preset strict_smoke --discover-traces --replay-workspace /tmp/sandboxed-agent-eval-benchmark-replay
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study --suite benchmark --recorded-output fixtures/model_outputs/silent_failure_study.json --output-dir /tmp/sandboxed-agent-eval-benchmark-model-study
make ci
python3 -m pytest
git diff --check -- .
```

Results:
- The first Phase 17 red run failed because `benchmark_task_suite` was not exported.
- Focused Phase 17 benchmark tests passed after implementation.
- Final full pytest run passed: 95 tests.
- Benchmark oracle smoke passed and printed `runs=64 task_success_rate=1.000 pass_at_k=1.000`.
- Benchmark gate replay discovered and replayed all 64 oracle traces with zero divergences.
- Benchmark recorded model study passed and printed `models=1 final_answer_pass_rate=1.000 validator_pass_rate=0.500 silent_failures=32`.
- `make ci` passed on the default smoke reproducibility path.
- Final full pytest run passed: 95 tests.
- Whitespace check passed.

Commands run for Phase 18:

```bash
python3 -m pytest tests/test_phase18_root_cause.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study --suite benchmark --recorded-output fixtures/model_outputs/silent_failure_study.json --output-dir /tmp/sandboxed-agent-eval-root-cause-study
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
study = json.loads(Path("/tmp/sandboxed-agent-eval-root-cause-study/silent_failure_study.json").read_text())
report = json.loads(Path("/tmp/sandboxed-agent-eval-root-cause-study/report/report.json").read_text())
print(study["root_cause_breakdown"]["validator_gap"])
print(report["executive_summary"])
print(sorted(report["root_cause_summary"]["categories"]))
PY
make ci
git diff --check -- .
```

Results:
- The first Phase 18 red run failed because `ROOT_CAUSE_CATEGORIES` was not exported from `evaluation.report`.
- Focused Phase 18 root-cause tests passed after implementation.
- Final full pytest run passed: 99 tests.
- Benchmark root-cause model study passed and printed `models=1 final_answer_pass_rate=1.000 validator_pass_rate=0.500 silent_failures=32`.
- Root-cause artifact inspection printed validator gap `0.5`, the executive summary sentence, and all normalized root-cause categories.
- `make ci` passed on the default smoke reproducibility path.
- Whitespace check passed.

Commands run for Phase 19:

```bash
PYTHONPATH=src python3 -m pytest tests/test_phase19_model_matrix.py -v
python3 -m pytest tests/test_phase19_model_matrix.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_matrix --suite benchmark --recorded-output fixtures/model_outputs/model_matrix.json --output-dir /tmp/sandboxed-agent-eval-model-matrix
python3 -m pytest
make ci
git diff --check -- .
```

Results:
- The first Phase 19 red run failed because `sandboxed_agent_eval_harness.evaluation.model_matrix` did not exist.
- Focused Phase 19 model matrix tests passed: 3 tests.
- Benchmark model matrix CLI passed and printed `models=5 run_count=320 distinct_signatures=5 max_validator_gap=1.000`.
- The generated matrix summary reported final-answer-only grading overestimated validated correctness by 56.2 percentage points and deterministic validators caught 180 silent failures.
- Final full pytest run passed: 102 tests.
- `make ci` passed on the default smoke reproducibility path.
- Whitespace check passed.

Commands run for Phase 20:

```bash
PYTHONPATH=src python3 -m pytest tests/test_phase20_live_provider_workflow.py -v
python3 -m pytest tests/test_phase20_live_provider_workflow.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider --model-provider openai --output-dir /tmp/sandboxed-agent-eval-live-fail-closed
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider --live --model-provider openai --api-key-env SANDBOXED_AGENT_EVAL_MISSING_OPENAI_KEY --output-dir /tmp/sandboxed-agent-eval-live-skip
python3 -m pytest
make ci
git diff --check -- .
```

Results:
- The first Phase 20 red run failed because `sandboxed_agent_eval_harness.evaluation.live_provider` did not exist.
- Focused Phase 20 live provider workflow tests passed: 4 tests.
- Fail-closed CLI smoke printed `status=failed_closed reason=live_flag_required` and returned exit code 2.
- Missing-credential CLI smoke printed `status=skipped reason=missing_credentials ... records=0` and wrote skipped summary output without credentials.
- Final full pytest run passed after implementation.
- `make ci` passed on the default smoke reproducibility path.
- Whitespace check passed.

Commands run for Phase 21:

```bash
PYTHONPATH=src python3 -m pytest tests/test_phase21_sandbox_backends.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke --baseline oracle_tool_selection_agent --trials 1 --sandbox-backend workspace --output-dir /tmp/sandboxed-agent-eval-workspace-backend-smoke
python3 -m pytest
make ci
git diff --check -- .
```

Results:
- The first Phase 21 red run failed because `DockerSandboxBackend` was not exported from `sandboxed_agent_eval_harness.sandbox`.
- The documentation anti-overclaim test failed until README described Docker as evaluation isolation and not a security product.
- Focused Phase 21 sandbox backend tests passed after implementation.
- Workspace backend smoke printed `sandbox_backend=workspace` and passed oracle smoke.
- Final full pytest run passed after implementation.
- `make ci` passed on the default smoke reproducibility path.
- Whitespace check passed.

Commands run for Phase 22:

```bash
python3 -m pytest tests/test_phase22_config_loader.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate --json
make validate-config
python3 -m pytest
make ci
git diff --check -- .
```

Results:
- The first Phase 22 red run failed because `sandboxed_agent_eval_harness.config` did not exist.
- Focused Phase 22 config loader tests passed after implementation.
- Runtime config validation printed `config_validation=passed tools=7 validators=10 task_suites=2 eval_runs=1`.
- `make validate-config` passed and is part of `make ci`.
- Final full pytest passed: 119 tests.
- `make ci` passed with config validation, oracle smoke, strict gate, recorded model study, and report generation.

Commands run for Phase 23:

```bash
python3 -m pytest tests/test_phase23_portfolio_report.py -v
make portfolio-report
test -s reports/portfolio_report.md
test -s reports/portfolio_report.json
test -s reports/tables/model_matrix.csv
test -s reports/tables/failure_taxonomy.csv
test -s reports/tables/domain_breakdown.csv
test "$(find reports/examples -name 'replayable_failure_*.md' | wc -l)" -ge 3
python3 -m pytest
make ci
git diff --check -- .
```

Results:
- The first Phase 23 red run failed because `sandboxed_agent_eval_harness.evaluation.portfolio` did not exist.
- Focused Phase 23 tests passed after implementation.
- `make portfolio-report` printed `portfolio_report=reports/portfolio_report.md case_studies=3 models=5`.
- Portfolio artifacts include Markdown, JSON, model matrix CSV, failure taxonomy CSV, domain breakdown CSV, and three replayable failure case studies.
- Final full pytest passed: 122 tests.
- `make ci` passed with config validation, oracle smoke, strict gate, recorded model study, and report generation.

Commands run for Phase 24:

```bash
python3 -m pytest tests/test_phase24_portfolio_freeze.py -v
test -s docs/interview_notes.md
test -s docs/architecture.md
test -s docs/limitations.md
test -s docs/failure_case_studies.md
make portfolio-report
python3 -m pytest
make ci
git diff --check -- .
```

Results:
- The first Phase 24 red run failed because README was too long, docs were missing, roadmap was not frozen, and validation/runbook checks were absent.
- Focused Phase 24 freeze tests passed after implementation.
- `make portfolio-report` regenerated the portfolio report and replayable case-study artifacts.
- Final full pytest passed: 126 tests.
- `make ci` passed with config validation, oracle smoke, strict gate, recorded model study, and report generation.

## Important Decisions

- Decision: This project is eval infrastructure, not an agent product.
  Reason: The core value is catching silent tool-use failures that final-answer scoring misses.
  Date: 2026-04-30

- Decision: Deterministic validators come before LLM-as-judge.
  Reason: The project must produce reproducible evidence, not subjective grading only.
  Date: 2026-04-30

- Decision: Trace replay is core, not optional.
  Reason: A failure that cannot be replayed is weak evidence.
  Date: 2026-04-30

- Decision: Finance is one task suite, not the whole product.
  Reason: Large-scale financial ingestion and evidence graphs belong to the separate A1 project.
  Date: 2026-04-30

- Decision: MVP data should be fixture-backed by default.
  Reason: Live APIs and changing market/financial data would make deterministic validation noisy.
  Date: 2026-04-30

- Decision: Live model providers must be opt-in and tested through injected or recorded transports by default.
  Reason: Default validation should stay credential-free, network-free, and reproducible.
  Date: 2026-05-01

- Decision: The final roadmap freezes at Phase 24.
  Reason: The project should converge into an eval infrastructure portfolio artifact instead of growing into a dashboard or general agent product.
  Date: 2026-05-02

## Known Limitations

- Limitation: Replay execution is limited to the current fixture-backed tools.
  Impact: The benchmark suite can replay the current finance, data, coding, optimization, file-workflow, and citation tasks, but new tool families still need executable adapters before traces can be re-executed end to end.
  Planned fix: Add replay support alongside each new executable adapter.

- Limitation: Docker backend execution is optional and not part of default CI.
  Impact: Default validation proves command policy, injected Docker command behavior, and workspace compatibility, while actual container execution still depends on a local Docker daemon.
  Planned fix: Keep Docker as an optional smoke path and avoid presenting it as a security boundary.

- Limitation: Default agent baselines are deterministic fixture-compatible simulations.
  Impact: They exercise the harness, validators, traces, and metrics, while the recorded model fixture demonstrates model-style failures without being a live provider benchmark.
  Planned fix: Use the Phase 20 credentials-gated live workflow manually when credentials are intentionally supplied, then keep recorded transcripts for reproducible replay.

- Limitation: The recorded model matrix uses controlled behavior profiles rather than live provider transcripts.
  Impact: It demonstrates that the harness can distinguish failure signatures across model-like outputs, but it is not a live-provider benchmark.
  Planned fix: Convert reviewed Phase 20 live runs into recorded fixtures for reproducible replay.

- Limitation: Fixture-backed executor covers only the current default tools.
  Impact: New domains beyond the current finance, data, coding, and optimization fixtures still need executable adapters before they can be evaluated end to end.
  Planned fix: Add adapters as new task suites are introduced.

- Limitation: Benchmark tasks are synthetic and fixture-backed.
  Impact: They support deterministic benchmark claims for harness behavior, but not live-provider or real-world production benchmark claims.
  Planned fix: Keep claims precise; treat Phase 20 live outputs as manual evidence until they are converted into reviewed recorded fixtures.

- Limitation: The report's final-answer-only score is a deterministic proxy.
  Impact: It demonstrates silent-failure and root-cause reporting but does not semantically judge answer quality.
  Planned fix: Keep deterministic checks first; add optional controlled final-answer scoring only after executable tool adapters and regression thresholds are stable.

- Limitation: Regression comparison in the report is descriptive.
  Impact: Pass/fail enforcement lives in the gate evaluator and CLI, while the report itself does not yet embed gate outcomes.
  Planned fix: Later phases can surface gate outcomes in report artifacts and wire the strict smoke command into project-bound CI scripts.

- Limitation: Gate presets are JSON-backed.
  Impact: They are versioned and dependency-free, but they do not share the `.yaml` format used by the earlier config stubs.
  Planned fix: Keep JSON until there is a real need to migrate gate presets into the Phase 22 config loader format.

- Limitation: Gate CLI trace discovery replays all traces listed in `summary.json`.
  Impact: It cannot yet filter by task, domain, or baseline for narrower gate runs.
  Planned fix: Add trace discovery filters when broader suites make that useful.

- Limitation: The Phase 22 YAML loader is project-specific.
  Impact: Tool, task-suite, validator, and eval-run configs are now runtime-validated, but the parser intentionally supports only the current controlled config subset and is not a general YAML parser.
  Planned fix: Keep configs simple and dependency-free unless future config shapes justify a parser dependency.

- Limitation: Root-cause categories are deterministic mappings from validator failures and trace metadata.
  Impact: They make reports auditable and reproducible, but they do not claim subjective causal explanation beyond what validators and traces show.
  Planned fix: Keep explanations deterministic and use Phase 24 docs to make the evidence narrative easier to review.

- Limitation: The benchmark suite reuses a compact set of local fixture files.
  Impact: It broadens failure-taxonomy and replay coverage without adding external data complexity, but it is not a replacement for live or third-party benchmark datasets.
  Planned fix: Keep claims precise; optional live runs remain credentials-gated and outside default validation.

## Failure Modes to Watch

- Building an agent instead of an eval harness
- Using only final-answer scoring
- Using LLM-as-judge before deterministic validators
- Allowing tasks without hidden expected state
- Logging traces without making them replayable
- Making finance tasks too close to the A1 evidence-engine project
- Building dashboard code before validators work
- Comparing models without controlling task, tool, prompt, and fixture versions

## Next Steps

1. Maintenance only: fix bugs, refresh recorded evidence, and polish documentation when needed.
2. Keep sandbox claims limited to evaluation isolation, not a security product.
3. Keep recorded model matrix claims offline and fixture-backed unless a live run is explicitly executed and documented.
4. Do not add new roadmap phases, dashboard product work, generic agent runtime features, or unrelated finance ingestion work.
