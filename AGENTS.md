# AGENTS.md

You are working on this repository as an autonomous coding agent.

## Project Goal

Read `README.md`, `ROADMAP.md`, `TASK_MEMORY.md`, `VALIDATION.md`, and `RUNBOOK.md` before making changes.

Your job is to advance the next incomplete roadmap phase, not to invent unrelated features.

This project is an evaluation harness for tool-using agents. It should expose silent failures where final answers look plausible but tool use, arguments, state mutation, numeric values, citations, constraints, or business rules failed.

## Project Scope

In scope:
- Typed task schemas
- Typed tool registry
- Tool input/output validation
- Sandboxed execution
- Resource limits
- Trace capture
- Trace replay
- State diff tracking
- Deterministic validators
- pass@k consistency
- Agent baseline comparison
- Failure taxonomy
- Regression report/dashboard

Out of scope:
- Building a general agent product
- Large-scale SEC/FMP ingestion
- Multimodal extraction as the main product
- GraphRAG as the main product
- Financial evidence graph as the main product
- Due-diligence memo generation

Those out-of-scope items belong to the separate A1 financial evidence project.

## Hard Constraints

Do not:
- Change project direction without explicit instruction
- Add heavy dependencies unless justified in `TASK_MEMORY.md`
- Rewrite large modules unnecessarily
- Hide failures or report unverified success
- Generate misleading benchmark reports
- Commit secrets, credentials, tokens, paid API keys, or local private data
- Depend on live external APIs for default tests
- Use LLM-as-judge before deterministic validators exist
- Build dashboard features before trace and validator data exist
- Compare agent/model runs without controlling task, tool, prompt, fixture, and version metadata
- Perform destructive actions without explicit approval

## Workflow

Before starting:
1. Run `git status`.
2. Read `README.md`.
3. Read `ROADMAP.md`.
4. Read `TASK_MEMORY.md`.
5. Read `VALIDATION.md`.
6. Read `RUNBOOK.md`.
7. Identify the next incomplete phase.
8. Inspect relevant files before editing.

During work:
1. Make small, testable changes.
2. Keep interfaces modular and typed.
3. Add or update tests for changed behavior.
4. Prefer fixture-backed data over live external data.
5. Update `README.md` when user-facing behavior changes.
6. Update `TASK_MEMORY.md` with what changed, what was verified, and what remains.
7. Keep implementation aligned with the current phase acceptance criteria.

Validation:
1. Run the commands listed in `VALIDATION.md`.
2. Always run relevant unit tests once tests exist.
3. Run smoke tests for touched CLI or UI paths once they exist.
4. Run `git diff --check -- .`.

Commit:
- Commit each completed phase when the user asks for commits or when an autonomous run explicitly includes committing.
- Use clear commit messages:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `test: ...`
- Do not mix unrelated phases in one commit.

## Stopping Rules

Only stop and ask for help if:
- Tests cannot pass after reasonable debugging
- Product direction is ambiguous
- Implementation risks data loss
- Credentials or paid external services are required
- A task would violate hard constraints
- Required local data is unavailable

When stopping, report:
- What was attempted
- What passed
- What failed
- Exact blocker
- Recommended next step

## Repository Boundary

This repository is the standalone `Sandbox` / sandboxed-agent-eval-harness project. The tracked project boundary is the repository root:

```text
.
```

Local sibling project directories may still appear as untracked folders in this working copy. Do not modify or stage them while working on this project.
