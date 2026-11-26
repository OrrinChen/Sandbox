import json
import os
import subprocess
import sys


def _run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "financial_evidence_engine.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_cli_help_lists_required_commands():
    result = _run_cli("--help")

    assert result.returncode == 0
    for command in (
        "verify-claim",
        "build-corpus",
        "run-eval",
        "build-case-studies",
        "build-report",
        "serve-demo",
    ):
        assert command in result.stdout


def test_verify_claim_cli_returns_support_without_api_key():
    result = _run_cli(
        "verify-claim",
        "--claim",
        "Apple FY2024 revenue was $391.035 billion.",
        "--company",
        "AAPL",
        "--period",
        "2024-FY",
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["command"] == "verify-claim"
    assert payload["verdict"] == "support"
    assert payload["api_key_required"] is False


def test_bad_input_and_missing_pdf_fail_gracefully():
    missing_claim = _run_cli("verify-claim")
    missing_pdf = _run_cli("build-corpus", "--deck-pdf", "missing-investor-deck.pdf")

    assert missing_claim.returncode == 2
    assert "required" in missing_claim.stderr

    payload = json.loads(missing_pdf.stdout)
    assert missing_pdf.returncode == 2
    assert payload["error_code"] == "missing_pdf"
    assert "missing-investor-deck.pdf" in payload["message"]
    assert "Traceback" not in missing_pdf.stderr


def test_production_profile_and_helpers_are_offline_and_traceable(tmp_path):
    from financial_evidence_engine.production import (
        CONFIG_PROFILES,
        check_data_provenance,
        plan_cache_invalidation,
        version_artifact,
    )

    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"ok": true}\n')

    version = version_artifact(artifact)
    provenance = check_data_provenance((artifact,))
    invalidation = plan_cache_invalidation((artifact,), reason="test")

    assert CONFIG_PROFILES["local"].network_enabled is False
    assert len(version.content_hash) == 64
    assert provenance[0].status == "pass"
    assert invalidation[0].would_delete is False


def test_cli_smoke_script_covers_phase19_commands():
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "scripts/smoke_cli_workflow.py"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "commands=6" in result.stdout
    assert "verify_verdict=support" in result.stdout
    assert "network_enabled=False" in result.stdout
