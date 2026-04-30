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

## Validator Validation

Run after validator work:

```bash
python3 -m pytest tests/test_validators.py -v
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
