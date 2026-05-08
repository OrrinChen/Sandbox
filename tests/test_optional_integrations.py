from __future__ import annotations

import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tracing import load_trace_events


ROOT = Path(__file__).resolve().parents[1]


def test_optional_dependency_guard_reports_install_hint():
    from sandboxed_agent_eval_harness.integrations.common import (
        IntegrationUnavailableError,
        require_optional_dependency,
    )

    with pytest.raises(IntegrationUnavailableError) as exc_info:
        require_optional_dependency(
            "definitely_missing_langchain_module_for_harness_tests",
            extra="ai-integrations",
        )

    assert "optional integration dependency" in str(exc_info.value)
    assert ".[ai-integrations]" in str(exc_info.value)


def test_langchain_tool_adapter_describes_and_executes_fixture_tool(tmp_path):
    from sandboxed_agent_eval_harness.integrations.langchain_tools import LangChainToolAdapter
    from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, default_tool_registry
    from sandboxed_agent_eval_harness.tracing import TraceLogger

    task = default_task_suite().tasks[0]
    plan = OracleToolSelectionAgent().run(task)
    tool_call = plan.tool_calls[0]
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")
    trace_path = tmp_path / "langchain_tool_adapter.jsonl"
    logger = TraceLogger(trace_path, run_metadata={"run_id": "lc-adapter-smoke", "task_id": task.task_id})

    adapter = LangChainToolAdapter(default_tool_registry(), executor=executor, logger=logger)
    descriptors = adapter.tool_descriptors()
    result = adapter.invoke_tool(tool_call.tool_name, tool_call.arguments, sandbox=sandbox)

    assert {descriptor["tool_name"] for descriptor in descriptors} == set(default_tool_registry().names())
    assert result
    events = load_trace_events(trace_path)
    assert [event.event_type for event in events] == ["tool_call", "tool_result"]
    assert events[0].metadata["integration"] == "langchain"
    assert events[0].payload["tool_name"] == tool_call.tool_name


def test_langgraph_runner_emits_node_transition_trace_and_validators(tmp_path):
    from sandboxed_agent_eval_harness.integrations.langgraph_runner import LangGraphRunner

    task = default_task_suite().tasks[0]
    result = LangGraphRunner().run(
        task=task,
        baseline=OracleToolSelectionAgent(),
        output_dir=tmp_path / "langgraph",
    )

    assert result.passed is True
    assert result.backend == "local"
    assert result.metrics["stategraph_compiled"] is False
    assert result.checkpoint_path.is_file()
    events = load_trace_events(result.trace_path)
    graph_nodes = [
        event.payload["node"]
        for event in events
        if event.event_type == "graph_node"
    ]
    assert graph_nodes == ["plan", "tool_call", "tool_result", "validate", "retry_or_finish"]
    assert any(event.event_type == "validator_result" for event in events)
    assert all(event.metadata.get("integration") == "langgraph_style" for event in events)


def test_langgraph_backend_requires_optional_dependency_when_missing(tmp_path):
    from sandboxed_agent_eval_harness.integrations.common import IntegrationUnavailableError
    from sandboxed_agent_eval_harness.integrations.langgraph_runner import LangGraphRunner

    task = default_task_suite().tasks[0]
    with pytest.raises(IntegrationUnavailableError) as exc_info:
        LangGraphRunner(backend="langgraph").run(
            task=task,
            baseline=OracleToolSelectionAgent(),
            output_dir=tmp_path / "langgraph",
        )

    assert "langgraph.graph" in str(exc_info.value)
    assert ".[ai-integrations]" in str(exc_info.value)


