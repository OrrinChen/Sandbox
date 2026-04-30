# Sandboxed Tool-Use Agent Evaluation Harness Roadmap

## Current State

Completed:
- [x] Phase 0: Project framing and autonomous workflow scaffold
- [x] Phase 1: Planning and repository skeleton
- [x] Phase 2: Core schemas
- [x] Phase 3: Tool registry
- [x] Phase 4: Sandbox and state tracking
- [x] Phase 5: Trace logging and replay
- [x] Phase 6: Deterministic Validators

Current phase:
- [ ] Phase 7: Initial Task Suites

Deferred:
- Optimization and coding suites beyond initial design
- Cloud execution
- Paid APIs and live financial data
- Full regression dashboard
- LLM-as-judge scoring
- Production deployment

## Phase 1: Planning and Repository Skeleton

Goal:
Create the minimal repository structure needed to start implementation without losing the core project direction.

Why now:
The project currently has planning documents only. The next useful step is a small, testable skeleton that future Codex runs can extend phase by phase.

Tasks:
- [x] Create `pyproject.toml`
- [x] Create `configs/`
- [x] Create `src/sandboxed_agent_eval_harness/`
- [x] Create `tests/`
- [x] Define package entry points or command stubs
- [x] Add initial config stubs for models, tools, sandbox, task suites, validators, and eval runs
- [x] Keep finance and data analysis as the first two task domains

Acceptance criteria:
- `python -m pytest` runs and passes, even if tests are skeletal
- `git diff --check` passes
- Package imports successfully
- README reflects the current state
- TASK_MEMORY records what changed and what was verified
- No unrelated features are added

Do not:
- Build agent baselines before core schemas exist
- Add paid API dependencies
- Depend on live external financial data
- Implement dashboard code before traces and validators work

## Phase 2: Core Schemas

Goal:
Define the typed contracts for tasks, tools, traces, validators, and run results.

Tasks:
- [x] Define `TaskSpec`
- [x] Define `ToolSpec`
- [x] Define `TraceEvent`
- [x] Define `ValidatorResult`
- [x] Define `RunResult`
- [x] Add schema serialization tests
- [x] Add schema validation failure tests

Acceptance criteria:
- Each schema has explicit required fields
- Invalid tool arguments can be rejected deterministically
- Trace events can be serialized to JSONL-compatible records
- Tests cover valid and invalid examples

## Phase 3: Tool Registry

Goal:
Register typed tools with permissions, side-effect declarations, and input/output validation.

Tasks:
- [x] Implement registry lookup by tool name
- [x] Validate tool inputs before execution
- [x] Validate tool outputs after execution
- [x] Track declared side effects and permissions
- [x] Add first fixture-backed finance tools
- [x] Add first local CSV/data tools

Acceptance criteria:
- Unknown tools are rejected
- Invalid arguments are rejected before execution
- Tool side effects are declared in metadata
- Registry tests cover success and failure paths

## Phase 4: Sandbox and State Tracking

Goal:
Execute tools in controlled local sandboxes and track state mutations.

Tasks:
- [x] Implement filesystem sandbox
- [x] Implement Python execution sandbox or safe subprocess wrapper
- [x] Add timeout handling
- [x] Add file access allowlist
- [x] Add state reset between runs
- [x] Add state diff capture

Acceptance criteria:
- Runs cannot write outside the task workspace
- Timeouts terminate the task
- Each run starts from a clean initial state
- State diffs can be attached to traces

## Phase 5: Trace Logging and Replay

Goal:
Make every failure reproducible enough to debug.

Tasks:
- [x] Log user messages
- [x] Log agent messages
- [x] Log tool calls
- [x] Log tool results
- [x] Log state diffs
- [x] Log validator results
- [x] Persist traces as JSONL or structured JSON
- [x] Implement minimal replay from trace and fixture state

Acceptance criteria:
- A failed run can be opened from a trace file
- Tool calls and results are preserved in order
- Replay uses pinned task, tool, prompt, model, and fixture versions where available

## Phase 6: Deterministic Validators

Goal:
Catch silent failures that final-answer scoring misses.

Initial validators:
- [x] Schema validator
- [x] Tool sequence validator
- [x] Argument validator
- [x] State validator
- [x] Numeric validator
- [x] Citation validator

Expansion validators:
- [ ] Constraint validator
- [ ] Unit test validator
- [ ] Policy validator
- [ ] Cost and latency validator

Acceptance criteria:
- A plausible final answer with wrong tool use fails
- A plausible final answer with wrong arguments fails
- A plausible final answer with unsupported citation fails
- State corruption is detected even when final text looks correct

## Phase 7: Initial Task Suites

Goal:
Create small fixture-backed finance and data analysis suites before expanding domains.

Initial scope:
- [ ] 3-5 finance tasks
- [ ] 3-5 data analysis tasks
- [ ] Hidden expected state for each task
- [ ] Gold numeric/file outputs where relevant
- [ ] Known failure traps for each task

Acceptance criteria:
- Tasks are deterministic
- Tasks do not require live network access
- Each task maps to at least one validator
- Final-answer-only scoring can differ from validator scoring

## Phase 8: Agent Baselines and Evaluation Runner

Goal:
Compare tool-use reliability across simple agent architectures.

