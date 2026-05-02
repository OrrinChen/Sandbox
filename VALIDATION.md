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

## Executable Fixture Tool Adapter Validation

Run after fixture-backed tool adapters exist:

```bash
python3 -m pytest tests/test_tool_execution.py -v
python3 -m pytest tests/test_eval_runner.py tests/test_report.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-tool-execution
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

Expected result:
- Finance, transcript, and CSV fixture tools execute without network access.
- CSV grouped metric tools write output files inside the run workspace.
- Trace tool results contain executed fixture outputs, not baseline-provided placeholders.
- State diffs are captured from sandbox snapshots and match expected output files.

## Trace Replay Execution Validation

Run after replay execution exists:

```bash
python3 -m pytest tests/test_trace_replay_execution.py -v
python3 -m pytest tests/test_trace_replay.py tests/test_trace_replay_execution.py tests/test_tool_execution.py tests/test_eval_runner.py tests/test_report.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-replay-execution
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor
trace = Path("/tmp/sandboxed-agent-eval-replay-execution/traces/oracle_tool_selection_agent-data-sales-region-summary-000.jsonl")
result = TraceReplayExecutor().replay(trace, workspace="/tmp/sandboxed-agent-eval-replay-workspace")
print(result.to_dict())
PY
git diff --check -- .
```

Expected result:
- Recorded tool calls are re-executed with fixture-backed adapters.
- Recorded and replayed tool results match for untampered traces.
- Recorded and replayed state diffs match for untampered traces.
- Tampered recorded tool results and state diffs are caught by tests.

## Regression Threshold Gate Validation

Run after regression threshold gates exist:

```bash
python3 -m pytest tests/test_regression_gates.py tests/test_report.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-gates-current
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path

thresholds = {
    "min_task_success_rate": 1.0,
    "min_pass_at_k": 1.0,
    "max_replay_divergences": 0,
}
Path("/tmp/sandboxed-agent-eval-gates-thresholds.json").write_text(json.dumps(thresholds) + "\n")
PY
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates \
  --summary /tmp/sandboxed-agent-eval-gates-current/summary.json \
  --thresholds /tmp/sandboxed-agent-eval-gates-thresholds.json \
  --replay-trace /tmp/sandboxed-agent-eval-gates-current/traces/oracle_tool_selection_agent-data-sales-region-summary-000.jsonl \
  --replay-workspace /tmp/sandboxed-agent-eval-gates-replay
git diff --check -- .
```

Expected result:
- Regression gate tests pass.
- Full test suite passes.
- Gate CLI prints a structured report.
- Gate CLI exits status 0 when thresholds pass.
- Gate CLI tests confirm status 1 when thresholds fail.
- Replay divergence count is included in gate and report outputs.

## Config-backed Regression Gate Preset Validation

Run after config-backed gate presets and trace discovery exist:

```bash
python3 -m pytest tests/test_regression_gates.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-gate-preset-current
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates \
  --summary /tmp/sandboxed-agent-eval-gate-preset-current/summary.json \
  --threshold-preset strict_smoke \
  --discover-traces \
  --replay-workspace /tmp/sandboxed-agent-eval-gate-preset-replay
git diff --check -- .
```

Expected result:
- Project gate preset config loads.
- Gate CLI discovers trace paths from `summary.json`.
- Discovered traces replay without divergence for the oracle smoke run.
- Gate CLI exits status 0 for the strict smoke preset.
- Full test suite remains green.

## Portfolio Suite Expansion Validation

Run after coding and optimization deterministic suites exist:

```bash
python3 -m pytest \
  tests/test_task_suites.py \
  tests/test_tool_registry.py \
  tests/test_tool_execution.py \
  tests/test_validators.py \
  tests/test_eval_runner.py \
  tests/test_trace_replay_execution.py \
  -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-portfolio-suite
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates \
  --summary /tmp/sandboxed-agent-eval-portfolio-suite/summary.json \
  --threshold-preset strict_smoke \
  --discover-traces \
  --replay-workspace /tmp/sandboxed-agent-eval-portfolio-suite-replay
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.report \
  --summary /tmp/sandboxed-agent-eval-portfolio-suite/summary.json \
  --output-dir /tmp/sandboxed-agent-eval-portfolio-report