def test_langgraph_backend_builds_compiled_stategraph_with_thread_checkpoint(tmp_path, monkeypatch):
    from sandboxed_agent_eval_harness.integrations.langgraph_runner import LangGraphRunner

    fake_graph = _FakeLangGraphModule()
    fake_memory = _FakeLangGraphMemoryModule()
    monkeypatch.setitem(sys.modules, "langgraph", ModuleType("langgraph"))
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_graph)
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint", ModuleType("langgraph.checkpoint"))
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.memory", fake_memory)

    task = default_task_suite().tasks[0]
    result = LangGraphRunner(backend="langgraph").run(
        task=task,
        baseline=OracleToolSelectionAgent(),
        output_dir=tmp_path / "compiled-langgraph",
    )

    assert result.passed is True
    assert result.backend == "langgraph"
    assert result.metrics["stategraph_compiled"] is True
    assert result.metrics["thread_id"] == result.run_id
    assert result.metrics["state_history_count"] == 5
    assert fake_graph.created_graphs
    builder = fake_graph.created_graphs[0]
    assert builder.state_schema_name == "HarnessGraphState"
    assert set(builder.nodes) == {"plan", "tool_call", "tool_result", "validate", "retry_or_finish"}
    assert ("START", "plan") in builder.edges
    assert ("plan", "tool_call") in builder.edges
    assert ("tool_call", "tool_result") in builder.edges
    assert ("tool_result", "validate") in builder.edges
    assert ("validate", "retry_or_finish") in builder.edges
    assert builder.conditional_edges["retry_or_finish"]["path_map"] == {"finish": "END"}
    assert builder.compiled_with_checkpointer is fake_memory.created_savers[0]
    assert builder.compiled_graph.invoke_config == {"configurable": {"thread_id": result.run_id}}
    checkpoint = json.loads(result.checkpoint_path.read_text())
    assert checkpoint["stategraph_compiled"] is True
    assert checkpoint["state_history_count"] == 5
    events = load_trace_events(result.trace_path)
    assert any(event.metadata.get("stategraph_compiled") is True for event in events)
    assert [event.payload["node"] for event in events if event.event_type == "graph_node"] == [
        "plan",
        "tool_call",
        "tool_result",
        "validate",
        "retry_or_finish",
    ]


def test_langsmith_exporter_writes_local_export_and_does_not_upload_by_default(tmp_path, monkeypatch):
    from sandboxed_agent_eval_harness.integrations.langgraph_runner import LangGraphRunner
    from sandboxed_agent_eval_harness.integrations.langsmith_exporter import LangSmithTraceExporter

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    task = default_task_suite().tasks[0]
    graph_result = LangGraphRunner().run(
        task=task,
        baseline=OracleToolSelectionAgent(),
        output_dir=tmp_path / "langgraph",
    )
    export_path = tmp_path / "langsmith" / "local_trace_export.jsonl"

    export_result = LangSmithTraceExporter().export(
        [graph_result.trace_path],
        output_path=export_path,
        upload=False,
    )

    assert export_result.status == "local_exported"
    assert export_result.uploaded is False
    assert export_result.output_path == export_path
    records = [json.loads(line) for line in export_path.read_text().splitlines()]
    assert records
    assert records[0]["exporter"] == "langsmith"
    assert records[0]["upload_enabled"] is False


def test_optional_integration_makefile_and_extras_are_not_default_ci():
    makefile = (ROOT / "Makefile").read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert "optional-integrations-smoke:" in makefile
    assert "sandboxed_agent_eval_harness.integrations.smoke" in makefile
    assert "ci: test validate-config smoke gate model-study report" in makefile
    assert "ai-integrations" in pyproject
    assert "langchain" in pyproject
    assert "langgraph" in pyproject
    assert "langsmith" in pyproject


class _FakeLangGraphModule(ModuleType):
    START = "START"
    END = "END"

    def __init__(self) -> None:
        super().__init__("langgraph.graph")
        self.created_graphs = []

    def StateGraph(self, state_schema):
        graph = _FakeStateGraph(state_schema)
        self.created_graphs.append(graph)
        return graph


class _FakeStateGraph:
    def __init__(self, state_schema) -> None:
        self.state_schema_name = state_schema.__name__
        self.nodes = {}
        self.edges = []
        self.conditional_edges = {}
        self.compiled_with_checkpointer = None
        self.compiled_graph = None

    def add_node(self, name, func):
        self.nodes[name] = func

    def add_edge(self, source, target):
        self.edges.append((source, target))

    def add_conditional_edges(self, source, path, path_map):
        self.conditional_edges[source] = {"path": path, "path_map": dict(path_map)}

    def compile(self, checkpointer=None):
        self.compiled_with_checkpointer = checkpointer
        self.compiled_graph = _FakeCompiledGraph(self)
        return self.compiled_graph


class _FakeCompiledGraph:
    def __init__(self, builder) -> None:
        self.builder = builder
        self.invoke_config = None

    def invoke(self, state, config=None):
        self.invoke_config = config
        current = dict(state)
        for node in ["plan", "tool_call", "tool_result", "validate", "retry_or_finish"]:
            current.update(self.builder.nodes[node](current))
        return current

    def get_state_history(self, config):
        return list(range(5))


class _FakeLangGraphMemoryModule(ModuleType):
    def __init__(self) -> None:
        super().__init__("langgraph.checkpoint.memory")
        self.created_savers = []

    def InMemorySaver(self):
        saver = object()
        self.created_savers.append(saver)
        return saver
