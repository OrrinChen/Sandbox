"""Optional MCP protocol adapter for fixture-backed harness tools.

This module intentionally implements the small JSON-RPC surface the harness needs
for evaluation: `tools/list`, `tools/call`, and trace conversion. It does not
start a live MCP server or depend on the MCP Python SDK in default validation.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Optional

from sandboxed_agent_eval_harness.sandbox import FileSystemSandbox
from sandboxed_agent_eval_harness.schemas import JsonDict, SchemaValidationError, TraceEvent
from sandboxed_agent_eval_harness.tools import (
    FixtureToolExecutor,
    ToolExecutionError,
    ToolRegistry,
    default_tool_registry,
)
from sandboxed_agent_eval_harness.tools.registry import ToolRegistryError
from sandboxed_agent_eval_harness.tracing import TraceLogger


JSONRPC_VERSION = "2.0"
MCP_TOOLS_LIST = "tools/list"
MCP_TOOLS_CALL = "tools/call"


class MCPToolAdapter:
    """Map harness tool specs and fixture execution into MCP-shaped payloads."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        *,
        executor: Optional[FixtureToolExecutor] = None,
        logger: Optional[TraceLogger] = None,
    ) -> None:
        self.registry = registry or default_tool_registry()
        self.executor = executor or FixtureToolExecutor(self.registry)
        self.logger = logger

    def tool_descriptors(self, tool_names: Optional[Iterable[str]] = None) -> list[JsonDict]:
        names = list(tool_names or self.registry.names())
        descriptors: list[JsonDict] = []
        for tool_name in names:
            tool = self.registry.get(tool_name)
            descriptors.append(
                {
                    "name": tool.tool_name,
                    "description": (
                        f"Fixture-backed MCP view of harness tool `{tool.tool_name}`; "
                        "outputs remain checked by deterministic harness validators."
                    ),
                    "inputSchema": dict(tool.input_schema),
                    "annotations": {
                        "fixtureBacked": True,
                        "permissions": list(tool.permissions),
                        "sideEffects": list(tool.side_effects),
                        "stateMutation": dict(tool.state_mutation),
                        "failureModes": list(tool.failure_modes),
                    },
                }
            )
        return descriptors

    def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        sandbox: FileSystemSandbox,
        request_id: Any = None,
    ) -> JsonDict:
        validated_arguments = self.registry.validate_input(tool_name, arguments)
        trace_metadata = _mcp_trace_metadata(request_id)
        if self.logger is not None:
            self.logger.log_tool_call(tool_name, validated_arguments, metadata=trace_metadata)
        result = self.executor.execute(tool_name, validated_arguments, sandbox)
        if self.logger is not None:
            self.logger.log_tool_result(tool_name, result, metadata=trace_metadata)
        return mcp_tool_result(result, is_error=False)


