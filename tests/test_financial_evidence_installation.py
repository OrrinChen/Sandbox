"""Ensure the legacy engine can run outside its original repository layout."""

import json
from pathlib import Path

from financial_evidence_engine import demo
from financial_evidence_engine.bundled import RESOURCES
from financial_evidence_engine.cli import main


def test_demo_and_cli_resolve_installed_assets_outside_the_checkout(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("raise AssertionError('unrelated local app')")

    state = demo.load_demo_state()
    assert len(state.case_studies) == 3
    assert len(state.retrieval_methods) == 5
    assert demo.load_demo_state(project_root=tmp_path).case_studies == {}

    assert main(["serve-demo", "--dry-run"]) == 0
    command = json.loads(capsys.readouterr().out)["serve_command"]
    assert Path(command[4]) == Path(demo.__file__).with_name("streamlit_app.py")

    assert main(["build-corpus", "--corpus", "raw"]) == 0
    assert json.loads(capsys.readouterr().out)["chunks"] == 482


def test_packaged_inputs_match_the_preserved_a1_examples():
    original = Path(__file__).resolve().parents[1] / "legacy" / "financial-evidence-engine"
    for bundled in RESOURCES.rglob("*"):
        if bundled.is_file():
            relative = bundled.relative_to(RESOURCES)
            upstream = original / ("tests" if relative.parts[0] == "fixtures" else "") / relative
            assert bundled.read_bytes() == upstream.read_bytes(), relative
