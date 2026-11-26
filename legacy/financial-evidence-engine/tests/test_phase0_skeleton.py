from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def test_phase0_required_repository_files_exist():
    expected_files = [
        "README.md",
        "LICENSE",
        "VALIDATION.md",
        "configs/companies.yaml",
        "configs/dense_lsa.yaml",
        "src/financial_evidence_engine/__init__.py",
    ]

    missing = [
        relative_path
        for relative_path in expected_files
        if not (PROJECT_ROOT / relative_path).is_file()
    ]

    assert missing == []
    assert (PROJECT_ROOT.parents[1] / "pyproject.toml").is_file()


def test_agent_working_files_are_not_committed():
    removed = ["AGENTS.md", "TASK_MEMORY.md", "RUNBOOK.md", "ROADMAP.md"]
    present = [name for name in removed if (PROJECT_ROOT / name).exists()]
    assert present == []


def test_initial_company_universe_loads_three_large_cap_companies():
    from financial_evidence_engine.config import load_company_universe

    companies = load_company_universe(PROJECT_ROOT / "configs/companies.yaml")

    assert [company.ticker for company in companies] == ["AAPL", "MSFT", "NVDA"]
    assert {company.fiscal_year for company in companies} == {2024}
    assert all(company.cik.isdigit() and len(company.cik) == 10 for company in companies)
    assert all("10-K" in company.required_documents for company in companies)
    assert all("XBRL company facts" in company.required_documents for company in companies)


def test_company_universe_rejects_empty_config(tmp_path):
    from financial_evidence_engine.config import load_company_universe

    empty_config = tmp_path / "companies.yaml"
    empty_config.write_text("companies: []\n", encoding="utf-8")

    try:
        load_company_universe(empty_config)
    except ValueError as exc:
        assert "at least one company" in str(exc)
    else:
        raise AssertionError("empty company universe should fail")
