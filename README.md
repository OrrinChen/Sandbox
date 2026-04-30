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

The repository has completed Phase 2 core schema work. It now has workflow documents, Python package metadata, initial config stubs, a `src/` package layout, skeletal tests, and typed schema contracts for tasks, tools, traces, validator results, and run results.

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
