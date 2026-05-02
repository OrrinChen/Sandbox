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
- [x] Phase 7: Initial Task Suites
- [x] Phase 8: Agent Baselines and Evaluation Runner
- [x] Phase 9: Report and Regression View
- [x] Phase 10: Executable Fixture Tool Adapters
- [x] Phase 11: Trace Replay Execution
- [x] Phase 12: Regression Threshold Gates
- [x] Phase 13: Config-backed Gate Presets and Trace Discovery
- [x] Phase 14: Portfolio-grade Deterministic Suite Expansion
- [x] Phase 15: Real Model Adapter and Silent Failure Study
- [x] Phase 16: Reproducibility and CI
- [x] Phase 17: Benchmark-Scale Deterministic Suite Expansion
- [x] Phase 18: Failure Taxonomy v2 and Root-Cause Report
- [x] Phase 19: Recorded Model Matrix
- [x] Phase 20: Credentials-Gated Live Provider Workflow
- [x] Phase 21: Sandbox Backend Hardening

Current phase:
- [ ] Phase 22: Config Loader and Suite Registry Cleanup

Deferred:
- Broader optimization and coding suites beyond initial deterministic slices
- Live multi-provider model experiments with credentials supplied outside default tests
- Cloud execution
- Paid APIs and live financial data
- LLM-as-judge scoring
- Production deployment

## Qiushi Roadmap Discipline

This roadmap is written from current facts, not aspiration. Do not mark a capability complete until the command, artifact, or test named in the acceptance criteria exists and has passed locally.

Main line:
This is eval infrastructure, not an agent product. The core value is exposing silent tool-use failures that final-answer-only grading misses: wrong tool choice, wrong arguments, wrong state mutation, wrong numeric values, unsupported citations, violated constraints, non-replayable traces, timeouts, and cost regressions.

Current facts:
- Phases 0-21 are complete.
- The default deterministic suite has 8 fixture-backed tasks across finance, data analysis, coding, and optimization.
- The benchmark deterministic suite has 64 fixture-backed tasks across finance, data analysis, coding, optimization, file workflow, and citation domains.
- The recorded model study currently shows final-answer pass rate 1.000 versus validator pass rate 0.500, with 4 silent failures caught.
- The recorded benchmark model study shows final-answer pass rate 1.000 versus validator pass rate 0.500, with 32 silent failures caught.
- The recorded model matrix has 5 offline profiles over the 64-task benchmark suite, 320 total runs, and 5 distinct failure signatures.
- The matrix key finding is that final-answer-only grading overestimated validated correctness by 56.2 percentage points and deterministic validators caught 180 silent failures.
- The live provider workflow is credentials-gated, fails closed without `--live`, skips cleanly without credentials, and can convert live outputs into recorded fixture candidates.
- Oracle benchmark replay currently covers 64 traces with 0 divergences.
- Reports now emit normalized root-cause breakdowns, validator gap, silent failure rate, answer overclaim rate, top replayable failure traces, and an executive summary sentence.
- `make ci` exists and locally runs pytest, oracle smoke, strict gate, recorded model study, and report generation.
- The sandbox has a default workspace backend plus an optional Docker command envelope with network disabled, resource limits, read-only fixture mount, and deterministic artifact export. It is evaluation isolation, not a security product.

Principal contradiction:
The harness architecture now has benchmark-scale fixture coverage, root-cause reporting, and model-profile comparison, but it still needs recruiter-readable portfolio evidence before it can be treated as an S-level AI infra project.

Required path to portfolio readiness:
```text
Phase 23 -> Phase 24
```

Optional hardening path:
```text
Phase 20 -> Phase 21 -> Phase 22
```

Full path if time allows:
```text
Phase 19 -> Phase 20 -> Phase 21 -> Phase 22 -> Phase 23 -> Phase 24
```

Hard stop:
Stop feature expansion after Phase 24. After that, only maintain, fix bugs, refresh recorded evidence, and polish documentation. Do not add a web app, dashboard product, generic agent runtime, or unrelated finance ingestion work.

