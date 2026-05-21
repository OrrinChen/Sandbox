"""Typed tool registry and default tool declarations."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from sandboxed_agent_eval_harness.schemas import JsonDict, ToolSpec


class ToolRegistryError(ValueError):
    """Base error for registry lookup and registration failures."""


class UnknownToolError(ToolRegistryError):
    """Raised when a requested tool name is not registered."""


class DuplicateToolError(ToolRegistryError):
    """Raised when two tool specs use the same tool name."""


class ToolRegistry:
    """Registry for typed tools with deterministic input/output validation."""

    def __init__(self, tools: Iterable[ToolSpec] = ()) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ToolSpec) -> None:
        if tool.tool_name in self._tools:
            raise DuplicateToolError(f"duplicate tool registered: {tool.tool_name}")
        self._tools[tool.tool_name] = tool

    def names(self) -> List[str]:
        return sorted(self._tools)

    def get(self, tool_name: str) -> ToolSpec:
        try:
            return self._tools[tool_name]
        except KeyError as exc:
            raise UnknownToolError(f"unknown tool: {tool_name}") from exc

    def validate_input(self, tool_name: str, arguments: Mapping[str, Any]) -> JsonDict:
        return self.get(tool_name).validate_input(arguments)

    def validate_output(self, tool_name: str, result: Mapping[str, Any]) -> JsonDict:
        return self.get(tool_name).validate_output(result)

    def metadata(self, tool_name: str) -> JsonDict:
        tool = self.get(tool_name)
        return {
            "tool_name": tool.tool_name,
            "permissions": list(tool.permissions),
            "side_effects": list(tool.side_effects),
            "state_mutation": dict(tool.state_mutation),
            "failure_modes": list(tool.failure_modes),
        }


def default_tool_specs() -> List[ToolSpec]:
    return [
        ToolSpec(
            tool_name="financial_statement.lookup",
            input_schema={
                "type": "object",
                "required": ["ticker", "fiscal_year", "statement"],
                "properties": {
                    "ticker": {"type": "string"},
                    "fiscal_year": {"type": "integer"},
                    "statement": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["ticker", "fiscal_year", "statement", "source", "values"],
                "properties": {
                    "ticker": {"type": "string"},
                    "fiscal_year": {"type": "integer"},
                    "statement": {"type": "string"},
                    "source": {"type": "string"},
                    "values": {"type": "object"},
                },
            },
            side_effects=[],
            permissions=["read_fixture"],
            state_mutation={},
            failure_modes=[
                "missing_fixture",
                "wrong_fiscal_period",
                "wrong_statement_type",
                "unsupported_ticker",
            ],
        ),
        ToolSpec(
            tool_name="transcript.search",
            input_schema={
                "type": "object",
                "required": ["ticker", "fiscal_period", "query"],
                "properties": {
                    "ticker": {"type": "string"},
                    "fiscal_period": {"type": "string"},
                    "query": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["ticker", "fiscal_period", "source", "matches"],
                "properties": {
                    "ticker": {"type": "string"},
                    "fiscal_period": {"type": "string"},
                    "source": {"type": "string"},
                    "matches": {"type": "array"},
                },
            },
            side_effects=[],
            permissions=["read_fixture"],
            state_mutation={},
            failure_modes=[
                "missing_fixture",
                "unsupported_query",
                "unsupported_citation",
                "wrong_fiscal_period",
            ],
        ),
        ToolSpec(
            tool_name="csv.read",
            input_schema={
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string"},
                    "delimiter": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["path", "columns", "rows"],
                "properties": {
                    "path": {"type": "string"},
                    "columns": {"type": "array"},
                    "rows": {"type": "integer"},
                },
            },
            side_effects=[],
            permissions=["read_visible_files"],
            state_mutation={},
            failure_modes=["missing_file", "invalid_csv", "schema_mismatch"],
        ),
        ToolSpec(
            tool_name="csv.group_metrics",
            input_schema={
                "type": "object",
                "required": ["path", "group_by", "metric", "output_path"],
                "properties": {
                    "path": {"type": "string"},
                    "group_by": {"type": "string"},
                    "metric": {"type": "string"},
                    "output_path": {"type": "string"},
                    "drop_missing": {"type": "boolean"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["rows", "output_path"],
                "properties": {
                    "rows": {"type": "integer"},
                    "output_path": {"type": "string"},
                },
            },
            side_effects=["writes_file"],
            permissions=["read_visible_files", "write_task_workspace"],
            state_mutation={"writes": ["summary_table"]},
            failure_modes=[
                "missing_file",
                "missing_column",
                "invalid_metric",
                "invalid_csv",
                "write_denied",
            ],
        ),
        ToolSpec(
            tool_name="code.patch",
            input_schema={
                "type": "object",
                "required": ["path", "replacements"],
                "properties": {
                    "path": {"type": "string"},
                    "replacements": {"type": "array"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["path", "replacements_applied"],
                "properties": {
                    "path": {"type": "string"},
                    "replacements_applied": {"type": "integer"},
                },
            },
            side_effects=["modifies_file"],
            permissions=["read_visible_files", "write_task_workspace"],
            state_mutation={"modifies": ["source_file"]},
            failure_modes=["missing_file", "replacement_not_found", "invalid_patch", "write_denied"],
        ),
        ToolSpec(
            tool_name="python.unit_tests",
            input_schema={
                "type": "object",
                "required": ["test_path"],
                "properties": {
                    "test_path": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["passed", "tests_run", "failures"],
                "properties": {
                    "passed": {"type": "boolean"},
                    "tests_run": {"type": "integer"},
                    "failures": {"type": "integer"},
                },
            },
            side_effects=[],
            permissions=["read_visible_files", "execute_sandboxed_python"],
            state_mutation={},
            failure_modes=["missing_file", "test_failure", "timeout", "invalid_test_fixture"],
        ),
        ToolSpec(
            tool_name="optimization.solve_newsvendor",
            input_schema={
                "type": "object",
                "required": ["path", "output_path"],
                "properties": {
                    "path": {"type": "string"},
                    "output_path": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["output_path", "order_quantity", "service_level", "expected_cost", "source"],
                "properties": {
                    "output_path": {"type": "string"},
                    "order_quantity": {"type": "integer"},
                    "service_level": {"type": "number"},
                    "expected_cost": {"type": "number"},
                    "source": {"type": "string"},
                },
            },
            side_effects=["writes_file"],
            permissions=["read_visible_files", "write_task_workspace"],
            state_mutation={"writes": ["optimization_solution"]},
            failure_modes=["missing_file", "invalid_fixture", "infeasible_instance", "write_denied"],
        ),
        ToolSpec(
            tool_name="load_market_data",
            input_schema={
                "type": "object",
                "required": ["artifact_path"],
                "properties": {"artifact_path": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["artifact_id", "symbol", "rows", "start_ts", "end_ts", "has_future_return_column"],
                "properties": {
                    "artifact_id": {"type": "string"},
                    "symbol": {"type": "string"},
                    "rows": {"type": "integer"},
                    "start_ts": {"type": "string"},
                    "end_ts": {"type": "string"},
                    "has_future_return_column": {"type": "boolean"},
                },
            },
            side_effects=[],
            permissions=["read_visible_files"],
            state_mutation={},
            failure_modes=["missing_artifact", "invalid_lob_artifact", "lookahead_column_present"],
        ),
        ToolSpec(
            tool_name="run_backtest",
            input_schema={
                "type": "object",
                "required": ["market_data_path", "strategy_id", "config_path", "output_path"],
                "properties": {
                    "market_data_path": {"type": "string"},
                    "strategy_id": {"type": "string"},
                    "config_path": {"type": "string"},
                    "output_path": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": [
                    "strategy_id",
                    "config_id",
                    "gross_pnl",
                    "net_pnl",
                    "fees",
                    "sharpe",
                    "max_drawdown",
                    "costs_included",
                    "lookahead_detected",
                    "output_path",
                    "source",
                ],
                "properties": {
                    "strategy_id": {"type": "string"},
                    "config_id": {"type": "string"},
                    "gross_pnl": {"type": "number"},
                    "net_pnl": {"type": "number"},
                    "fees": {"type": "number"},
                    "sharpe": {"type": "number"},
                    "max_drawdown": {"type": "number"},
                    "costs_included": {"type": "boolean"},
                    "lookahead_detected": {"type": "boolean"},
                    "output_path": {"type": "string"},
                    "source": {"type": "string"},
                },
            },
            side_effects=["writes_file"],
            permissions=["read_visible_files", "write_task_workspace"],
            state_mutation={"writes": ["backtest_result"]},
            failure_modes=["missing_market_data", "invalid_config", "lookahead_detected", "costs_not_included"],
        ),
        ToolSpec(
            tool_name="read_strategy_report",
            input_schema={
                "type": "object",
                "required": ["report_path"],
                "properties": {"report_path": {"type": "string"}},
            },
            output_schema={
                "type": "object",
                "required": ["source", "strategy_id", "recommended_strategy", "metrics", "warnings"],
                "properties": {
                    "source": {"type": "string"},
                    "strategy_id": {"type": "string"},
                    "recommended_strategy": {"type": "string"},
                    "metrics": {"type": "object"},
                    "warnings": {"type": "array"},
                },
            },
            side_effects=[],
            permissions=["read_visible_files"],
            state_mutation={},
            failure_modes=["missing_report", "invalid_report", "ungrounded_claim"],
        ),
        ToolSpec(
            tool_name="risk_check",
            input_schema={
                "type": "object",
                "required": ["backtest_path", "limits_path"],
                "properties": {
                    "backtest_path": {"type": "string"},
                    "limits_path": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["passed", "violations", "max_drawdown", "limit_max_drawdown", "source"],
                "properties": {
                    "passed": {"type": "boolean"},
                    "violations": {"type": "array"},
                    "max_drawdown": {"type": "number"},
                    "limit_max_drawdown": {"type": "number"},
                    "source": {"type": "string"},
                },
            },
            side_effects=[],
            permissions=["read_visible_files"],
            state_mutation={},
            failure_modes=["missing_backtest", "invalid_limits", "risk_limit_violation"],
        ),
        ToolSpec(
            tool_name="compare_artifacts",
            input_schema={
                "type": "object",
                "required": ["gross_path", "cost_aware_path"],
                "properties": {
                    "gross_path": {"type": "string"},
                    "cost_aware_path": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["gross_pnl", "cost_aware_pnl", "fee_drag", "winner", "sources"],
                "properties": {
                    "gross_pnl": {"type": "number"},
                    "cost_aware_pnl": {"type": "number"},
                    "fee_drag": {"type": "number"},
                    "winner": {"type": "string"},
                    "sources": {"type": "array"},
                },
            },
            side_effects=[],
            permissions=["read_visible_files"],
            state_mutation={},
            failure_modes=["missing_artifact", "cost_omission", "inconsistent_artifacts"],
        ),
    ]


def default_tool_registry() -> ToolRegistry:
    return ToolRegistry(default_tool_specs())
