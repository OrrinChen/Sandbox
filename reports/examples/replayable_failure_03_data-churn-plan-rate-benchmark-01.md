# replayable_failure_03: data-churn-plan-rate-benchmark-01

Model or baseline: recorded_overconfident_model
Trace path: artifacts/eval_runs/portfolio_model_matrix/traces/recorded_overconfident_model-data-churn-plan-rate-benchmark-01-000.jsonl
Root causes: FINAL_ANSWER_OVERCLAIM, NUMERIC_MISMATCH
Failure types: numeric_mismatch
Tool sequence: csv.read, csv.group_metrics

## Prompt
Benchmark data task 5: compute churn rate by plan and write a deterministic CSV.

## Replay command
Replay command:
```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor
result = TraceReplayExecutor().replay(Path('artifacts/eval_runs/portfolio_model_matrix/traces/recorded_overconfident_model-data-churn-plan-rate-benchmark-01-000.jsonl'), workspace='/tmp/sandboxed-agent-eval-portfolio-replay')
print(result.to_dict())
PY
```