Truthfulness rules:
- Benchmark-scale claims must be described as fixture-backed deterministic results, not live-provider benchmark results.
- Root-cause reporting claims must remain tied to deterministic validator and trace data, not LLM-as-judge explanations.
- Model matrix comparison is recorded and offline; do not describe it as a live-provider benchmark.
- Do not claim live provider results unless a run used explicit credentials and `--live`; default validation still does not run live providers.
- Do not call sandboxing secure; describe Phase 21 as optional evaluation isolation, not a security product.
- Do not claim runtime configs are authoritative until Phase 22 passes.
- Do not present this as portfolio-final until Phase 23 and Phase 24 pass.

Minimum resume-ready path:
If time is constrained, complete Phases 23 and 24 after Phase 19. That is sufficient for a strong big-tech AI infra / LLM eval portfolio project.

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
- [x] Constraint validator
- [x] Unit test validator
- [x] Policy validator
- [x] Cost and latency validator

Acceptance criteria:
- A plausible final answer with wrong tool use fails
- A plausible final answer with wrong arguments fails
- A plausible final answer with unsupported citation fails
- State corruption is detected even when final text looks correct

## Phase 7: Initial Task Suites

Goal:
Create small fixture-backed finance and data analysis suites before expanding domains.

Initial scope:
- [x] 3-5 finance tasks
- [x] 3-5 data analysis tasks
- [x] Hidden expected state for each task
- [x] Gold numeric/file outputs where relevant
- [x] Known failure traps for each task

Acceptance criteria:
- Tasks are deterministic
- Tasks do not require live network access
- Each task maps to at least one validator
- Final-answer-only scoring can differ from validator scoring

## Phase 8: Agent Baselines and Evaluation Runner

Goal:
Compare tool-use reliability across simple agent architectures.

Baselines:
- [x] Single-shot tool-calling agent
- [x] ReAct-style agent
- [x] Planner-executor agent
- [x] Oracle-tool-selection baseline

Metrics:
- [x] Task success rate
- [x] pass@k
- [x] Tool selection accuracy
- [x] Argument correctness
- [x] State correctness
- [x] Numeric correctness
- [x] Citation correctness
- [x] Average turns
- [x] Latency
- [x] Cost
- [x] Timeout rate

Acceptance criteria:
- Same task can run repeated trials
- pass@k consistency is measured
- Per-validator metrics are reported
- Failure taxonomy is aggregated

## Phase 9: Report and Regression View

Goal:
Produce a portfolio-ready reliability report before building a full dashboard.

Tasks:
- [x] Generate success rate by domain
- [x] Compare final-answer pass vs validator pass
- [x] Generate failure type distribution
- [x] Generate pass@k curve
- [x] Generate cost and latency summary
- [x] List worst traces
- [x] Compare against a previous run artifact

Acceptance criteria:
- Report explains where agents fail
- Regressions can be seen across task/tool/prompt/model versions
- Failed traces can be opened and replayed

## Phase 10: Executable Fixture Tool Adapters

Goal:
Move the runner from planned fixture-shaped tool results to executable local fixture-backed tools.

Tasks:
- [x] Implement fixture-backed tool executor
- [x] Execute finance statement fixtures
- [x] Execute transcript search fixtures
- [x] Execute CSV read fixtures
- [x] Execute CSV grouped metric outputs inside a sandbox workspace
- [x] Capture state diffs from sandbox snapshots
- [x] Write actual tool execution results into traces
- [x] Keep registry input/output validation in the execution path
- [x] Keep smoke runner deterministic and network-free

Acceptance criteria:
- Tool calls are executed through local adapters rather than trusting baseline-provided results
- CSV output files are written inside a per-run sandbox workspace
- State validator uses actual workspace diffs
- Trace tool results show executed fixture outputs
- Existing evaluation and report metrics still pass

## Phase 11: Trace Replay Execution

Goal:
Make persisted traces reproducible by re-executing recorded tool calls and detecting divergence.

Tasks:
- [x] Load persisted trace metadata and identify the task
- [x] Re-execute recorded tool calls with fixture-backed adapters
- [x] Compare recorded tool results with replayed tool results
- [x] Recompute sandbox state diffs
- [x] Compare recorded state diff with replayed state diff
- [x] Report deterministic divergence records
- [x] Serialize replay execution results
- [x] Keep replay execution deterministic and network-free

Acceptance criteria:
- A passing trace can be re-executed without divergence
- Tampered recorded tool results are detected
- Tampered recorded state diffs are detected
- Replay execution writes outputs in an isolated workspace
- Existing trace, evaluation, and report tests still pass

