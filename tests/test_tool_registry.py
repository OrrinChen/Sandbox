from pathlib import Path

import pytest

from sandboxed_agent_eval_harness.schemas import SchemaValidationError, ToolSpec
from sandboxed_agent_eval_harness.tools.registry import (
    DuplicateToolError,
    ToolRegistry,
    UnknownToolError,
    default_tool_registry,
    default_tool_specs,
)


ROOT = Path(__file__).resolve().parents[1]


def make_echo_tool(name="fixture.echo"):
    return ToolSpec(
        tool_name=name,
        input_schema={
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        side_effects=[],
        permissions=["read_fixture"],
        state_mutation={},
        failure_modes=["invalid_message"],
    )


def test_registry_looks_up_tool_by_name():
    tool = make_echo_tool()
    registry = ToolRegistry([tool])

    assert registry.get("fixture.echo") == tool
    assert registry.names() == ["fixture.echo"]


def test_registry_rejects_unknown_tool_name():
    registry = ToolRegistry([make_echo_tool()])

    with pytest.raises(UnknownToolError, match="missing.tool"):
        registry.get("missing.tool")


def test_registry_rejects_duplicate_tool_names():
    with pytest.raises(DuplicateToolError, match="fixture.echo"):
        ToolRegistry([make_echo_tool(), make_echo_tool()])


def test_registry_validates_tool_input_before_execution():
    registry = ToolRegistry([make_echo_tool()])

    valid = registry.validate_input("fixture.echo", {"message": "hello"})

    assert valid == {"message": "hello"}
    with pytest.raises(SchemaValidationError, match="message"):
        registry.validate_input("fixture.echo", {"message": 123})


def test_registry_validates_tool_output_after_execution():
    registry = ToolRegistry([make_echo_tool()])

    valid = registry.validate_output("fixture.echo", {"message": "hello"})

    assert valid == {"message": "hello"}
    with pytest.raises(SchemaValidationError, match="message"):
        registry.validate_output("fixture.echo", {})


def test_registry_exposes_permissions_side_effects_and_failure_modes():
    tool = make_echo_tool()
    registry = ToolRegistry([tool])

    metadata = registry.metadata("fixture.echo")

    assert metadata["permissions"] == ["read_fixture"]
    assert metadata["side_effects"] == []
    assert metadata["failure_modes"] == ["invalid_message"]
    assert metadata["state_mutation"] == {}


def test_default_registry_includes_fixture_backed_finance_and_data_tools():
    registry = default_tool_registry()

    assert "financial_statement.lookup" in registry.names()
    assert "transcript.search" in registry.names()
    assert "csv.read" in registry.names()
    assert "csv.group_metrics" in registry.names()
    assert "code.patch" in registry.names()
    assert "python.unit_tests" in registry.names()
    assert "optimization.solve_newsvendor" in registry.names()

    finance = registry.get("financial_statement.lookup")
    data = registry.get("csv.group_metrics")
    code_patch = registry.get("code.patch")
    unit_tests = registry.get("python.unit_tests")
    optimization = registry.get("optimization.solve_newsvendor")

    assert finance.permissions == ["read_fixture"]
    assert finance.side_effects == []
    assert "wrong_fiscal_period" in finance.failure_modes
    assert data.permissions == ["read_visible_files", "write_task_workspace"]
    assert data.side_effects == ["writes_file"]
    assert data.state_mutation == {"writes": ["summary_table"]}
    assert code_patch.permissions == ["read_visible_files", "write_task_workspace"]
    assert code_patch.side_effects == ["modifies_file"]
    assert unit_tests.permissions == ["read_visible_files", "execute_sandboxed_python"]
    assert optimization.permissions == ["read_visible_files", "write_task_workspace"]


def test_default_tool_specs_are_unique_and_validatable():
    specs = default_tool_specs()
    registry = ToolRegistry(specs)

    assert len(registry.names()) == len(specs)
    registry.validate_input(
        "financial_statement.lookup",
        {"ticker": "AAPL", "fiscal_year": 2023, "statement": "income"},
    )
    registry.validate_output(
        "financial_statement.lookup",
        {
            "ticker": "AAPL",
            "fiscal_year": 2023,
            "statement": "income",
            "source": "fixtures/finance/aapl_income_statement.json",
            "values": {"revenue": 383285},
        },
    )
    registry.validate_input(
        "csv.group_metrics",
        {
            "path": "fixtures/data/sales.csv",
            "group_by": "region",
            "metric": "revenue",
            "output_path": "summary.csv",
        },
    )
    registry.validate_input(
        "code.patch",
        {
            "path": "fixtures/code/discount.py",
            "replacements": [{"old": "bad", "new": "good"}],
        },
    )
    registry.validate_input(
        "optimization.solve_newsvendor",
        {
            "path": "fixtures/optimization/newsvendor.json",
            "output_path": "newsvendor_solution.json",
        },
    )


def test_tools_config_declares_default_tool_names():
    tools_config = (ROOT / "configs" / "tools.yaml").read_text()

    for tool in default_tool_specs():
        assert tool.tool_name in tools_config
