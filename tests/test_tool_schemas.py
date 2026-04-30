import pytest

from sandboxed_agent_eval_harness.schemas import (
    SchemaValidationError,
    TaskSpec,
    ToolSpec,
)


def test_task_spec_round_trips_to_plain_dict():
    task = TaskSpec(
        task_id="finance-revenue-yoy",
        domain="finance",
        instruction="Compare FY2023 and FY2022 revenue from fixture data.",
        available_tools=["financial_statement.lookup"],
        initial_state={"workspace": "runs/finance-revenue-yoy"},
        hidden_expected_state={"revenue_yoy_pct": 7.8},
        visible_files=["fixtures/aapl_income_statement.json"],
        success_criteria=["uses annual revenue", "cites fixture source"],
        validator_list=["numeric", "citation"],
        max_turns=6,
        max_cost=0.25,
        timeout_seconds=30,
    )

    serialized = task.to_dict()
    restored = TaskSpec.from_dict(serialized)

    assert restored == task
    assert serialized["task_id"] == "finance-revenue-yoy"
    assert serialized["available_tools"] == ["financial_statement.lookup"]
    assert serialized["hidden_expected_state"] == {"revenue_yoy_pct": 7.8}


def test_task_spec_rejects_missing_required_fields():
    payload = {
        "domain": "finance",
        "instruction": "Compare revenue.",
        "available_tools": ["financial_statement.lookup"],
        "initial_state": {},
        "hidden_expected_state": {},
        "visible_files": [],
        "success_criteria": ["numeric value matches"],
        "validator_list": ["numeric"],
        "max_turns": 3,
        "max_cost": 0.1,
        "timeout_seconds": 10,
    }

    with pytest.raises(SchemaValidationError, match="task_id"):
        TaskSpec.from_dict(payload)


def test_task_spec_rejects_invalid_limits():
    with pytest.raises(SchemaValidationError, match="max_turns"):
        TaskSpec(
            task_id="bad-task",
            domain="data_analysis",
            instruction="Compute grouped metrics.",
            available_tools=["csv.read"],
            initial_state={},
            hidden_expected_state={},
            visible_files=[],
            success_criteria=["writes output file"],
            validator_list=["schema"],
            max_turns=0,
            max_cost=0.1,
            timeout_seconds=10,
        )


def test_tool_spec_validates_inputs_and_outputs_deterministically():
    tool = ToolSpec(
        tool_name="csv.group_metrics",
        input_schema={
            "type": "object",
            "required": ["path", "group_by", "metric"],
            "properties": {
                "path": {"type": "string"},
                "group_by": {"type": "string"},
                "metric": {"type": "string"},
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
        state_mutation={"writes": ["summary.csv"]},
        failure_modes=["missing_column", "invalid_csv"],
    )

    arguments = tool.validate_input(
        {
            "path": "fixtures/sales.csv",
            "group_by": "region",
            "metric": "revenue",
            "drop_missing": True,
        }
    )
    result = tool.validate_output({"rows": 4, "output_path": "summary.csv"})

    assert arguments["group_by"] == "region"
    assert result["rows"] == 4
    assert tool.to_dict()["tool_name"] == "csv.group_metrics"
    assert ToolSpec.from_dict(tool.to_dict()) == tool


def test_tool_spec_rejects_missing_required_argument():
    tool = ToolSpec(
        tool_name="financial_statement.lookup",
        input_schema={
            "type": "object",
            "required": ["ticker", "fiscal_year"],
            "properties": {
                "ticker": {"type": "string"},
                "fiscal_year": {"type": "integer"},
            },
        },
        output_schema={"type": "object", "required": [], "properties": {}},
        side_effects=[],
        permissions=["read_fixture"],
        state_mutation={},
        failure_modes=["missing_ticker"],
    )

    with pytest.raises(SchemaValidationError, match="fiscal_year"):
        tool.validate_input({"ticker": "AAPL"})


def test_tool_spec_rejects_argument_type_mismatch():
    tool = ToolSpec(
        tool_name="financial_statement.lookup",
        input_schema={
            "type": "object",
            "required": ["ticker", "fiscal_year"],
            "properties": {
                "ticker": {"type": "string"},
                "fiscal_year": {"type": "integer"},
            },
        },
        output_schema={"type": "object", "required": [], "properties": {}},
        side_effects=[],
        permissions=["read_fixture"],
        state_mutation={},
        failure_modes=["invalid_type"],
    )

    with pytest.raises(SchemaValidationError, match="fiscal_year"):
        tool.validate_input({"ticker": "AAPL", "fiscal_year": "2023"})


def test_tool_spec_rejects_non_object_arguments_deterministically():
    tool = ToolSpec(
        tool_name="financial_statement.lookup",
        input_schema={
            "type": "object",
            "required": ["ticker"],
            "properties": {"ticker": {"type": "string"}},
        },
        output_schema={"type": "object", "required": [], "properties": {}},
        side_effects=[],
        permissions=["read_fixture"],
        state_mutation={},
        failure_modes=["invalid_arguments"],
    )

    with pytest.raises(SchemaValidationError, match="input"):
        tool.validate_input(None)
