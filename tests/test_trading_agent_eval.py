from __future__ import annotations

from pathlib import Path

from sandboxed_agent_eval_harness.agents import AgentBaseline, AgentRunPlan, PlannedToolCall
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tasks import task_suite_by_name, trading_task_suite
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, default_tool_registry
from sandboxed_agent_eval_harness.tracing import load_trace_events
from sandboxed_agent_eval_harness.validators import (
    default_validator_names,
    validate_artifact_grounding,
    validate_cost_inclusion,
    validate_lookahead,
    validate_pnl_consistency,
    validate_risk_limits,
)


ROOT = Path(__file__).resolve().parents[1]
TRADING_TOOLS = {"load_market_data", "run_backtest", "read_strategy_report", "risk_check", "compare_artifacts"}
TRADING_VALIDATORS = {
    "lookahead_validator",
    "pnl_consistency_validator",
    "cost_inclusion_validator",
    "risk_limit_validator",
    "artifact_grounding_validator",
}


def test_trading_task_suite_is_fixture_backed_and_runtime_registered():
    suite = trading_task_suite()
    registry = default_tool_registry()

    assert task_suite_by_name("trading").suite_id == "trading-agent-eval-suite"
    assert suite.version == "trading-tasks-v1"
    assert len(suite.tasks) == 6
    assert {task.domain for task in suite.tasks} == {"trading_agent_eval"}
    assert TRADING_TOOLS.issubset(set(registry.names()))
    assert TRADING_VALIDATORS.issubset(set(default_validator_names()))
    for task in suite.tasks:
        metadata = suite.metadata_for(task.task_id)
        assert set(task.available_tools).issubset(set(registry.names()))
        assert set(task.validator_list).issubset(set(default_validator_names()))
        assert task.max_cost == 0.0
        assert metadata["final_answer_only_risk"] is True
        assert metadata["known_failure_traps"]


def test_trading_fixture_tools_execute_backtest_risk_and_comparison(tmp_path):
    task = _trading_task("trading-cost-aware-vs-gross-pnl")
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")

    market_data = executor.execute("load_market_data", {"artifact_path": "fixtures/trading/lob_snapshot.json"}, sandbox)
    backtest = executor.execute(
        "run_backtest",
        {
            "market_data_path": "fixtures/trading/lob_snapshot.json",
            "strategy_id": "mean_reversion_v1",
            "config_path": "fixtures/trading/backtest_config_cost_aware.json",
            "output_path": "cost_aware_backtest.json",
        },
        sandbox,
    )
    risk = executor.execute(
        "risk_check",
        {"backtest_path": "cost_aware_backtest.json", "limits_path": "fixtures/trading/risk_limits.json"},
        sandbox,
    )
    comparison = executor.execute(
        "compare_artifacts",
        {"gross_path": "fixtures/trading/backtest_gross_report.json", "cost_aware_path": "cost_aware_backtest.json"},
        sandbox,
    )

    assert market_data["artifact_id"] == "lob-es-mini-2024-01-03"
    assert market_data["has_future_return_column"] is False
    assert backtest["gross_pnl"] == 1050.0
    assert backtest["net_pnl"] == 820.0
    assert backtest["fees"] == 230.0
    assert backtest["costs_included"] is True
    assert backtest["lookahead_detected"] is False
    assert risk["passed"] is True
    assert comparison["fee_drag"] == 230.0
    assert comparison["winner"] == "cost_aware"


def test_trading_validators_catch_silent_backtest_failures(tmp_path):
    task = _trading_task("trading-lookahead-risk-silent-failure")
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")

    backtest = executor.execute(
        "run_backtest",
        {
            "market_data_path": "fixtures/trading/lob_snapshot_with_future_return.json",
            "strategy_id": "mean_reversion_v1",
            "config_path": "fixtures/trading/backtest_config_gross_lookahead.json",
            "output_path": "bad_backtest.json",
        },
        sandbox,
    )
    risk = executor.execute(
        "risk_check",
        {"backtest_path": "bad_backtest.json", "limits_path": "fixtures/trading/risk_limits.json"},
        sandbox,
    )
    events = [_tool_result("run_backtest", backtest), _tool_result("risk_check", risk)]

    assert validate_lookahead(events).failure_type == "lookahead_detected"
    assert validate_cost_inclusion(events).failure_type == "costs_not_included"
    assert validate_pnl_consistency(events, {"net_pnl": 1250.0, "sharpe": 2.3}).failure_type == "pnl_consistency_mismatch"
    assert validate_risk_limits(events).failure_type == "risk_limit_violation"
    assert (
        validate_artifact_grounding(
            "Strategy is profitable, Sharpe 2.3, net PnL 1250.",
            events,
            required_sources=["strategy-report-mean-reversion-v1"],
        ).failure_type
        == "artifact_grounding_missing"
    )


