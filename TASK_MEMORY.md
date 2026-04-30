# Task Memory: Sandboxed Tool-Use Agent Evaluation Harness

## Latest Status

Current branch:
`codex/ashare-radar-phase1a`

Latest commit:
Phase 2 is being committed in the current run. Use `git log -1 -- sandboxed-agent-eval-harness` for the exact commit after this run finishes.

Current phase:
Phase 3: Tool registry

Main blocker:
No implementation blocker. Phase 2 core schemas are in place.

Next recommended action:
Implement the Phase 3 tool registry using `ToolSpec` for lookup, input validation, output validation, permissions, and side-effect metadata.

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

## Known Limitations

- Limitation: Tool registry is not implemented.
  Impact: Tool lookup, permission metadata use, and automatic input/output validation are not wired into runtime behavior.
  Planned fix: Phase 3 creates registry lookup and validation paths backed by `ToolSpec`.

- Limitation: Config files are stubs.
  Impact: They document intended configuration surfaces but are not consumed by runtime code yet.
  Planned fix: Later phases load and validate config files after schemas exist.

- Limitation: No task fixtures exist yet.
  Impact: The harness cannot demonstrate silent failure detection.
  Planned fix: Phase 7 creates small finance and data analysis fixture-backed tasks after core runtime pieces exist.

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

1. Define Phase 3 registry module boundaries.
2. Add failing tests for tool registry lookup and unknown-tool rejection.
3. Implement a minimal registry backed by `ToolSpec`.
4. Add input and output validation paths through the registry.
5. Add first fixture-backed tool declarations only after registry behavior is stable.
