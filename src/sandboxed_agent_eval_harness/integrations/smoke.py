"""Credential-free smoke command for optional integration adapters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.integrations.langchain_tools import LangChainToolAdapter
from sandboxed_agent_eval_harness.integrations.langgraph_runner import LangGraphRunner
from sandboxed_agent_eval_harness.integrations.langsmith_exporter import LangSmithTraceExporter
from sandboxed_agent_eval_harness.integrations.mcp import MCPFixtureServer
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, default_tool_registry
from sandboxed_agent_eval_harness.tracing import TraceLogger


def run_optional_integrations_smoke(output_dir: Path | str = "artifacts/integrations") -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    task = default_task_suite().tasks[0]
    registry = default_tool_registry()
    executor = FixtureToolExecutor(registry)

    langchain_dir = output_path / "langchain"
    langchain_dir.mkdir(parents=True, exist_ok=True)
    descriptors_path = langchain_dir / "tool_descriptors.json"
    trace_path = langchain_dir / "tool_adapter_trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    sandbox = executor.create_sandbox(task, langchain_dir / "workspace")
    logger = TraceLogger(trace_path, run_metadata={"run_id": "optional-langchain-smoke", "task_id": task.task_id})
    adapter = LangChainToolAdapter(registry, executor=executor, logger=logger)
    descriptors = adapter.tool_descriptors()
    plan = OracleToolSelectionAgent().run(task)
    first_tool_call = plan.tool_calls[0]
    adapter.invoke_tool(first_tool_call.tool_name, first_tool_call.arguments, sandbox=sandbox)
    descriptors_path.write_text(json.dumps(descriptors, indent=2, sort_keys=True) + "\n")

    mcp_dir = output_path / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    mcp_trace_path = mcp_dir / "fixture_tool_trace.jsonl"
    if mcp_trace_path.exists():
        mcp_trace_path.unlink()
    mcp_logger = TraceLogger(mcp_trace_path, run_metadata={"run_id": "optional-mcp-smoke", "task_id": task.task_id})
    mcp_server = MCPFixtureServer(registry, executor=executor, logger=mcp_logger)
    mcp_sandbox = executor.create_sandbox(task, mcp_dir / "workspace")
    mcp_tools_response = mcp_server.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": "tools-list", "method": "tools/list", "params": {}}
    )
    (mcp_dir / "tool_descriptors.json").write_text(
        json.dumps(mcp_tools_response["result"]["tools"], indent=2, sort_keys=True) + "\n"
    )
    mcp_server.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "fixture-call",
            "method": "tools/call",
            "params": {"name": first_tool_call.tool_name, "arguments": first_tool_call.arguments},
        },
        sandbox=mcp_sandbox,
    )

    graph_result = LangGraphRunner(registry=registry, executor=executor).run(
        task=task,
        baseline=OracleToolSelectionAgent(),
        output_dir=output_path / "langgraph",
    )
    export_result = LangSmithTraceExporter().export(
        [graph_result.trace_path],
        output_path=output_path / "langsmith" / "local_trace_export.jsonl",
        upload=False,
    )
    return {
        "langchain_tools": str(len(descriptors)),
        "langchain_trace": str(trace_path),
        "mcp_tools": str(len(mcp_tools_response["result"]["tools"])),
        "mcp_fixture_trace": str(mcp_trace_path),
        "langgraph_trace": str(graph_result.trace_path),
        "langsmith_export": str(export_result.output_path),
        "upload": "disabled",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run optional integration adapter smoke checks.")
    parser.add_argument("--output-dir", default="artifacts/integrations")
    args = parser.parse_args(argv)

    result = run_optional_integrations_smoke(args.output_dir)
    print(
        f"langchain_tools={result['langchain_tools']} "
        f"mcp_tools={result['mcp_tools']} "
        f"mcp_fixture_trace={result['mcp_fixture_trace']} "
        f"langgraph_trace={result['langgraph_trace']} "
        f"langsmith_export={result['langsmith_export']} "
        f"upload={result['upload']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
