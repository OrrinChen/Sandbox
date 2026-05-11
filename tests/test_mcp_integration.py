from __future__ import annotations

import json
from pathlib import Path

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tracing import TraceLogger, load_trace_events


ROOT = Path(__file__).resolve().parents[1]


def test_mcp_fixture_server_lists_harness_tools_as_mcp_descriptors():
    from sandboxed_agent_eval_harness.integrations.mcp import MCPFixtureServer
    from sandboxed_agent_eval_harness.tools import default_tool_registry

    response = MCPFixtureServer().handle_jsonrpc(
        {"jsonrpc": "2.0", "id": "tools-1", "method": "tools/list", "params": {}}
    )

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "tools-1"
    tools = response["result"]["tools"]
    assert {tool["name"] for tool in tools} == set(default_tool_registry().names())
    transcript_tool = next(tool for tool in tools if tool["name"] == "transcript.search")
    assert transcript_tool["inputSchema"]["required"] == ["ticker", "fiscal_period", "query"]
    assert transcript_tool["annotations"]["fixtureBacked"] is True
    assert transcript_tool["annotations"]["sideEffects"] == []
    assert "deterministic harness validators" in transcript_tool["description"]


def test_mcp_tool_call_executes_fixture_tool_and_emits_trace_events(tmp_path):
    from sandboxed_agent_eval_harness.integrations.mcp import MCPFixtureServer
    from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, default_tool_registry

    task = default_task_suite().tasks[0]
    plan = OracleToolSelectionAgent().run(task)
    tool_call = plan.tool_calls[0]
    trace_path = tmp_path / "mcp_tool_call.jsonl"
    logger = TraceLogger(trace_path, run_metadata={"run_id": "mcp-smoke", "task_id": task.task_id})
    executor = FixtureToolExecutor(default_tool_registry())
    server = MCPFixtureServer(default_tool_registry(), executor=executor, logger=logger)
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")

    response = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {"name": tool_call.tool_name, "arguments": tool_call.arguments},
        },
        sandbox=sandbox,
    )

    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]
    assert json.loads(response["result"]["content"][0]["text"]) == response["result"]["structuredContent"]
    events = load_trace_events(trace_path)
    assert [event.event_type for event in events] == ["tool_call", "tool_result"]
    assert all(event.metadata["integration"] == "mcp" for event in events)
    assert all(event.metadata["mcp_method"] == "tools/call" for event in events)
    assert all(event.metadata["mcp_request_id"] == "call-1" for event in events)
    assert events[0].payload["tool_name"] == tool_call.tool_name


def test_mcp_trace_replay_converts_jsonrpc_tool_exchange_to_harness_trace(tmp_path):
    from sandboxed_agent_eval_harness.integrations.mcp import MCPTraceReplay

    trace_path = tmp_path / "mcp_jsonrpc_exchange.jsonl"
    logger = TraceLogger(trace_path, run_metadata={"run_id": "mcp-replay", "task_id": "fixture-task"})
    request = {
        "jsonrpc": "2.0",
        "id": "call-42",
        "method": "tools/call",
        "params": {
            "name": "transcript.search",
            "arguments": {"ticker": "NVDA", "fiscal_period": "2024-Q4", "query": "data center"},
        },
    }
    response = {
        "jsonrpc": "2.0",
        "id": "call-42",
        "result": {
            "content": [{"type": "text", "text": "{\"matches\": []}"}],
            "structuredContent": {
                "ticker": "NVDA",
                "fiscal_period": "2024-Q4",
                "source": "nvda-2024-q4-transcript-datacenter",
                "matches": [],
            },
            "isError": False,
        },
    }

    summary = MCPTraceReplay.write_trace_from_jsonrpc_exchange([request, response], logger)

    assert summary == {"requests": 1, "responses": 1, "tool_calls": 1, "tool_results": 1}
    events = load_trace_events(trace_path)
    assert [event.event_type for event in events] == ["tool_call", "tool_result"]
    replay = MCPTraceReplay(events)
    assert replay.summary() == {"mcp_tool_calls": 1, "mcp_tool_results": 1, "missing_results": 0}
    assert replay.to_jsonrpc_records()[0]["method"] == "tools/call"
    assert replay.to_jsonrpc_records()[1]["result"]["structuredContent"]["source"] == (
        "nvda-2024-q4-transcript-datacenter"
    )


def test_mcp_fixture_server_rejects_protocol_errors_without_live_network(tmp_path):
    from sandboxed_agent_eval_harness.integrations.mcp import MCPFixtureServer

    server = MCPFixtureServer()

    missing_sandbox = server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "call-without-sandbox",
            "method": "tools/call",
            "params": {"name": "csv.read", "arguments": {"path": "fixtures/data/regional_sales.csv"}},
        }
    )
    unknown_method = server.handle_jsonrpc({"jsonrpc": "2.0", "id": "bad-method", "method": "resources/list"})

    assert missing_sandbox["error"]["code"] == -32000
    assert "sandbox" in missing_sandbox["error"]["message"]
    assert unknown_method["error"]["code"] == -32601
    assert "unsupported MCP method" in unknown_method["error"]["message"]


def test_mcp_integration_is_documented_as_optional_fixture_backed_and_not_default_ci():
    readme = (ROOT / "README.md").read_text()
    makefile = (ROOT / "Makefile").read_text()
    validation = (ROOT / "VALIDATION.md").read_text()

    assert "MCP" in readme
    assert "fixture-backed MCP" in readme
    assert "no live MCP server by default" in readme
    assert "mcp_fixture_trace" in makefile
    assert "ci: test validate-config smoke gate model-study report" in makefile
    assert "MCP optional integration smoke" in validation
