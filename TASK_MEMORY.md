# Task Memory: Sandboxed Tool-Use Agent Evaluation Harness

## Latest Status

Current branch:
`codex/ashare-radar-phase1a`

Latest commit:
Phase 1 is being committed in the current run. Use `git log -1 -- sandboxed-agent-eval-harness` for the exact commit after this run finishes.

Current phase:
Phase 2: Core schemas

Main blocker:
No implementation blocker. Phase 1 package skeleton is in place.

Next recommended action:
Define the Phase 2 core schemas: `TaskSpec`, `ToolSpec`, `TraceEvent`, `ValidatorResult`, and `RunResult`, with serialization and validation tests.

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

- Limitation: Core schemas are not implemented.
  Impact: Tool registry, trace logging, validators, and task definitions do not have typed contracts yet.
  Planned fix: Phase 2 creates schema dataclasses or equivalent typed models with serialization tests.

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

1. Define Phase 2 schema module boundaries.
2. Add failing schema serialization and validation tests.
3. Implement minimal typed schemas.
4. Add invalid-input tests for schema validation.
5. Update validation commands once schema-specific tests exist.