git diff --check -- .
```

Expected result:
- Default suite includes finance, data analysis, coding, and optimization tasks.
- Coding fixture task patches a file and passes sandboxed unit tests.
- Optimization fixture task writes a deterministic solution artifact.
- Constraint, unit-test, policy, and cost/latency validators are available.
- Oracle smoke prints `runs=8 task_success_rate=1.000 pass_at_k=1.000`.
- Gate preset CLI replays all discovered traces with zero divergences.
- Report CLI writes a four-domain report with zero worst traces for the oracle smoke run.

## Model Adapter And Silent Failure Study Validation

Run after recorded model adapters and silent-failure study output exist:

```bash
python3 -m pytest tests/test_model_adapters.py tests/test_model_study.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir /tmp/sandboxed-agent-eval-model-study
git diff --check -- .
```

Expected result:
- Recorded model output fixtures load without live API access.
- OpenAI Responses adapter request construction is tested through injected transport only.
- `ModelAdapterAgent` runs through the existing evaluation runner.
- Study output writes `summary.json`, report artifacts, and `silent_failure_study.json`.
- CLI prints `models=1 final_answer_pass_rate=1.000 validator_pass_rate=0.500 silent_failures=4`.

## Benchmark-Scale Deterministic Suite Validation

Run after the benchmark suite exists:

```bash
python3 -m pytest tests/test_phase17_benchmark_suite.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite benchmark \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-benchmark
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.gates \
  --summary /tmp/sandboxed-agent-eval-benchmark/summary.json \
  --threshold-preset strict_smoke \
  --discover-traces \
  --replay-workspace /tmp/sandboxed-agent-eval-benchmark-replay
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir /tmp/sandboxed-agent-eval-benchmark-model-study
git diff --check -- .
```

Expected result:
- Benchmark suite loads 64 deterministic fixture-backed tasks.
- Benchmark domains include finance, data analysis, coding, optimization, file workflow, and citation.
- Every benchmark task includes explicit failure-taxonomy traps.
- Oracle benchmark smoke prints `runs=64 task_success_rate=1.000 pass_at_k=1.000`.
- Gate preset CLI replays all benchmark oracle traces with zero divergences.
- Recorded benchmark model study prints `models=1 final_answer_pass_rate=1.000 validator_pass_rate=0.500 silent_failures=32`.

## Failure Taxonomy v2 And Root-Cause Report Validation

Run after normalized root-cause reporting exists:

```bash
python3 -m pytest tests/test_phase18_root_cause.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir /tmp/sandboxed-agent-eval-root-cause-study
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
study = json.loads(Path("/tmp/sandboxed-agent-eval-root-cause-study/silent_failure_study.json").read_text())
report = json.loads(Path("/tmp/sandboxed-agent-eval-root-cause-study/report/report.json").read_text())
print(study["root_cause_breakdown"]["validator_gap"])
print(report["executive_summary"])
print(sorted(report["root_cause_summary"]["categories"]))
PY
git diff --check -- .
```

Expected result:
- Root-cause tests cover every Phase 18 category.
- `report.json` includes `executive_summary` and `root_cause_summary`.
- `report.md` includes an executive summary section.
- `silent_failure_study.json` includes `root_cause_breakdown`.
- The benchmark study prints `models=1 final_answer_pass_rate=1.000 validator_pass_rate=0.500 silent_failures=32`.

## Recorded Model Matrix Validation

Run after the recorded model matrix exists:

```bash
python3 -m pytest tests/test_phase19_model_matrix.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_matrix \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/model_matrix.json \
  --output-dir /tmp/sandboxed-agent-eval-model-matrix
git diff --check -- .
```

Expected result:
- `fixtures/model_outputs/model_matrix.json` defines at least four recorded profiles.
- Every profile covers all 64 benchmark task ids.
- The matrix CLI writes `model_matrix_summary.json`, `model_comparison_report.md`, `silent_failure_by_model.csv`, `summary.json`, and report artifacts.
- The CLI prints at least `models=4`, `distinct_signatures=4`, and `max_validator_gap=...`.
- No network calls, API keys, or live provider credentials are required.

## Credentials-Gated Live Provider Workflow Validation

Run after the live provider workflow exists:

```bash
python3 -m pytest tests/test_phase20_live_provider_workflow.py -v
python3 -m pytest
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --model-provider openai \
  --output-dir /tmp/sandboxed-agent-eval-live-fail-closed