## Phase 12: Regression Threshold Gates

Goal:
Fail evaluation runs deterministically when key reliability metrics or replay reproducibility regress beyond configured thresholds.

Why now:
The harness can execute tasks, validate results, generate reports, and replay traces. The next useful step is turning descriptive regression data into explicit pass/fail gates suitable for local validation and future CI.

Tasks:
- [x] Define a typed gate result and gate report surface
- [x] Enforce minimum task success rate
- [x] Enforce minimum pass@k
- [x] Compare task success and pass@k drops against a previous summary
- [x] Cap configured failure taxonomy counts
- [x] Cap replay divergence counts from replay execution results
- [x] Add a CLI that exits non-zero when configured gates fail
- [x] Add replay divergence summaries to reports

Acceptance criteria:
- Gate tests cover passing thresholds
- Gate tests cover failing metric and failure-taxonomy thresholds
- CLI tests cover non-zero exits on configured regressions
- Report tests cover replay divergence summary output
- Existing evaluation, replay, and report tests still pass

Do not:
- Depend on live APIs or paid services
- Use LLM-as-judge for regression gates
- Treat missing replay data as a passing replay-divergence gate when that gate is configured

## Phase 13: Config-backed Gate Presets and Trace Discovery

Goal:
Make regression gates usable as a stable local or CI command without hand-writing temporary threshold files or trace path lists.

Why now:
Phase 12 introduced gate evaluation and a CLI. The next bottleneck is operational: the thresholds should be versioned in the project, and replay gates should discover traces from the evaluation summary artifact.

Tasks:
- [x] Add a project-level regression gate preset config
- [x] Load named threshold presets from config
- [x] Keep direct `--thresholds` JSON path support
- [x] Discover unique trace paths from `summary.json`
- [x] Let gate CLI replay discovered traces
- [x] Include preset metadata in gate reports
- [x] Add tests for preset loading, trace discovery, and preset CLI smoke

Acceptance criteria:
- Preset loading is covered by tests
- Trace discovery is deterministic and de-duplicates paths
- Gate CLI can run from `summary.json` plus `--threshold-preset strict_smoke`
- Gate CLI replays discovered traces and enforces `max_replay_divergences`
- Existing regression gate tests still pass
- Full pytest still passes

Do not:
- Add a YAML parser or heavy dependency just to read gate presets
- Add repository-root CI workflow files while the project boundary is `sandboxed-agent-eval-harness/`
- Depend on live APIs or external services

## Phase 14: Portfolio-grade Deterministic Suite Expansion

Goal:
Expand the MVP beyond finance/data examples into deterministic coding and optimization tasks with executable tools, replayable traces, and stricter validators.

Why now:
The project is strong as an eval harness MVP, but a resume-grade AI infra project benefits from showing multiple task domains and validators that catch failures beyond numbers and citations.

Tasks:
- [x] Add a sandboxed coding fixture task
- [x] Add a small optimization fixture task
- [x] Add executable `code.patch` and `python.unit_tests` tools
- [x] Add executable `optimization.solve_newsvendor` tool
- [x] Add constraint, unit-test, policy, and cost/latency validators
- [x] Wire new validators into the evaluation runner
- [x] Update baseline planning for coding and optimization tasks
- [x] Keep trace replay execution deterministic for new tools
- [x] Update configs and docs for the expanded suite

Acceptance criteria:
- Default suite covers finance, data analysis, coding, and optimization
- New coding and optimization tasks use local fixtures only
- New tools validate inputs and outputs through `ToolSpec`
- Oracle baseline passes the expanded suite
- Non-oracle baselines still produce deterministic failure taxonomy
- Trace replay can re-execute new task traces without divergence
- Full pytest passes

Do not:
- Add live APIs, paid services, or external benchmark downloads
- Add heavy dependencies
- Treat a written final answer as enough when state, unit-test, or constraint validators fail

## Phase 15: Real Model Adapter and Silent Failure Study

Goal:
Add model adapter interfaces and a recorded model-output study that compares final-answer-only scoring against deterministic validation.

Why now:
The harness is now structurally complete, but resume-grade evidence needs model-style failure data instead of only deterministic baseline simulations.

