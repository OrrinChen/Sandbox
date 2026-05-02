# replayable_failure_01: citation-nvda-datacenter-evidence-01

Model or baseline: recorded_overconfident_model
Trace path: artifacts/eval_runs/portfolio_model_matrix/traces/recorded_overconfident_model-citation-nvda-datacenter-evidence-01-000.jsonl
Root causes: CITATION_UNSUPPORTED, FINAL_ANSWER_OVERCLAIM, NUMERIC_MISMATCH
Failure types: numeric_mismatch, unsupported_citation
Tool sequence: transcript.search

## Prompt
Benchmark citation task 1: identify NVIDIA FY2024 data center revenue and cite the transcript source id.

## Replay command
Replay command:
```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor
result = TraceReplayExecutor().replay(Path('artifacts/eval_runs/portfolio_model_matrix/traces/recorded_overconfident_model-citation-nvda-datacenter-evidence-01-000.jsonl'), workspace='/tmp/sandboxed-agent-eval-portfolio-replay')
print(result.to_dict())
PY
```