test "$?" -eq 2
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --live \
  --model-provider openai \
  --api-key-env SANDBOXED_AGENT_EVAL_MISSING_OPENAI_KEY \
  --output-dir /tmp/sandboxed-agent-eval-live-skip
make ci
git diff --check -- .
```

Expected result:
- Live CLI fails closed without `--live`.
- Live CLI skips cleanly without credentials and writes `summary.json` with `status=skipped`.
- OpenAI and generic HTTP live adapters are tested through injected transports only.
- `--record-output` writes `raw_outputs.jsonl` and `recorded_fixture_candidate.json` in injected-transport tests.
- Default pytest and `make ci` do not require credentials and do not run live provider calls.

## Sandbox Backend Hardening Validation

Run after workspace and Docker sandbox backends exist:

```bash
python3 -m pytest tests/test_phase21_sandbox_backends.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --sandbox-backend workspace \
  --output-dir /tmp/sandboxed-agent-eval-workspace-backend-smoke
python3 -m pytest
make ci
git diff --check -- .
```

Expected result:
- Workspace backend preserves existing fixture-backed tool behavior.
- Docker backend command surface disables network, applies memory/CPU/PID limits, mounts fixtures read-only, and uses a writable workspace mount.
- Docker unit-test execution path is covered through an injected deterministic command runner, so default tests do not require a local Docker daemon.
- Runner CLI accepts `--sandbox-backend workspace|docker`.
- Docs describe Docker as evaluation isolation, not a security product.

## Config Loader And Suite Registry Validation

Run after runtime config loaders exist:

```bash
python3 -m pytest tests/test_phase22_config_loader.py -v
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate --json
make validate-config
python3 -m pytest
make ci
git diff --check -- .
```

Expected result:
- `load_tools_config()`, `load_validators_config()`, `load_task_suites_config()`, and `load_eval_runs_config()` parse the versioned project configs.
- `validate_project_config()` fails bad config deterministically.
- Runtime tool, validator, task-suite, and eval-run surfaces match the config files.
- `make validate-config` runs the CLI.
- `make ci` includes config validation before smoke, gate, model-study, and report generation.

## Public Portfolio Report Validation

Run after the static portfolio report generator exists:

```bash
python3 -m pytest tests/test_phase23_portfolio_report.py -v
make portfolio-report
test -s reports/portfolio_report.md
test -s reports/portfolio_report.json
test -s reports/tables/model_matrix.csv
test -s reports/tables/failure_taxonomy.csv
test -s reports/tables/domain_breakdown.csv
test "$(find reports/examples -name 'replayable_failure_*.md' | wc -l)" -ge 3
python3 -m pytest
make ci
git diff --check -- .
```

Expected result:
- One command generates the public portfolio report.
- `portfolio_report.md` includes problem, system, evidence, benchmark, failure taxonomy, reproducibility, and limitations.
- `portfolio_report.json` is machine-readable and marks the evidence as recorded/offline, not a live-provider benchmark.
- Model matrix, failure taxonomy, and domain breakdown tables are written under `reports/tables/`.
- Case studies under `reports/examples/` point to replayable JSONL traces.
- Default validation remains key-free and network-free.

## Reproducibility And CI Validation

Run after Makefile commands and GitHub Actions are added:

```bash
python3 -m pytest tests/test_phase16_ci.py -v
make -n ci
make ci
python3 -m pytest
git diff --check -- .
```

Expected result:
- Makefile declares `test`, `smoke`, `gate`, `model-study`, `report`, and `ci`.
- `make ci` runs full pytest, oracle smoke, strict gate, recorded model study, and report generation.
- GitHub Actions workflow uses `working-directory: sandboxed-agent-eval-harness`.
- GitHub Actions workflow does not reference live API credentials or `--live`.
- Artifacts are generated under ignored `artifacts/`.

## Before Commit

Always run:

```bash
git status --short --untracked-files=all -- .
git diff --check -- .
```

Also run the phase-specific commands above for the files touched.
