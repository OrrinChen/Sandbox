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

The repository has completed Phase 6 deterministic validator work. It now has workflow documents, Python package metadata, config stubs, a `src/` package layout, skeletal tests, typed schema contracts, a `ToolSpec`-backed registry, a minimal local sandbox, JSONL trace logging, minimal trace replay from fixture state, and first deterministic validators.

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

For the current package skeleton:

```bash
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
import sandboxed_agent_eval_harness
print(sandboxed_agent_eval_harness.__name__)
PY
git diff --check -- .
```

For later phases, follow `VALIDATION.md`.

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

The registry handles lookup, unknown-tool rejection, duplicate-tool rejection, input validation before execution, output validation after execution, and metadata access for permissions, side effects, state mutation, and failure modes. It does not execute tools yet.

## Sandbox

The first sandbox utilities live in `sandboxed_agent_eval_harness.sandbox`.

They provide:

- `FileSystemSandbox`
- `StateSnapshot`
- `StateDiff`
- `run_python_subprocess()`
- `SandboxPathError`
- `SandboxTimeoutError`

The filesystem sandbox constrains path operations to a task workspace, supports an optional read allowlist, resets to deterministic initial files, and captures added/modified/deleted file diffs. The subprocess helper runs Python snippets in the workspace with a timeout. It is a local test harness primitive, not a production isolation boundary.

## Trace Logging And Replay

The first trace utilities live in `sandboxed_agent_eval_harness.tracing`.

They provide:

- `TraceLogger`
- `TraceReplay`
- `TraceReplayError`
- `load_trace_events()`

The logger appends ordered JSONL events for user messages, agent messages, tool calls, tool results, state diffs, validator results, timeout events, and error events. Each event carries pinned run metadata where available, including task, tool, prompt, model, and fixture versions.

The replay helper loads persisted JSONL traces, rejects malformed or non-contiguous event sequences, preserves original event order, and carries fixture state needed to inspect a failed run. It reconstructs trace context for debugging; it does not execute tools yet.

## Deterministic Validators

The first validator utilities live in `sandboxed_agent_eval_harness.validators`.

They provide:

- `validate_schema()`
- `validate_tool_sequence()`
- `validate_tool_arguments()`
- `validate_state()`
- `validate_numeric()`
- `validate_citations()`
- `default_validator_names()`

Each validator returns the existing `ValidatorResult` schema. The validators catch malformed schema payloads, wrong or missing tool sequences, invalid tool-call arguments, state-diff mismatches, numeric mismatches with explicit tolerance, and unsupported or missing citations. They are deterministic and fixture-friendly; they do not call live APIs or LLM judges.
