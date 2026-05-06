# Replayable Failure Walkthrough

This walkthrough uses recorded offline evidence from:

```text
artifacts/eval_runs/portfolio_model_matrix/traces/recorded_overconfident_model-citation-nvda-datacenter-evidence-01-000.jsonl
```

Run id:
`recorded_overconfident_model-citation-nvda-datacenter-evidence-01-000`

This example does not require an API key, network access, or a live model provider.

## Prompt

```text
Benchmark citation task 1: identify NVIDIA FY2024 data center revenue and cite the transcript source id.
```

## Why Final-answer Grading Would Pass

The recorded profile produced a plausible final answer and the run metadata marks:

```text
final_answer_passed: true
```

Answer-only grading would treat this as successful because the response appears to name the requested metric and cite evidence.

## What The Trace Shows

The agent called the expected fixture-backed evidence tool:

```text
tool: transcript.search
arguments:
  ticker: NVDA
  fiscal_period: FY2024 Q4
  query: data center revenue
```

The tool returned the supported source and true fixture value:

```text
source: nvda-2024-q4-transcript-datacenter
data_center_revenue: 47525
```

## Validator Failures

Deterministic validators caught two hidden failures:

```text
numeric_mismatch:
  expected: 47525
  actual: 47526
  metric: data_center_revenue_usd_millions

unsupported_citation:
  supported: nvda-2024-q4-transcript-datacenter
  actual: unsupported-citation-nvda-datacenter-evidence-01
```

Root-cause categories:

```text
NUMERIC_MISMATCH
CITATION_UNSUPPORTED
FINAL_ANSWER_OVERCLAIM
```

This is the core silent-failure pattern: the final answer looks plausible, but the numeric value and citation do not match the replayable tool evidence.

## Replay command

```bash
PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from sandboxed_agent_eval_harness.tracing import TraceReplayExecutor

trace = Path("artifacts/eval_runs/portfolio_model_matrix/traces/recorded_overconfident_model-citation-nvda-datacenter-evidence-01-000.jsonl")
result = TraceReplayExecutor().replay(trace, workspace="/tmp/sandboxed-agent-eval-portfolio-replay")
print(result.to_dict())
PY
```

## Expected output

The replay should preserve the ordered trace and expose validator failures equivalent to:

```text
passed: false
final_answer_passed: true
numeric_mismatch actual=47526 expected=47525
unsupported_citation actual=unsupported-citation-nvda-datacenter-evidence-01 supported=nvda-2024-q4-transcript-datacenter
```
