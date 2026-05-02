from pathlib import Path

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.evaluation.runner import main, run_evaluation
from sandboxed_agent_eval_harness.sandbox import (
    DockerSandboxBackend,
    LocalWorkspaceBackend,
    SandboxBackendConfig,
    SandboxCommandResult,
    sandbox_backend_by_name,
)
from sandboxed_agent_eval_harness.tasks import TaskSuite, default_task_suite
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, default_tool_registry


ROOT = Path(__file__).resolve().parents[1]


def test_local_workspace_backend_keeps_existing_sandbox_behavior(tmp_path):
    task = _task("data-sales-region-summary")
    backend = LocalWorkspaceBackend()
    sandbox = backend.create_sandbox(task, tmp_path / "workspace", fixture_root=ROOT)

    assert backend.name == "workspace"
    assert sandbox.read_text("fixtures/data/regional_sales.csv").startswith("region,product,revenue")

    sandbox.write_text("summary_by_region.csv", "region,revenue\nwest,5100\n")
    exported = backend.export_artifacts(sandbox.workspace, tmp_path / "export")

    assert exported == ["fixtures/data/regional_sales.csv", "summary_by_region.csv"]
    assert (tmp_path / "export" / "summary_by_region.csv").read_text() == "region,revenue\nwest,5100\n"


def test_docker_backend_command_disables_network_and_mounts_fixtures_read_only(tmp_path):
    backend = DockerSandboxBackend(
        config=SandboxBackendConfig(
            timeout_seconds=2.5,
            memory_limit="256m",
            cpus="0.5",
            pids_limit=64,
            image="python:3.11-slim",
        ),
        fixture_root=ROOT,
        docker_executable="docker",
    )

    command = backend.command_for_workspace(tmp_path / "workspace", ["python", "-c", "print('ok')"])
    joined = " ".join(command)

    assert backend.name == "docker"
    assert "--network" in command
    assert "none" in command
    assert "--memory" in command
    assert "256m" in command
    assert "--cpus" in command
    assert "0.5" in command
    assert "--pids-limit" in command
    assert "64" in command
    assert "--read-only" in command
    assert "--tmpfs" in command
    assert "target=/fixtures,readonly" in joined
    assert "target=/workspace" in joined
    assert "--network host" not in joined


def test_docker_backend_rejects_network_enabled_configuration():
    try:
        SandboxBackendConfig(network_disabled=False)
    except ValueError as exc:
        assert "network_disabled must remain true" in str(exc)
    else:
        raise AssertionError("Docker sandbox config must not allow network-enabled mode")


def test_docker_backend_runs_coding_unit_test_path_with_injected_command_runner(tmp_path):
    captured = []

    def fake_runner(command, timeout_seconds):
        captured.append((command, timeout_seconds))
        return SandboxCommandResult(
            returncode=0,
            stdout='{"passed": true, "tests_run": 2, "failures": 0}\n',
            stderr="",
        )

    backend = DockerSandboxBackend(
        config=SandboxBackendConfig(timeout_seconds=4, memory_limit="128m", cpus="1.0"),
        fixture_root=ROOT,
        command_runner=fake_runner,
    )
    executor = FixtureToolExecutor(default_tool_registry(), backend=backend)
    sandbox = executor.create_sandbox(_task("coding-discount-total-fix"), tmp_path / "workspace")

    executor.execute(
        "code.patch",
        {
            "path": "fixtures/code/discount.py",
            "replacements": [
                {
                    "old": "return sum(prices) - discount",
                    "new": "return sum(prices) * (1 - discount)",
                }
            ],
        },
        sandbox,
    )
    result = executor.execute("python.unit_tests", {"test_path": "fixtures/code/test_discount.py"}, sandbox)

    assert result == {"passed": True, "tests_run": 2, "failures": 0}
    assert captured
    assert captured[0][1] == 4
    assert "--network" in captured[0][0]
    assert "none" in captured[0][0]


def test_evaluation_runner_accepts_workspace_sandbox_backend(tmp_path):
    summary = run_evaluation(
        suite=_suite_with("data-sales-region-summary", "coding-discount-total-fix"),
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path,
        sandbox_backend_name="workspace",
    )

    assert summary.metrics["task_success_rate"] == 1.0
    assert {run.metrics["sandbox_backend"] for run in summary.runs} == {"workspace"}


def test_evaluation_cli_accepts_workspace_sandbox_backend(tmp_path, capsys):
    exit_code = main(
        [
            "--suite",
            "smoke",
            "--baseline",
            "oracle_tool_selection_agent",
            "--trials",
            "1",
            "--sandbox-backend",
            "workspace",
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runs=8" in output
    assert "sandbox_backend=workspace" in output


def test_sandbox_backend_factory_returns_named_backends():
    assert sandbox_backend_by_name("workspace").name == "workspace"
    assert sandbox_backend_by_name("docker").name == "docker"


def test_docs_describe_docker_backend_without_security_overclaim():
    readme = (ROOT / "README.md").read_text().lower()

    assert "evaluation isolation" in readme
    assert "not a security product" in readme
    assert "secure sandbox" not in readme


def _task(task_id):
    return next(task for task in default_task_suite().tasks if task.task_id == task_id)


def _suite_with(*task_ids):
    tasks = [_task(task_id) for task_id in task_ids]
    full_suite = default_task_suite()
    return TaskSuite(
        suite_id="phase21-focused-suite",
        version=full_suite.version,
        tasks=tasks,
        task_metadata={task.task_id: full_suite.metadata_for(task.task_id) for task in tasks},
    )
