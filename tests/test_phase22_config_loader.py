from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sandboxed_agent_eval_harness.agents import default_agent_baselines
from sandboxed_agent_eval_harness.config import (
    ProjectConfigValidationError,
    default_config_dir,
    load_eval_runs_config,
    load_task_suites_config,
    load_tools_config,
    load_validators_config,
    validate_project_config,
)
from sandboxed_agent_eval_harness.config.validate import main as validate_config_main
from sandboxed_agent_eval_harness.tasks import benchmark_task_suite, default_task_suite
from sandboxed_agent_eval_harness.tools import default_tool_registry
from sandboxed_agent_eval_harness.validators import default_validator_names


ROOT = Path(__file__).resolve().parents[1]


def test_config_loaders_match_runtime_surfaces():
    tools_config = load_tools_config()
    validators_config = load_validators_config()
    task_suites_config = load_task_suites_config()
    eval_runs_config = load_eval_runs_config()

    assert tools_config.names() == default_tool_registry().names()
    assert validators_config.names() == default_validator_names()
    assert task_suites_config.manifest_paths() == [
        Path("fixtures/tasks/initial_suite.json"),
        Path("fixtures/tasks/benchmark_suite.json"),
    ]
    assert task_suites_config.task_ids_for("initial-fixture-suite") == default_task_suite().task_ids()
    assert task_suites_config.task_ids_for("benchmark-fixture-suite") == benchmark_task_suite().task_ids()

    smoke = eval_runs_config.get("smoke")
    assert smoke.suite == "initial-fixture-suite"
    assert smoke.trials_per_task == 1
    assert smoke.baselines == [baseline.name for baseline in default_agent_baselines()]
    assert "task_success_rate" in smoke.metrics
    assert "pass_at_k" in smoke.metrics


def test_validate_project_config_returns_machine_readable_summary():
    report = validate_project_config()

    assert report.passed is True
    assert report.config_dir == default_config_dir()
    assert report.to_dict()["tool_count"] == len(default_tool_registry().names())
    assert report.to_dict()["validator_count"] == len(default_validator_names())
    assert report.to_dict()["task_suite_count"] == 2
    assert report.to_dict()["eval_run_count"] == 1


def test_bad_config_fails_deterministically(tmp_path: Path):
    config_dir = tmp_path / "configs"
    shutil.copytree(ROOT / "configs", config_dir)
    tools_path = config_dir / "tools.yaml"
    tools_path.write_text(tools_path.read_text().replace("  - tool_name: csv.read", "  - tool_name: csv.typo"))

    with pytest.raises(ProjectConfigValidationError, match="tools config names do not match runtime defaults"):
        validate_project_config(config_dir=config_dir)


def test_validate_config_cli_reports_success(capsys):
    exit_code = validate_config_main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "config_validation=passed" in captured.out
    assert "tools=7" in captured.out
    assert "task_suites=2" in captured.out


def test_makefile_includes_validate_config_in_ci():
    makefile = (ROOT / "Makefile").read_text()

    assert ".PHONY:" in makefile
    for target in ["test", "smoke", "gate", "model-study", "report", "validate-config", "ci"]:
        assert target in makefile
    assert "validate-config:" in makefile
    assert "config.validate" in makefile
    assert "ci: test validate-config smoke gate model-study report" in makefile
