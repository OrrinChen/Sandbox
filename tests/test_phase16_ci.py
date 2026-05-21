from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_makefile_declares_reproducibility_targets():
    makefile = (ROOT / "Makefile").read_text()

    for target in ["test", "smoke", "gate", "model-study", "report", "ci"]:
        assert f"{target}:" in makefile

    assert "-m pytest" in makefile
    assert "sandboxed_agent_eval_harness.evaluation.runner" in makefile
    assert "sandboxed_agent_eval_harness.evaluation.gates" in makefile
    assert "sandboxed_agent_eval_harness.evaluation.model_study" in makefile
    assert "sandboxed_agent_eval_harness.evaluation.report" in makefile
    assert "OPENAI_API_KEY" not in makefile
    assert "--live" not in makefile


def test_github_actions_ci_uses_repo_root_and_no_live_credentials():
    workflow = (ROOT / ".github" / "workflows" / "sandboxed-agent-eval-harness-ci.yml").read_text()

    assert "working-directory: sandboxed-agent-eval-harness" not in workflow
    assert "make ci" in workflow
    assert "actions/checkout@" in workflow
    assert "actions/setup-python@" in workflow
    assert "upload-artifact" in workflow
    assert "path: artifacts/" in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "--live" not in workflow


def test_docs_do_not_reference_old_parent_workspace_working_directory():
    stale_snippet = "working-directory: sandboxed-agent-eval-harness"
    docs = [
        ROOT / "AGENTS.md",
        ROOT / "ROADMAP.md",
        ROOT / "RUNBOOK.md",
        ROOT / "TASK_MEMORY.md",
        ROOT / "VALIDATION.md",
    ]

    for path in docs:
        assert stale_snippet not in path.read_text()


def test_artifact_outputs_are_ignored_by_default():
    gitignore = (ROOT / ".gitignore").read_text()

    assert "artifacts/" in gitignore
