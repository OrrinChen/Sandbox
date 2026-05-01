# Task Memory: Sandboxed Tool-Use Agent Evaluation Harness

## Latest Status

Current branch:
`codex/ashare-radar-phase1a`

Latest commit:
Phase 10 executable fixture-backed tool adapters. Use `git log -1 -- sandboxed-agent-eval-harness` for the exact commit hash.

Current phase:
MVP vertical slice plus executable fixture-backed tools complete; next phase not selected.

Main blocker:
No implementation blocker. Phase 10 executable fixture-backed tool adapters are in place.

Next recommended action:
Select the next phase from deferred expansions. Recommended next target: trace replay execution, using the fixture-backed executor to re-run persisted tool calls against pinned fixture/workspace state.

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
  Planned fix: Recommended next phase uses the fixture-backed executor to re-run persisted trace tool calls.

- Limitation: Agent baselines are deterministic fixture-compatible simulations.
  Impact: They exercise the harness, validators, traces, and metrics, but they are not evidence about real model reliability yet.
  Planned fix: Later phases can add real local or API-backed model adapters once deterministic reporting is stable.

- Limitation: Baselines still plan tool choices and arguments deterministically.
  Impact: Tool execution is real for current fixtures, but agent behavior is still simulated.
  Planned fix: Add real local or API-backed model adapters only after replay execution and regression gates are stable.

- Limitation: Fixture-backed executor covers only the current default tools.
  Impact: New domains still need executable adapters before they can be evaluated end to end.
  Planned fix: Add adapters as new task suites are introduced.

- Limitation: The report's final-answer-only score is a deterministic proxy.
  Impact: It demonstrates silent-failure reporting but does not semantically judge answer quality.
  Planned fix: Keep deterministic checks first; add optional controlled final-answer scoring only after executable tool adapters and regression thresholds are stable.

- Limitation: Regression comparison is descriptive.
  Impact: The report shows deltas but does not yet fail CI or enforce thresholds.
  Planned fix: Add configurable regression gates after the report format stabilizes.

- Limitation: Config files are stubs.
  Impact: They document intended configuration surfaces but are not consumed by runtime code yet, except config mirrors for current tool, task-suite, validator, and eval-run defaults.
  Planned fix: Later phases load and validate config files once runtime contracts stabilize.

- Limitation: Initial task fixtures are intentionally small and synthetic.
  Impact: They are useful for deterministic harness validation but not yet broad enough for benchmark claims.
  Planned fix: Later task-suite expansion adds more domains, edge cases, and regression coverage after the report view exists.

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

1. Select the next phase scope explicitly.
2. Recommended: implement trace replay execution using persisted tool calls and fixture-backed adapters.
3. Add replay verification that detects divergence between recorded and re-executed tool results/state diffs.
4. Add optional regression threshold gates once replay execution is stable.
