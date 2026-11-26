from pathlib import Path
import subprocess
import sys


DOCS = (
    "docs/interview_story.md",
    "docs/sixty_second_pitch.md",
    "docs/resume_bullets.md",
    "docs/system_design_notes.md",
    "docs/failure_modes.md",
    "docs/demo_script.md",
)


def test_interview_packaging_docs_exist_and_frame_project_correctly():
    for path in DOCS:
        assert Path(path).exists(), path

    interview_story = Path("docs/interview_story.md").read_text()
    sixty_second_pitch = Path("docs/sixty_second_pitch.md").read_text()
    resume_bullets = Path("docs/resume_bullets.md").read_text()
    system_design = Path("docs/system_design_notes.md").read_text()
    failure_modes = Path("docs/failure_modes.md").read_text()
    demo_script = Path("docs/demo_script.md").read_text()

    assert "ordinary RAG" in interview_story
    assert "claim-level evidence engine" in interview_story
    assert "I built this because ordinary RAG" in sixty_second_pitch
    assert "中文" in sixty_second_pitch
    assert "60 due-diligence tasks" in resume_bullets
    assert "validator-augmented" in resume_bullets
    assert "Evidence graph" in system_design
    assert "fiscal-period confusion" in failure_modes
    assert "python3 -m streamlit run app.py" in demo_script
    assert "financial_evidence_engine.cli" in demo_script


def test_readme_has_fast_portfolio_entry_points():
    readme = Path("README.md").read_text()

    assert "2-minute read" in readme
    assert "10-minute artifact" in readme
    assert "30-minute reproduction" in readme
    assert "reports/final_report.pdf" in readme
    assert "docs/interview_story.md" in readme
    assert "docs/sixty_second_pitch.md" in readme


def test_interview_packaging_smoke_script():
    result = subprocess.run(
        [sys.executable, "scripts/smoke_interview_packaging.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "docs=6" in result.stdout
    assert "readme_2min=True" in result.stdout
    assert "repo_30min=True" in result.stdout
