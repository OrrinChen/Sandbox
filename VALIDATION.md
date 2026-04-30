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

## Evaluation Smoke Test

Run after task suites and evaluation runner exist:

```bash
python3 -m pytest tests/test_eval_runner.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke
git diff --check -- .
```

Expected result:
- Smoke suite completes.
- Trace artifact is written.
- Validator summary is written.
- Failure taxonomy is present when failures occur.

## Before Commit

Always run:

```bash
git status --short
git diff --check -- .
```

Also run the phase-specific commands above for the files touched.
