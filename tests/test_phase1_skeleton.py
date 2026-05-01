from pathlib import Path
import importlib


ROOT = Path(__file__).resolve().parents[1]


def test_package_imports_and_exposes_version():
    package = importlib.import_module("sandboxed_agent_eval_harness")

    assert package.__version__ == "0.1.0"


def test_pyproject_declares_phase1_package_metadata():
    pyproject = (ROOT / "pyproject.toml").read_text()

    assert 'name = "sandboxed-agent-eval-harness"' in pyproject
    assert 'version = "0.1.0"' in pyproject
    assert 'sandboxed-agent-eval = "sandboxed_agent_eval_harness.cli:main"' in pyproject
    assert 'testpaths = ["tests"]' in pyproject


def test_config_stubs_exist_and_include_current_domains():
    config_dir = ROOT / "configs"
    expected_files = {
        "models.yaml",
        "tools.yaml",
        "sandbox.yaml",
        "task_suites.yaml",
        "validators.yaml",
        "eval_runs.yaml",
    }

    assert {path.name for path in config_dir.glob("*.yaml")} == expected_files

    task_suites = (config_dir / "task_suites.yaml").read_text()
    assert "finance" in task_suites
    assert "data_analysis" in task_suites
    assert "optimization" in task_suites
    assert "coding" in task_suites


def test_phase1_package_layout_exists():
    package_root = ROOT / "src" / "sandboxed_agent_eval_harness"
    expected_packages = {
        "agents",
        "tools",
        "sandbox",
        "tasks",
        "validators",
        "tracing",
        "evaluation",
        "dashboard",
    }

    assert (package_root / "__init__.py").is_file()
    for package_name in expected_packages:
        assert (package_root / package_name / "__init__.py").is_file()


def test_phase1_cli_stub_reports_package_version(capsys):
    from sandboxed_agent_eval_harness.cli import main

    exit_code = main()

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "sandboxed-agent-eval-harness 0.1.0"
