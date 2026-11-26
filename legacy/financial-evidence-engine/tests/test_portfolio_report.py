import json


def test_portfolio_report_package_has_required_sections_and_content():
    from financial_evidence_engine.reports.portfolio_report import build_portfolio_report_package

    package = build_portfolio_report_package()
    markdown = package.to_markdown()

    assert package.page_count <= 10
    assert [section.title for section in package.sections] == [
        "Problem: ordinary RAG is unsafe for financial due diligence",
        "System overview",
        "Evidence graph and validators",
        "Real retrieval benchmark",
        "Three failure case studies",
        "Investor deck and chart extraction case",
        "Ablation results",
        "Limitations",
        "Reproducibility",
        "Resume bullet",
    ]
    assert package.case_study_count == 3
    assert "fiscal_period_confusion" in markdown
    assert "numeric_unit_mismatch" in markdown
    assert "unsupported_narrative_claim" in markdown
    assert "NVIDIA FY2024 Data Center revenue" in markdown
    assert "Limitations" in markdown
    assert "python3 scripts/build_portfolio_report.py" in markdown
    assert "Built a multimodal financial due-diligence evidence engine" in package.resume_bullet


def test_portfolio_report_artifact_writer_outputs_pdf_markdown_figures_tables_and_resume(tmp_path):
    from financial_evidence_engine.reports.portfolio_report import (
        build_portfolio_report_package,
        write_portfolio_report_artifacts,
    )

    package = build_portfolio_report_package()
    manifest = write_portfolio_report_artifacts(package, reports_dir=tmp_path / "reports")

    assert manifest.pdf_path.name == "final_report.pdf"
    assert manifest.markdown_path.name == "final_report.md"
    assert manifest.resume_bullet_path.name == "resume_bullet.txt"
    assert len(manifest.figure_paths) == 5
    assert len(manifest.table_paths) >= 2
    assert manifest.manifest_path.exists()

    pdf_bytes = manifest.pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert pdf_bytes.count(b"/Type /Page") <= 10

    markdown = manifest.markdown_path.read_text()
    assert "## 5. Three failure case studies" in markdown
    assert "## 8. Limitations" in markdown
    assert "## 9. Reproducibility" in markdown

    manifest_payload = json.loads(manifest.manifest_path.read_text())
    assert manifest_payload["page_count"] <= 10
    assert manifest_payload["case_study_count"] == 3
    assert manifest_payload["includes_limitations"] is True
    assert manifest_payload["includes_reproducibility"] is True
    assert manifest_payload["pdf_path"].endswith("final_report.pdf")


def test_portfolio_report_smoke_script_is_registered_in_reproducibility_commands():
    from financial_evidence_engine.reports import REPRODUCIBILITY_COMMANDS

    assert "python3 scripts/build_portfolio_report.py" in REPRODUCIBILITY_COMMANDS
