"""Smoke check for Phase 20 interview and resume packaging."""

from __future__ import annotations

from pathlib import Path


DOCS = (
    Path("docs/interview_story.md"),
    Path("docs/sixty_second_pitch.md"),
    Path("docs/resume_bullets.md"),
    Path("docs/system_design_notes.md"),
    Path("docs/failure_modes.md"),
    Path("docs/demo_script.md"),
)


def main() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    existing_docs = [path for path in DOCS if path.exists()]
    doc_text = "\n".join(path.read_text(encoding="utf-8") for path in existing_docs)
    readme_2min = "2-minute read" in readme and "docs/interview_story.md" in readme
    report_10min = "10-minute artifact" in readme and Path("reports/final_report.pdf").exists()
    repo_30min = "30-minute reproduction" in readme and "python3 -m pytest" in readme
    evidence_framing = "claim-level evidence engine" in doc_text and "ordinary RAG" in doc_text
    print(
        f"docs={len(existing_docs)} "
        f"readme_2min={readme_2min} "
        f"report_10min={report_10min} "
        f"repo_30min={repo_30min} "
        f"evidence_framing={evidence_framing}"
    )


if __name__ == "__main__":
    main()