Baselines:
- [ ] Single-shot tool-calling agent
- [ ] ReAct-style agent
- [ ] Planner-executor agent
- [ ] Oracle-tool-selection baseline

Metrics:
- Task success rate
- pass@k
- Tool selection accuracy
- Argument correctness
- State correctness
- Numeric correctness
- Citation correctness
- Average turns
- Latency
- Cost
- Timeout rate

Acceptance criteria:
- Same task can run repeated trials
- pass@k consistency is measured
- Per-validator metrics are reported
- Failure taxonomy is aggregated

## Phase 9: Report and Regression View

Goal:
Produce a portfolio-ready reliability report before building a full dashboard.

Tasks:
- [ ] Generate success rate by domain
- [ ] Compare final-answer pass vs validator pass
- [ ] Generate failure type distribution
- [ ] Generate pass@k curve
- [ ] Generate cost and latency summary
- [ ] List worst traces
- [ ] Compare against a previous run artifact

Acceptance criteria:
- Report explains where agents fail
- Regressions can be seen across task/tool/prompt/model versions
- Failed traces can be opened and replayed

## Project Positioning

Project name:
Sandboxed Tool-Use Agent Evaluation Harness

Core question:
Can tool-using agents complete real workflows reliably, repeatably, and safely?

This project is not an agent demo. It is evaluation infrastructure for exposing silent tool-use failures, especially cases where the final answer looks successful but tool choice, arguments, state mutation, numbers, citations, constraints, or business rules failed.

Core pipeline:

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

## Scope Boundary

In scope:
- Task schema
- Typed tool registry
- Tool input/output schema validation
- Sandboxed execution
- Resource limits
- Tool-call trace logging
- State diff tracking
- Deterministic validators
- Failure taxonomy
- Trace replay
- pass@k consistency metrics
- Agent baseline comparison
- Regression report/dashboard

Out of scope:
- Large-scale SEC/FMP ingestion
- Multimodal extraction as the main product
- GraphRAG as the main product
- Financial evidence graph as the main product
- Due-diligence memo generation

Those belong to A1: Multimodal Financial Due-Diligence Evidence Engine.

## Domain Suites

### Finance Analyst Tasks

Examples:
- Fetch a fixture-backed financial statement
- Compare YoY revenue
- Retrieve transcript evidence
- Validate fiscal period
- Cite source
- Write short conclusion

Validators:
- Ticker
- Fiscal period
- Numeric value
- Citation support
- Source correctness

### Data Analysis Tasks

Examples:
- Load CSV
- Clean data
- Compute grouped metrics
- Train baseline model
- Export summary table
- Detect schema or leakage issues

Validators:
- Schema
- File output
- Metric correctness
- Unit tests
- Leakage check

### Optimization Tasks

Deferred until the first vertical slice works.

Examples:
- Solve a newsvendor order quantity problem
- Run a small routing heuristic
- Verify all stops are visited
- Diagnose infeasible portfolio constraints

### Software / Terminal Tasks

Deferred until the first vertical slice works.

Examples:
- Fix a small failing function
- Modify a CLI script
- Write tests for a bug
- Generate a patch

## Target Repository Structure

```text
sandboxed-agent-eval-harness/
  README.md
  AGENTS.md
  ROADMAP.md
  TASK_MEMORY.md
  VALIDATION.md
  RUNBOOK.md
  pyproject.toml

  configs/
    models.yaml
    tools.yaml
    sandbox.yaml
    task_suites.yaml
    validators.yaml
    eval_runs.yaml

  src/
    sandboxed_agent_eval_harness/
      agents/
      tools/
      sandbox/
      tasks/
      validators/
      tracing/
      evaluation/
      dashboard/

  tests/
    test_tool_schemas.py
    test_sandbox_limits.py
    test_trace_replay.py
    test_validators.py
    test_eval_runner.py
```

## Killer Experiment

Experiment:
Final-answer accuracy is not enough.

Compare:
- Final answer pass rate
- Tool sequence correctness
- Argument correctness
- State correctness
- Numeric correctness
- Citation correctness
- Constraint feasibility
- pass@k consistency
- Cost
- Latency

Expected conclusion:
Some agents produce plausible final answers while failing tool, state, citation, numeric, or constraint validators. Planner-executor may improve tool sequence correctness while increasing latency and cost. Reflection may fix some numeric errors while increasing tool calls and cost.

## Final Report Outline

```text
1. Problem framing: agent silent failure
2. Task schema and tool registry
3. Sandbox design
4. Validator design
5. Task suites
6. Agent baselines
7. Main results
8. Pass@k and consistency
9. Failure taxonomy
10. Regression dashboard
11. Trace replay examples
12. Reproducibility guide
```

## Resume Bullet

Long version:

> Built a sandboxed tool-use agent evaluation harness for finance, data, optimization, and coding workflows, with typed tool schemas, execution sandboxes, deterministic validators, trace replay, pass@k consistency metrics, and dashboards tracking tool choice, argument correctness, state mutation, citations, constraints, runtime, cost, and failure modes.

Short version:

> Built an agent reliability harness that exposes silent tool-use failures through sandboxed execution, deterministic validators, trace replay, pass@k consistency, and regression dashboards.
