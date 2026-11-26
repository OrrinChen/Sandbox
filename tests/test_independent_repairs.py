"""Regression checks for required exception text and Boolean object identity."""

import platform
import shutil

import pytest

from sandboxed_agent_eval_harness.benchmarks.independent import repairs

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin" and not shutil.which("bwrap"),
    reason="Execution requires the submission sandbox",
)


@pytest.mark.parametrize(
    "task_id,change",
    [
        ("repair-wordy", lambda s: s.replace("syntax error", "other error")),
        (
            "repair-leap",
            lambda s: (
                s
                + "\noriginal = leap_year\ndef leap_year(year):\n    return int(original(year))\n"
            ),
        ),
    ],
)
def test_submission_must_preserve_observable_contract(task_id, change):
    reference = repairs.run_reference(task_id)
    assert repairs.grade(task_id, reference)
    assert not repairs.grade(task_id, change(reference))


def test_diagnostics_do_not_change_observed_return_value():
    assert repairs.invoke(
        "def f():\n    print('trace')\n    return 3\n",
        ["from subject import f\nanswer = f()"],
    ) == [["value", 3]]


def test_submission_cannot_read_scorer_labels_or_bind_a_socket():
    code = """import socket

def denied(path):
    try:
        open(path, 'rb')
    except (FileNotFoundError, PermissionError):
        pass
    else:
        return False
    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.settimeout(0.2)
            sock.connect(('192.0.2.1', 9))
    except OSError:
        return True
    return False
"""
    probe = f"from subject import denied\nanswer = denied({str(repairs.DATA / 'repair_keys.json')!r})"
    assert repairs.invoke(code, [probe]) == [["value", True]]


def test_linux_hides_system_wide_install_under_a_read_only_runtime_mount(
    monkeypatch, tmp_path
):
    package = repairs.Path(
        "/usr/local/lib/python3/site-packages/sandboxed_agent_eval_harness"
    )
    monkeypatch.setattr(repairs, "PACKAGE", package)
    monkeypatch.setattr(repairs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(repairs.shutil, "which", lambda _: "/usr/bin/bwrap")
    cmd = repairs.isolated_command(tmp_path)
    assert cmd[cmd.index("--tmpfs") + 1] == str(package)
