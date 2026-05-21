# Trading-Agent Eval Domain

This is a domain extension of the eval harness, not a trading agent product.

The trading suite uses fixture-backed LOB, backtest, strategy-report, and risk-limit artifacts to test whether an agent can make a trading evaluation claim that is actually grounded in the tool trace.

## Scope

- Suite: `trading-agent-eval-suite`
- CLI preset: `--suite trading`
- Tasks: 6 fixture-backed tasks
- Domain: `trading_agent_eval`
- Default behavior: credential-free, network-free, offline fixtures only

## Tools

- `load_market_data`: read a LOB artifact and detect future-return columns.
- `run_backtest`: execute a deterministic fixture backtest and write a workspace artifact.
- `read_strategy_report`: read strategy recommendation metrics and warnings.
- `risk_check`: compare a backtest artifact against risk limits.
- `compare_artifacts`: compare gross-only and cost-aware artifacts.

## Validators

- `lookahead_validator`: fails when the trace uses future-return columns or a lookahead-enabled config.
- `pnl_consistency_validator`: fails when reported PnL, Sharpe, fees, or drawdown do not match the executed backtest artifact.
- `cost_inclusion_validator`: fails when fees are omitted or the backtest is not cost-aware.
- `risk_limit_validator`: fails when risk checks are missing or max drawdown violates limits.
- `artifact_grounding_validator`: fails when final answers cite or rely on artifacts that were not observed in the trace.
- `tool_sequence_validator`: still checks that market data, backtest, report, risk, and comparison tools are used in the expected order.

## Silent Failure Case

A plausible final answer can say:

```text
Strategy is profitable: net_pnl=1250.0, sharpe=2.3, max_drawdown=0.12.
```

The trace can still fail deterministic validation because:

- The backtest used `backtest_config_gross_lookahead.json`.
- The LOB artifact exposed `future_return`.
- Fees were `0.0` instead of `230.0`.
- The reported Sharpe `2.3` did not match the backtest artifact.
- Max drawdown `0.12` violated the `0.08` risk limit.
- The answer did not cite `strategy-report-mean-reversion-v1`.

## Smoke Command

```bash
PYTHONPATH=src python3 -m sandboxed_agent_eval_harness.evaluation.runner \
  --suite trading \
  --baseline oracle_tool_selection_agent \
  --trials 1 \
  --output-dir artifacts/eval_runs/trading_smoke
```

Expected summary:

```text
runs=6 task_success_rate=1.000 pass_at_k=1.000 sandbox_backend=workspace
```

## Resume Wording

Added a trading-agent evaluation domain to a deterministic tool-use agent harness, using LOB and PortfolioOS-style artifacts for backtest, risk-check, and artifact-grounding tasks; validators catch trading backtest hallucinations and risk omissions that final-answer-only grading misses, including omitted costs, lookahead leakage, wrong Sharpe/PnL, ignored max drawdown, and wrong backtest config.