Tasks:
- [x] Add a recorded model-output adapter
- [x] Add an optional OpenAI Responses API adapter with injectable transport
- [x] Add `ModelAdapterAgent` so adapter outputs can run through the existing evaluation runner
- [x] Preserve final-answer-only pass as a separate run metric
- [x] Add recorded model output fixtures with intentional silent failures
- [x] Add a silent failure study CLI
- [x] Generate model comparison output with final-answer pass rate, validator pass rate, overstatement rate, failure taxonomy, cost, and latency
- [x] Keep default tests fixture-safe and network-free
- [x] Update configs and docs

Acceptance criteria:
- Recorded model adapter can replay fixture-safe model plans
- OpenAI adapter request construction is testable without network access
- The study command writes `summary.json`, report artifacts, and `silent_failure_study.json`
- The recorded study demonstrates final-answer-only pass rate above validator pass rate
- Full pytest passes
- `git diff --check -- .` passes

Do not:
- Require API keys or live network calls for default tests
- Commit secrets or provider credentials
- Claim broad benchmark results from one recorded fixture study
- Use LLM-as-judge in place of deterministic validators

## Phase 16: Reproducibility and CI

Goal:
Make the project reproducible through one local command and one GitHub Actions workflow.

Why now:
The harness can run deterministic oracle smoke, strict gates, recorded model study, and report generation. The next useful step is making those checks hard to skip.

Tasks:
- [x] Add `make test`
- [x] Add `make smoke`
- [x] Add `make gate`
- [x] Add `make model-study`
- [x] Add `make report`
- [x] Add `make ci`
- [x] Add GitHub Actions CI
- [x] Set workflow `working-directory: sandboxed-agent-eval-harness`
- [x] Upload generated artifacts from CI
- [x] Keep default CI credential-free and network-free except for package installation/actions infrastructure

Acceptance criteria:
- `make ci` runs full pytest, oracle smoke, strict regression gate, recorded model study, and report generation
- GitHub Actions uses the project subdirectory as working directory
- GitHub Actions does not reference live API credentials or `--live`
- Generated `artifacts/` remain ignored by git
- Full pytest passes
- `git diff --check -- .` passes

Do not:
- Add live API credentials
- Add network-dependent tests
- Expand task suites
- Build dashboard features

## Phase 17: Benchmark-Scale Deterministic Suite Expansion

Priority:
Required for portfolio readiness.

Goal:
Expand from 8 deterministic tasks toward a structured 48-64 task benchmark without making broad live benchmark claims.

Tasks:
- [x] Add `fixtures/tasks/benchmark_suite.json`
- [x] Add `--suite benchmark`
- [x] Cover finance/evidence, data analysis, coding, optimization/OR, state mutation/file workflows, and citation/evidence traps
- [x] Map every task to explicit failure taxonomy traps
- [x] Keep oracle benchmark pass rate at 1.000
- [x] Keep replay divergence at 0 for oracle benchmark traces
- [x] Update recorded model fixtures to produce non-trivial silent failures on the benchmark suite

Acceptance criteria:
- Benchmark suite is deterministic and fixture-backed
- Default tests remain network-free
- Oracle benchmark pass rate is 1.000
- Replay divergence is 0
- Recorded model benchmark produces non-trivial silent failures

Commit target:
`feat: expand deterministic benchmark suite`

## Phase 18: Failure Taxonomy v2 and Root-Cause Report

Priority:
Required for portfolio readiness.

Goal:
Move reports from failure counts to root-cause explanations.

Tasks:
- [x] Add normalized root-cause categories
- [x] Add silent failure rate, answer overclaim rate, and validator gap
- [x] Add failure breakdowns by domain, tool, model, and validator
- [x] Add top replayable failure traces
- [x] Emit an executive summary sentence with final-answer overstatement

Acceptance criteria:
- `silent_failure_study.json` contains root-cause breakdowns
- `report.md` has an executive summary
- `report.json` exposes machine-readable root-cause fields
- Tests cover each failure taxonomy category

Commit target:
`feat: add root-cause failure taxonomy reports`

## Phase 19: Recorded Model Matrix

Priority:
Required for portfolio readiness.

Goal:
Compare several recorded model behavior profiles without live network calls.

Tasks:
- [x] Add at least four recorded model profiles
- [x] Generate `model_matrix_summary.json`
- [x] Generate `model_comparison_report.md`
- [x] Generate `silent_failure_by_model.csv`
- [x] Sort and compare models by failure signature

