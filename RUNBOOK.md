# RUNBOOK.md

Operational notes for local and autonomous Codex runs.

## Orientation

Start every session from the project directory:

```bash
cd "/Users/orynwilder/Documents/New project 2/sandboxed-agent-eval-harness"
git status --short
```

Then read:

```bash
sed -n '1,220p' README.md
sed -n '1,260p' ROADMAP.md
sed -n '1,220p' TASK_MEMORY.md
sed -n '1,220p' VALIDATION.md
```

## Advancing a Phase

1. Identify the current phase in `ROADMAP.md`.
2. Work only on that phase unless the user changes direction.
3. Keep changes small and testable.
4. Run the validation commands for that phase.
5. Update `TASK_MEMORY.md` with:
   - Files changed
   - Commands run
   - Results
   - Known limitations
   - Next recommended action
6. Commit only when the user asked for commits or the autonomous run explicitly includes committing.

## Current Stage Commands

Full reproducibility validation:

```bash
make validate-config
make ci
git diff --check -- .
```

## Expected Future Commands

After Phase 1 creates the Python package:

```bash
python3 -m pytest
PYTHONPATH=src python3 - <<'PY'
import sandboxed_agent_eval_harness
print(sandboxed_agent_eval_harness.__name__)
PY
```

After an evaluation runner exists:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner --suite smoke
```

Recorded model silent-failure study:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir /tmp/sandboxed-agent-eval-model-study
```

Benchmark oracle run:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite benchmark \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir /tmp/sandboxed-agent-eval-benchmark
```

Benchmark recorded model study:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir /tmp/sandboxed-agent-eval-benchmark-model-study
```

Root-cause report inspection:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_study \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/silent_failure_study.json \
  --output-dir /tmp/sandboxed-agent-eval-root-cause-study
python3 - <<'PY'
import json
from pathlib import Path
study = json.loads(Path("/tmp/sandboxed-agent-eval-root-cause-study/silent_failure_study.json").read_text())
print(study["root_cause_breakdown"]["validator_gap"])
print(study["root_cause_breakdown"]["executive_summary"])
PY
```

Recorded model matrix:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.model_matrix \
  --suite benchmark \
  --recorded-output fixtures/model_outputs/model_matrix.json \
  --output-dir /tmp/sandboxed-agent-eval-model-matrix
```

Expected output includes:

```text
models=5 run_count=320 distinct_signatures=5 max_validator_gap=1.000
```

Credentials-gated live provider workflow:

Fail-closed check:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --model-provider openai \
  --output-dir /tmp/sandboxed-agent-eval-live-fail-closed
```

Expected output includes:

```text
status=failed_closed reason=live_flag_required
```

Missing-credential skip check:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --live \
  --model-provider openai \
  --api-key-env SANDBOXED_AGENT_EVAL_MISSING_OPENAI_KEY \
  --output-dir /tmp/sandboxed-agent-eval-live-skip
```

Expected output includes:

```text
status=skipped reason=missing_credentials
```

Manual live run with intentional credentials:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.live_provider \
  --live \
  --model-provider openai \
  --model "$OPENAI_MODEL" \
  --max-tasks 1 \
  --max-cost-usd 0.25 \
  --record-output \
  --output-dir artifacts/live_runs/manual
```

Do not run live commands in CI, and do not commit generated live artifacts.

Sandbox backend smoke:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --sandbox-backend workspace \
  --output-dir /tmp/sandboxed-agent-eval-workspace-backend-smoke
```

Expected output includes:

```text
sandbox_backend=workspace
```

Optional Docker backend smoke, only when Docker is intentionally available:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite smoke \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --sandbox-backend docker \
  --output-dir /tmp/sandboxed-agent-eval-docker-backend-smoke
```

The Docker backend is evaluation isolation, not a security product. Default CI does not require Docker.

Runtime config validation:

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.config.validate --json
```

Expected output includes:

```text
config_validation=passed tools=7 validators=10 task_suites=2 eval_runs=1
```

This checks the project-owned tool, validator, task-suite, and eval-run configs against runtime defaults and manifests. It uses the current controlled config format; treat failures as real drift until proven otherwise.

Public portfolio report:

```bash
make portfolio-report
```

Expected output includes:

```text
portfolio_report=reports/portfolio_report.md case_studies=3 models=5
```

Generated files:

```text
reports/portfolio_report.md
reports/portfolio_report.json
reports/tables/model_matrix.csv
reports/tables/failure_taxonomy.csv
reports/tables/domain_breakdown.csv
reports/examples/replayable_failure_*.md
```

The report uses recorded offline model profiles and fixture-backed benchmark tasks. It is not a live-provider benchmark and does not require API keys.

GitHub Actions:

```text
.github/workflows/sandboxed-agent-eval-harness-ci.yml
```

The workflow lives at the git repository root so GitHub can discover it, but every run step uses:

```text
working-directory: sandboxed-agent-eval-harness
```

## Data and Network Policy

Default tests should be local and deterministic.

Use fixture-backed data for:
- Finance statements
- Transcript snippets
- CSV/data analysis tasks
- Gold numeric outputs
- Citation evidence

Do not require:
- Paid APIs
- Live financial data
- Cloud services
- Credentials

If a task truly requires credentials or paid services, stop and ask the user.

## Troubleshooting

If tests do not exist:
- Run documentation validation.
- Do not claim product behavior is verified.
- Record the limitation in `TASK_MEMORY.md`.

If `git status` shows sibling project changes:
- Ignore them unless the user explicitly asks about them.
- Do not modify sibling directories.

If a validator result is subjective:
- Replace it with a deterministic check where possible.
- Record any remaining subjective judgment as a limitation.

If trace replay cannot reproduce a failure:
- Treat replay as failed.
- Record missing metadata or fixture state.
- Do not mark the phase complete.

## Local vs Cloud Codex

Use local Codex for:
- Local files and datasets
- Fixture generation from local data
- Environment debugging
- Long-running local experiments

Use Codex Cloud for:
- Pure code refactors
- Test additions
- Documentation cleanup
- PR review
- Parallel tasks that do not need local private files
