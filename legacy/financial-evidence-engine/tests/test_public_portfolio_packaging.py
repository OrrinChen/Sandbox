from pathlib import Path


PUBLIC_TEXT_PATHS = (
    Path("PORTFOLIO.md"),
    Path("README.md"),
    Path("docs/interview_story.md"),
    Path("docs/sixty_second_pitch.md"),
    Path("docs/resume_bullets.md"),
    Path("docs/system_design_notes.md"),
    Path("docs/failure_modes.md"),
    Path("docs/demo_script.md"),
    Path("reports/final_report.md"),
    Path("reports/resume_bullet.txt"),
    Path("reports/dense_lsa/dense_lsa_rerank_ablation.md"),
    Path("reports/dense_sentence_transformer/dense_sentence_transformer_rerank_ablation.md"),
    Path("docs/hard_benchmark.md"),
    Path("reports/hard_benchmark/hard_benchmark.md"),
)


def test_public_packaging_has_no_local_or_self_rating_leaks():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_TEXT_PATHS)

    forbidden_fragments = (
        "ashare-radar",
        "/Users/",
        "New project 2",
        "S-level",
        "business-shock",
        "Business-shock",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined


def test_readme_is_the_public_entrypoint():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert readme.startswith("# Financial Evidence Engine")
    lead, results_and_after = readme.split("## Results", 1)
    assert "Synthetic benchmark generated in this repo" in lead
    assert "6 fictional issuers, 156 passages, 65 claims" in lead
    assert "not real SEC or EDGAR filings" in lead
    assert "0.159" in lead
    assert "0.466" in lead
    assert "0.966" in lead
    assert "18/47 (38.3%)" in lead
    assert "9/47 (19.1%)" in lead
    assert "33/47 (70.2%)" in lead
    assert "1.000" in lead
    assert "47/47" not in lead
    assert "100%" not in lead
    assert "favors the full engine" in lead
    assert "83.3%" in results_and_after
    assert "66.7%" in results_and_after
    assert "75.0%" in results_and_after
    assert "346" not in readme
    assert "```mermaid" in readme
    assert "## Limitations" in readme
    assert "AGENTS.md" not in readme
    assert "TASK_MEMORY.md" not in readme
    assert "RUNBOOK.md" not in readme
    assert "ROADMAP.md" not in readme
    for fragment in ("/Users/", "/home/", "C:/Users", "C:\\Users"):
        assert fragment not in readme

    demo_shots = (
        Path("docs/assets/claim_verification_demo.png"),
        Path("docs/assets/case_study_replay.png"),
        Path("docs/assets/memo_trace_demo.png"),
    )
    for path in demo_shots:
        assert str(path) in readme
        assert path.exists(), path
        assert path.stat().st_size > 10_000
    killer_metrics = Path("docs/assets/killer_metrics.png")
    assert killer_metrics.exists()
    assert "docs/assets/killer_metrics.png" not in readme
    assert "docs/sixty_second_pitch.md" in readme


def test_resume_bullets_avoid_overclaiming_optional_backends():
    generated_bullet = Path("reports/resume_bullet.txt").read_text(encoding="utf-8")
    doc_bullets = Path("docs/resume_bullets.md").read_text(encoding="utf-8")
    combined = generated_bullet + "\n" + doc_bullets

    assert "dense-proxy" in combined
    assert "validator-augmented retrieval" in combined
    assert "GraphRAG" not in generated_bullet
    assert "SEC/FMP data" not in generated_bullet
    assert "general chart" not in combined.lower()
    assert "trained neural" not in combined.lower()


def test_portfolio_md_is_recruiter_entrypoint():
    portfolio = Path("PORTFOLIO.md").read_text(encoding="utf-8")

    assert portfolio.startswith("# Financial Evidence Engine")
    assert "Claim-level financial evidence verification" in portfolio
    assert "docs/assets/claim_verification_demo.png" in portfolio
    assert "docs/assets/case_study_replay.png" in portfolio
    assert "docs/assets/memo_trace_demo.png" in portfolio
    assert "docs/assets/killer_metrics.png" in portfolio
    assert "30-minute reproduction" in portfolio
    assert "portfolio-v1" in portfolio
    assert "Ordinary RAG" in portfolio
    assert "claim decomposition" in portfolio
    assert "evidence graph" in portfolio
    assert "numeric reconciliation" in portfolio
    assert "validator gate" in portfolio
    assert "AI infra" in portfolio
    assert "Financial AI" in portfolio
    assert "RAG/eval" in portfolio


def test_makefile_exposes_short_portfolio_demo():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "portfolio-demo:" in makefile
    assert "python3 scripts/build_portfolio_screenshots.py" in makefile
    assert "python3 scripts/smoke_cli_workflow.py" in makefile
    assert "python3 scripts/smoke_interview_packaging.py" in makefile
    assert "screenshots=3" in makefile
    assert "commands=6" in makefile
    assert "verify_verdict=support" in makefile
    assert "docs=6" in makefile
    assert "api_key_required=False" in makefile
