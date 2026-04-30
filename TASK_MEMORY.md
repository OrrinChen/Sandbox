# Task Memory: Sandboxed Tool-Use Agent Evaluation Harness

## Latest Status

Current branch:
`codex/ashare-radar-phase1a`

Latest commit:
Phase 5 trace logging and replay. Use `git log -1 -- sandboxed-agent-eval-harness` for the exact commit hash.

Current phase:
Phase 6: Deterministic Validators

Main blocker:
No implementation blocker. Phase 5 trace logging and replay are in place.

Next recommended action:
Implement Phase 6 deterministic validators: schema, tool sequence, argument, state, numeric, and citation validators.

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

- Limitation: Trace replay does not execute tools yet.
  Impact: Failed runs can be opened and inspected from ordered trace events, but not re-run end to end.
  Planned fix: Later evaluation-runner work wires trace capture and replay into executable task runs.

- Limitation: Deterministic validators are not implemented.
  Impact: The harness cannot yet reject plausible final answers with wrong tool use, arguments, numeric values, citations, or state mutations.
  Planned fix: Phase 6 creates the first schema, tool sequence, argument, state, numeric, and citation validators.

- Limitation: Config files are stubs.
  Impact: They document intended configuration surfaces but are not consumed by runtime code yet, except `configs/tools.yaml` mirroring default tool declarations.
  Planned fix: Later phases load and validate config files once runtime contracts stabilize.

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

1. Define Phase 6 validator module boundaries.
2. Add failing tests for schema, tool sequence, argument, state, numeric, and citation validators.
3. Implement deterministic validator result generation.
4. Connect validators to existing `ValidatorResult` schema.
5. Keep validators fixture-backed and independent of live network data.