Acceptance criteria:
- At least four recorded model profiles run on the benchmark suite
- Each profile has a distinct failure signature
- No network calls are required

Commit target:
`feat: add recorded model matrix study`

## Phase 20: Credentials-Gated Live Provider Workflow

Priority:
Optional hardening.

Goal:
Add manual live provider experiments while keeping default CI deterministic and offline.

Tasks:
- [x] Add `--model-provider openai`
- [x] Add generic HTTP or second-provider adapter
- [x] Add `--live`, `--max-cost-usd`, `--max-tasks`, and `--record-output`
- [x] Fail closed without `--live`
- [x] Skip live tests without credentials
- [x] Convert live outputs into recorded fixture candidates

Acceptance criteria:
- Live smoke can run manually with credentials
- Default pytest does not require keys
- CI does not run live workflows
- Recorded fixture conversion is reproducible

Commit target:
`feat: add credentials-gated live model workflow`

## Phase 21: Sandbox Backend Hardening

Priority:
Optional hardening.

Goal:
Add optional container isolation while keeping the project honest about sandbox limits.

Tasks:
- [x] Add `LocalWorkspaceBackend`
- [x] Add optional `DockerSandboxBackend`
- [x] Disable network in Docker backend
- [x] Mount fixtures read-only
- [x] Export workspace artifacts deterministically
- [x] Add `--sandbox-backend workspace|docker`

Acceptance criteria:
- Workspace backend remains compatible
- Docker backend can run coding and data tasks
- Timeout and memory-limit behavior has deterministic tests
- Docs do not overclaim security

Commit target:
`feat: add optional container sandbox backend`

## Phase 22: Config Loader and Suite Registry Cleanup

Priority:
Optional hardening.

Goal:
Turn declarative config mirrors into runtime-consumed and validated configs.

Tasks:
- [ ] Add `load_tools_config()`
- [ ] Add `load_validators_config()`
- [ ] Add `load_task_suites_config()`
- [ ] Add `load_eval_runs_config()`
- [ ] Add `validate_project_config`
- [ ] Add `make validate-config`

Acceptance criteria:
- Bad config fails deterministically
- Runtime suite/tool/validator surfaces match README and configs
- Config validation is part of local reproducibility checks

Commit target:
`feat: add runtime config loading and validation`

## Phase 23: Public Portfolio Report

Priority:
Required for portfolio readiness.

Goal:
Generate a static report suitable for recruiters and interviewers.

Tasks:
- [ ] Generate `reports/portfolio_report.md`
- [ ] Generate `reports/portfolio_report.json`
- [ ] Generate model matrix, failure taxonomy, and domain breakdown tables
- [ ] Generate 2-3 replayable failure case studies
- [ ] Keep report generation key-free

Acceptance criteria:
- One command generates the portfolio report
- Report includes problem, system, evidence, benchmark, failure taxonomy, reproducibility, and limitations
- Case studies point to replayable traces

Commit target:
`feat: generate portfolio evidence report`

## Phase 24: README, Resume, and Interview Polish Freeze

Priority:
Required final freeze.

Goal:
Freeze the project into a portfolio-ready artifact and stop feature expansion.

Tasks:
- [ ] Rewrite README for 3-minute reviewer comprehension
- [ ] Add `docs/interview_notes.md`
- [ ] Add `docs/architecture.md`
- [ ] Add `docs/limitations.md`
- [ ] Add `docs/failure_case_studies.md`
- [ ] Add final resume bullet with numbers
- [ ] Mark roadmap frozen after Phase 24

Acceptance criteria:
- README has Problem, Architecture, Quickstart, Key Result, Reproducibility, and Limitations
- `make ci` passes
- Portfolio report is present and reproducible
- Claims avoid security or benchmark overstatement

Commit target:
`docs: polish portfolio narrative and freeze roadmap`

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

Initial deterministic slice implemented in Phase 14. Broader optimization families remain deferred.

Examples:
- Solve a newsvendor order quantity problem
- Run a small routing heuristic
- Verify all stops are visited
- Diagnose infeasible portfolio constraints

### Software / Terminal Tasks

Initial deterministic coding slice implemented in Phase 14. Broader terminal/software tasks remain deferred.

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
    test_report.py
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
