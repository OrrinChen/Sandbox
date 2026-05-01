# VALIDATION.md

This file defines the commands an autonomous Codex run should use to verify work before reporting success.

## Current Documentation-Only Validation

Use these commands while the repository has no Python package yet:

```bash
for f in README.md AGENTS.md ROADMAP.md TASK_MEMORY.md VALIDATION.md RUNBOOK.md; do test -s "$f" || exit 1; done
git diff --check -- .
```

Expected result:
- Every required workflow file exists and is non-empty.
- `git diff --check -- .` exits with status 0.

## Phase 1 Validation

Run after `pyproject.toml`, package directories, and skeletal tests exist:

```bash
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
import sandboxed_agent_eval_harness
print(sandboxed_agent_eval_harness.__name__)
PY
git diff --check -- .
```

Expected result:
- Tests pass.
- Package import succeeds.
- Whitespace check passes.

## Core Schema Validation

Run after Phase 2 schema work:

```bash
python3 -m pytest tests/test_tool_schemas.py tests/test_trace_schema.py -v
git diff --check -- .
```

Expected result:
- Valid schema examples pass.
- Invalid schema examples fail deterministically.
- Trace records serialize to JSONL-compatible objects.

## Tool Registry Validation

Run after Phase 3 tool registry work:

```bash
python3 -m pytest tests/test_tool_registry.py -v
PYTHONPATH=src python3 - <<'PY'
from sandboxed_agent_eval_harness.tools import default_tool_registry
registry = default_tool_registry()
print(" ".join(registry.names()))
PY
git diff --check -- .
```

Expected result:
- Tool lookup works by name.
- Unknown tools are rejected.
- Duplicate tool names are rejected.
- Inputs and outputs validate through `ToolSpec`.
- Default finance and data-analysis tool declarations are available.

## Runtime and Sandbox Validation

Run after sandbox work:

```bash
python3 -m pytest tests/test_sandbox_limits.py -v
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

Expected result:
- Timeouts are enforced.
- Filesystem writes are constrained to task workspace.
- State reset works between runs.
- State diff capture works.

## Trace Logging And Replay Validation

Run after trace logging and replay work:

```bash
python3 -m pytest tests/test_trace_replay.py -v
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

Expected result:
- Ordered JSONL trace events are persisted.
- Tool calls and tool results preserve payloads and order.
- State diffs, validator results, timeout events, and error events are representable.
- Replay rejects malformed or non-contiguous traces.
- Replay carries pinned task, tool, prompt, model, and fixture metadata where available.

## Validator Validation

Run after validator work:

```bash
python3 -m pytest tests/test_validators.py -v
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

Expected result:
- Wrong tool selection is caught.
- Wrong arguments are caught.
- Numeric mismatch is caught.
- Unsupported citation is caught.
- State corruption is caught.

## Task Suite Validation

Run after initial task suite work:

```bash
python3 -m pytest tests/test_task_suites.py -v
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

Expected result:
- Default suite loads from local fixtures.
- The suite has 3 finance tasks and 3 data-analysis tasks.
- Each task has hidden expected state.
- Each task maps to deterministic validators.
- Gold numeric/file outputs and known failure traps are present.

## Evaluation Smoke Test

Run after task suites and evaluation runner exist:

```bash
python3 -m pytest tests/test_eval_runner.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-smoke
git diff --check -- .
```

Expected result:
- Same task can run repeated trials.
- Smoke suite writes JSONL trace artifacts.
- `summary.json` includes task success rate, pass@k, per-validator metrics, and failure taxonomy.
- CLI smoke prints run count, task success rate, and pass@k.

## Report And Regression View Validation

Run after report generation exists:

```bash
python3 -m pytest tests/test_report.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --trials 2 \
  --output-dir /tmp/sandboxed-agent-eval-report-current
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 2 \
  --output-dir /tmp/sandboxed-agent-eval-report-previous
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.report \
  --summary /tmp/sandboxed-agent-eval-report-current/summary.json \
  --previous-summary /tmp/sandboxed-agent-eval-report-previous/summary.json \
  --output-dir /tmp/sandboxed-agent-eval-report
git diff --check -- .
```

Expected result:
- Report JSON and Markdown artifacts are written.
- Domain success, final-answer-vs-validator comparison, failure distribution, pass@k curve, cost/latency, and worst trace sections are present.
- Previous-run comparison shows metric deltas and version metadata.
- Worst trace entries point to replayable JSONL traces.

## Before Commit

Always run:

```bash
git status --short --untracked-files=all -- .
git diff --check -- .
```

Also run the phase-specific commands above for the files touched.