def test_trading_evaluation_oracle_passes_and_bad_agent_has_answer_only_silent_failures(tmp_path):
    suite = trading_task_suite()
    good_summary = run_evaluation(suite=suite, baselines=[_TradingOracleAgent()], trials_per_task=1, output_dir=tmp_path / "good")
    bad_summary = run_evaluation(suite=suite, baselines=[_TradingBadBacktestAgent()], trials_per_task=1, output_dir=tmp_path / "bad")

    assert good_summary.metrics["task_success_rate"] == 1.0
    assert bad_summary.metrics["task_success_rate"] == 0.0
    assert all(run.metrics["final_answer_passed"] is True for run in bad_summary.runs)
    failure_types = {
        result.failure_type
        for run in bad_summary.runs
        for result in run.validator_results
        if not result.passed
    }
    assert {"lookahead_detected", "costs_not_included", "pnl_consistency_mismatch", "risk_limit_violation"}.issubset(failure_types)
    trace_events = load_trace_events(bad_summary.runs[0].trace_path)
    assert any(event.payload.get("tool_name") == "run_backtest" for event in trace_events)


def test_trading_domain_is_documented_without_live_trading_overclaim():
    readme = (ROOT / "README.md").read_text()
    notes = (ROOT / "docs" / "trading_agent_eval.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()

    assert "trading-agent eval domain" in readme
    assert "LOB/backtest/risk artifacts" in readme
    assert "lookahead leakage" in readme
    assert "omitted costs" in readme
    assert "not a trading agent product" in notes
    assert "--suite trading" in notes
    assert "runs=6 task_success_rate=1.000 pass_at_k=1.000" in notes
    assert "not a live trading benchmark" in roadmap


class _TradingOracleAgent(AgentBaseline):
    name = "trading_oracle_agent"

    def run(self, task, attempt_index=0):
        return _trading_plan(task, self.name, bad=False)


class _TradingBadBacktestAgent(AgentBaseline):
    name = "trading_bad_backtest_agent"

    def run(self, task, attempt_index=0):
        return _trading_plan(task, self.name, bad=True)


def _trading_plan(task, agent_name: str, *, bad: bool) -> AgentRunPlan:
    if bad:
        metrics = {"net_pnl": 1250.0, "gross_pnl": 1250.0, "fees": 0.0, "sharpe": 2.3, "max_drawdown": 0.12}
        config_path = "fixtures/trading/backtest_config_gross_lookahead.json"
        market_data_path = "fixtures/trading/lob_snapshot_with_future_return.json"
        output_path = "bad_backtest.json"
        final = "Strategy is profitable: net_pnl=1250.0, sharpe=2.3, max_drawdown=0.12."
    else:
        metrics = dict(task.hidden_expected_state["numeric"])
        config_path = "fixtures/trading/backtest_config_cost_aware.json"
        market_data_path = "fixtures/trading/lob_snapshot.json"
        output_path = "cost_aware_backtest.json"
        final = "Use cost-aware strategy: net_pnl=820.0, sharpe=1.42, max_drawdown=0.071 [strategy-report-mean-reversion-v1]."
    tool_calls = [
        PlannedToolCall("load_market_data", {"artifact_path": market_data_path}, {}),
        PlannedToolCall(
            "run_backtest",
            {"market_data_path": market_data_path, "strategy_id": "mean_reversion_v1", "config_path": config_path, "output_path": output_path},
            {},
        ),
        PlannedToolCall("read_strategy_report", {"report_path": "fixtures/trading/strategy_report.json"}, {}),
        PlannedToolCall("risk_check", {"backtest_path": output_path, "limits_path": "fixtures/trading/risk_limits.json"}, {}),
        PlannedToolCall("compare_artifacts", {"gross_path": "fixtures/trading/backtest_gross_report.json", "cost_aware_path": output_path}, {}),
    ]
    return AgentRunPlan(
        agent_name=agent_name,
        final_answer=final,
        tool_calls=tool_calls,
        reported_metrics=metrics,
        state_diff={"added": [output_path], "modified": [], "deleted": []},
        turns=6,
        latency_seconds=0.02,
        cost=0.0,
        final_answer_passed=True,
    )


def _trading_task(task_id):
    return next(task for task in trading_task_suite().tasks if task.task_id == task_id)


def _tool_result(tool_name, result):
    from sandboxed_agent_eval_harness.schemas import TraceEvent

    return TraceEvent(
        event_id=f"{tool_name}-result",
        event_type="tool_result",
        sequence=0,
        payload={"tool_name": tool_name, "result": result},
    )
