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
    ]


def default_tool_registry() -> ToolRegistry:
    return ToolRegistry(default_tool_specs())
