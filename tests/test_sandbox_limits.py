import time
from pathlib import Path

import pytest

from sandboxed_agent_eval_harness.schemas import TraceEvent
from sandboxed_agent_eval_harness.sandbox import (
    FileSystemSandbox,
    SandboxPathError,
    SandboxTimeoutError,
    run_python_subprocess,
)


def test_filesystem_sandbox_allows_only_workspace_relative_paths(tmp_path):
    sandbox = FileSystemSandbox(tmp_path / "workspace")
    outside = tmp_path / "outside.txt"
    outside.write_text("do not change")

    sandbox.write_text("outputs/result.txt", "ok")

    assert sandbox.read_text("outputs/result.txt") == "ok"
    assert (sandbox.workspace / "outputs" / "result.txt").read_text() == "ok"
    with pytest.raises(SandboxPathError, match="outside workspace"):
        sandbox.write_text("../outside.txt", "changed")
    with pytest.raises(SandboxPathError, match="absolute"):
        sandbox.read_text(str(outside))
    assert outside.read_text() == "do not change"


def test_filesystem_sandbox_resets_to_initial_state(tmp_path):
    sandbox = FileSystemSandbox(
        tmp_path / "workspace",
        initial_files={
            "input/data.csv": "region,revenue\nwest,10\n",
            "notes.txt": "initial",
        },
    )

    sandbox.write_text("input/data.csv", "region,revenue\nwest,99\n")
    sandbox.write_text("outputs/summary.csv", "region,total\nwest,99\n")
    sandbox.delete("notes.txt")

    sandbox.reset()

    assert sandbox.read_text("input/data.csv") == "region,revenue\nwest,10\n"
    assert sandbox.read_text("notes.txt") == "initial"
    assert not (sandbox.workspace / "outputs" / "summary.csv").exists()


def test_filesystem_sandbox_enforces_read_allowlist(tmp_path):
    sandbox = FileSystemSandbox(
        tmp_path / "workspace",
        initial_files={
            "visible/input.csv": "ok",
            "hidden/answer.txt": "secret",
        },
        readable_paths=["visible"],
    )

    assert sandbox.read_text("visible/input.csv") == "ok"
    with pytest.raises(SandboxPathError, match="allowlist"):
        sandbox.read_text("hidden/answer.txt")


def test_state_diff_tracks_added_modified_and_deleted_files(tmp_path):
    sandbox = FileSystemSandbox(
        tmp_path / "workspace",
        initial_files={
            "input.csv": "a,b\n1,2\n",
            "delete_me.txt": "remove",
        },
    )
    before = sandbox.snapshot()

    sandbox.write_text("input.csv", "a,b\n1,3\n")
    sandbox.write_text("new/output.txt", "created")
    sandbox.delete("delete_me.txt")
    diff = before.diff(sandbox.snapshot())

    assert diff.added == ["new/output.txt"]
    assert diff.modified == ["input.csv"]
    assert diff.deleted == ["delete_me.txt"]
    assert diff.to_dict() == {
        "added": ["new/output.txt"],
        "modified": ["input.csv"],
        "deleted": ["delete_me.txt"],
    }


def test_state_diff_can_be_attached_to_trace_event(tmp_path):
    sandbox = FileSystemSandbox(tmp_path / "workspace", initial_files={"input.csv": "a,b\n1,2\n"})
    before = sandbox.snapshot()
    sandbox.write_text("output.csv", "total\n3\n")
    diff = before.diff(sandbox.snapshot())

    event = TraceEvent(
        event_id="evt-state-diff",
        event_type="state_diff",
        sequence=2,
        payload=diff.to_dict(),
    )

    assert TraceEvent.from_json_line(event.to_json_line()) == event


def test_python_subprocess_runs_in_workspace(tmp_path):
    sandbox = FileSystemSandbox(tmp_path / "workspace")

    result = run_python_subprocess(
        "from pathlib import Path\nPath('answer.txt').write_text('42')\nprint('ok')",
        workspace=sandbox.workspace,
        timeout_seconds=2,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    assert sandbox.read_text("answer.txt") == "42"


def test_python_subprocess_timeout_is_enforced(tmp_path):
    sandbox = FileSystemSandbox(tmp_path / "workspace")
    started = time.monotonic()

    with pytest.raises(SandboxTimeoutError, match="timed out"):
        run_python_subprocess(
            "import time\ntime.sleep(2)",
            workspace=sandbox.workspace,
            timeout_seconds=0.1,
        )

    assert time.monotonic() - started < 1


def test_sandbox_config_documents_task_workspace_mode():
    config = Path("configs/sandbox.yaml").read_text()

    assert "task_workspace_only" in config
    assert "default_seconds" in config