class MCPFixtureServer:
    """Credential-free fixture MCP server facade for tests and local smoke checks."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        *,
        executor: Optional[FixtureToolExecutor] = None,
        logger: Optional[TraceLogger] = None,
    ) -> None:
        self.registry = registry or default_tool_registry()
        self.executor = executor or FixtureToolExecutor(self.registry)
        self.adapter = MCPToolAdapter(self.registry, executor=self.executor, logger=logger)

    def handle_jsonrpc(
        self,
        request: Mapping[str, Any],
        *,
        sandbox: Optional[FileSystemSandbox] = None,
    ) -> JsonDict:
        request_id = request.get("id")
        if request.get("jsonrpc") != JSONRPC_VERSION:
            return _error_response(request_id, -32600, "invalid JSON-RPC request: expected jsonrpc='2.0'")
        method = request.get("method")
        if method == MCP_TOOLS_LIST:
            return _success_response(request_id, {"tools": self.adapter.tool_descriptors()})
        if method == MCP_TOOLS_CALL:
            if sandbox is None:
                return _error_response(request_id, -32000, "tools/call requires a fixture sandbox")
            params = request.get("params", {})
            if not isinstance(params, Mapping):
                return _error_response(request_id, -32602, "tools/call params must be an object")
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(tool_name, str) or not tool_name:
                return _error_response(request_id, -32602, "tools/call params.name must be a non-empty string")
            if not isinstance(arguments, Mapping):
                return _error_response(request_id, -32602, "tools/call params.arguments must be an object")
            try:
                result = self.adapter.call_tool(tool_name, arguments, sandbox=sandbox, request_id=request_id)
            except (SchemaValidationError, ToolRegistryError) as exc:
                return _error_response(request_id, -32602, str(exc))
            except ToolExecutionError as exc:
                return _success_response(request_id, mcp_tool_error(str(exc)))
            return _success_response(request_id, result)
        return _error_response(request_id, -32601, f"unsupported MCP method: {method}")


class MCPTraceReplay:
    """Convert MCP JSON-RPC tool exchanges to and from harness trace events."""

    def __init__(self, events: Iterable[TraceEvent]) -> None:
        self.events = [event for event in events if event.metadata.get("integration") == "mcp"]

    @staticmethod
    def write_trace_from_jsonrpc_exchange(
        records: Iterable[Mapping[str, Any]],
        logger: TraceLogger,
    ) -> JsonDict:
        pending_tool_names: dict[Any, str] = {}
        summary = {"requests": 0, "responses": 0, "tool_calls": 0, "tool_results": 0}
        for record in records:
            record_id = record.get("id")
            if record.get("method") == MCP_TOOLS_CALL:
                params = record.get("params", {})
                if not isinstance(params, Mapping):
                    continue
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(tool_name, str) or not isinstance(arguments, Mapping):
                    continue
                logger.log_tool_call(tool_name, arguments, metadata=_mcp_trace_metadata(record_id))
                pending_tool_names[record_id] = tool_name
                summary["requests"] += 1
                summary["tool_calls"] += 1
                continue
            if "result" in record or "error" in record:
                summary["responses"] += 1
                tool_name = pending_tool_names.get(record_id, "unknown_mcp_tool")
                result = record.get("result", {})
                if isinstance(result, Mapping):
                    structured = result.get("structuredContent", {})
                    is_error = bool(result.get("isError", False))
                else:
                    structured = {}
                    is_error = False
                if "error" in record:
                    error = record.get("error", {})
                    structured = {"error": error if isinstance(error, Mapping) else {"message": str(error)}}
                    is_error = True
                logger.log_tool_result(
                    tool_name,
                    structured if isinstance(structured, Mapping) else {},
                    metadata={**_mcp_trace_metadata(record_id), "mcp_is_error": is_error},
                )
                summary["tool_results"] += 1
        return summary

    def summary(self) -> JsonDict:
        call_ids = [
            event.metadata.get("mcp_request_id")
            for event in self.events
            if event.event_type == "tool_call"
        ]
        result_ids = {
            event.metadata.get("mcp_request_id")
            for event in self.events
            if event.event_type == "tool_result"
        }
        return {
            "mcp_tool_calls": len(call_ids),
            "mcp_tool_results": len(result_ids),
            "missing_results": sum(1 for request_id in call_ids if request_id not in result_ids),
        }

    def to_jsonrpc_records(self) -> list[JsonDict]:
        records: list[JsonDict] = []
        for event in self.events:
            request_id = event.metadata.get("mcp_request_id")
            if event.event_type == "tool_call":
                records.append(
                    {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": request_id,
                        "method": MCP_TOOLS_CALL,
                        "params": {
                            "name": event.payload["tool_name"],
                            "arguments": dict(event.payload["arguments"]),
                        },
                    }
                )
            elif event.event_type == "tool_result":
                records.append(
                    {
                        "jsonrpc": JSONRPC_VERSION,
                        "id": request_id,
                        "result": mcp_tool_result(event.payload.get("result", {}), is_error=False),
                    }
                )
        return records


def mcp_tool_result(result: Mapping[str, Any], *, is_error: bool) -> JsonDict:
    structured = dict(result)
    return {
        "content": [{"type": "text", "text": json.dumps(structured, sort_keys=True)}],
        "structuredContent": structured,
        "isError": is_error,
    }


def mcp_tool_error(message: str) -> JsonDict:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {"error": message},
        "isError": True,
    }


def _mcp_trace_metadata(request_id: Any) -> JsonDict:
    return {
        "integration": "mcp",
        "mcp_method": MCP_TOOLS_CALL,
        "mcp_request_id": request_id,
        "mcp_transport": "fixture_jsonrpc",
        "live_mcp_server": False,
    }


def _success_response(request_id: Any, result: Mapping[str, Any]) -> JsonDict:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": dict(result)}


def _error_response(request_id: Any, code: int, message: str) -> JsonDict:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
