from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_is_reviewer_friendly_and_claims_are_precise():
    readme = (ROOT / "README.md").read_text()
    headings = [
        "## Problem",
        "## Architecture",
        "## Quickstart",
        "## Key Result",
        "## Reproducibility",
        "## Limitations",
    ]

    assert len(readme.splitlines()) <= 180
    for heading in headings:
        assert heading in readme
    assert "Final-answer-only grading overestimated validated correctness by 56.2 percentage points" in readme
    assert "deterministic validators caught 180 silent failures" in readme
    assert "64 fixture-backed benchmark tasks" in readme
    assert "5 recorded offline model profiles" in readme
    assert "not a live-provider benchmark" in readme
    assert "not a security product" in readme
    assert "secure sandbox" not in readme.lower()
    assert "## First MVP Target" not in readme
    assert "## Core Schemas" not in readme


def test_interview_docs_exist_and_cover_required_topics():
    required_docs = {
        "docs/interview_notes.md": [
            "Resume bullet",
            "Final-answer-only grading",
            "56.2 percentage points",
            "180 silent failures",
        ],
        "docs/architecture.md": [
            "typed task schema",
            "typed tool registry",
            "JSONL trace",
            "deterministic validators",
            "regression gates",
        ],
        "docs/limitations.md": [
            "recorded offline",
            "fixture-backed",
            "not a live-provider benchmark",
            "not a security product",
        ],
        "docs/failure_case_studies.md": [
            "replayable_failure_01",
            "Trace path",
            "Replay command",
            "Root causes",
        ],
    }

    for relative_path, expected_terms in required_docs.items():
        text = (ROOT / relative_path).read_text()
        assert text.startswith("# ")
        for term in expected_terms:
            assert term in text


def test_roadmap_is_frozen_after_phase24():
    roadmap = (ROOT / "ROADMAP.md").read_text()

    assert "- [x] Phase 24: README, Resume, and Interview Polish Freeze" in roadmap
    assert "Current phase:\n- Maintenance only" in roadmap
    assert "Roadmap status: frozen after Phase 24" in roadmap
    assert "Do not add a web app, dashboard product, generic agent runtime, or unrelated finance ingestion work." in roadmap


def test_validation_and_runbook_include_phase24_checks():
    validation = (ROOT / "VALIDATION.md").read_text()
    runbook = (ROOT / "RUNBOOK.md").read_text()

    assert "README / Resume / Interview Polish Freeze Validation" in validation
    assert "python3 -m pytest tests/test_phase24_portfolio_freeze.py -v" in validation
    assert "docs/interview_notes.md" in validation
    assert "Phase 24 freeze check" in runbook
    assert "make ci" in runbook
