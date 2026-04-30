import json
from pathlib import Path

import pytest

from sandboxed_agent_eval_harness.schemas import TaskSpec
from sandboxed_agent_eval_harness.tasks import (
    TaskSuiteValidationError,
    default_task_suite,
    load_task_suite,
)
from sandboxed_agent_eval_harness.tools import default_tool_registry
from sandboxed_agent_eval_harness.validators import default_validator_names


ROOT = Path(__file__).resolve().parents[1]


def test_default_task_suite_has_initial_finance_and_data_tasks():
    suite = default_task_suite()

    assert suite.suite_id == "initial-fixture-suite"
    assert suite.version == "tasks-v1"
    assert len(suite.tasks) == 6
    assert len(suite.tasks_by_domain("finance")) == 3
    assert len(suite.tasks_by_domain("data_analysis")) == 3
    assert len(suite.task_ids()) == len(set(suite.task_ids()))
    assert all(isinstance(task, TaskSpec) for task in suite.tasks)


def test_initial_tasks_are_deterministic_and_validator_mapped():
    suite = default_task_suite()
    allowed_tools = set(default_tool_registry().names())
    allowed_validators = set(default_validator_names())

    for task in suite.tasks:
        metadata = suite.metadata_for(task.task_id)

        assert task.max_cost == 0.0
        assert task.hidden_expected_state
        assert set(task.available_tools).issubset(allowed_tools)
        assert set(task.validator_list).issubset(allowed_validators)
        assert "schema" in task.validator_list
        assert metadata["gold_outputs"]
        assert metadata["known_failure_traps"]
        assert metadata["final_answer_only_risk"] is True
        for relative_path in metadata["fixture_paths"]:
            assert (ROOT / relative_path).is_file()
        for relative_path in task.visible_files:
            assert (ROOT / relative_path).is_file()


def test_finance_tasks_are_fixture_backed_with_numeric_or_citation_gold():
    finance_tasks = default_task_suite().tasks_by_domain("finance")

    for task in finance_tasks:
        metadata = default_task_suite().metadata_for(task.task_id)

        assert task.available_tools
        assert any(tool in task.available_tools for tool in ["financial_statement.lookup", "transcript.search"])
        assert "numeric" in task.validator_list or "citation" in task.validator_list
        assert metadata["gold_outputs"].get("metrics") or metadata["gold_outputs"].get("citations")


def test_data_analysis_tasks_include_visible_csv_inputs_and_gold_files_or_metrics():
    data_tasks = default_task_suite().tasks_by_domain("data_analysis")

    for task in data_tasks:
        metadata = default_task_suite().metadata_for(task.task_id)

        assert task.visible_files
        assert all(path.endswith(".csv") for path in task.visible_files)
        assert any(tool.startswith("csv.") for tool in task.available_tools)
        assert "state" in task.validator_list or "numeric" in task.validator_list
        assert metadata["gold_outputs"].get("files") or metadata["gold_outputs"].get("metrics")


def test_load_task_suite_rejects_missing_hidden_expected_state(tmp_path):
    manifest = {
        "suite_id": "bad-suite",
        "version": "tasks-v1",
        "tasks": [
            {
                "task_id": "bad-task",
                "domain": "finance",
                "instruction": "Bad task.",
                "available_tools": ["financial_statement.lookup"],
                "initial_state": {},
                "visible_files": [],
                "success_criteria": ["Should fail before use."],
                "validator_list": ["schema"],
                "max_turns": 1,
                "max_cost": 0.0,
                "timeout_seconds": 10,
                "fixture_paths": [],
                "gold_outputs": {},
                "known_failure_traps": ["missing hidden state"],
                "final_answer_only_risk": True,
            }
        ],
    }
    manifest_path = tmp_path / "bad_suite.json"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(TaskSuiteValidationError, match="hidden_expected_state"):
        load_task_suite(manifest_path)


def test_task_suites_config_declares_initial_suite_and_task_ids():
    config_text = (ROOT / "configs" / "task_suites.yaml").read_text()
    suite = default_task_suite()

    assert suite.suite_id in config_text
    for task_id in suite.task_ids():
        assert task_id in config_text
