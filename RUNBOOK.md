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

Documentation-only validation:

```bash
for f in README.md AGENTS.md ROADMAP.md TASK_MEMORY.md VALIDATION.md RUNBOOK.md; do test -s "$f" || exit 1; done
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
