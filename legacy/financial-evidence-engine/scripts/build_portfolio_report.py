"""Build the Phase 17 portfolio-ready technical report artifacts."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.reports import (
    build_portfolio_report_package,
    write_portfolio_report_artifacts,
)


def main() -> None:
    package = build_portfolio_report_package()
    manifest = write_portfolio_report_artifacts(package)
    print(
        f"sections={len(package.sections)} "
        f"pages={package.page_count} "
        f"case_studies={package.case_study_count} "
        f"figures={len(manifest.figure_paths)} "
        f"tables={len(manifest.table_paths)} "
        f"pdf={manifest.pdf_path} "
        f"markdown={manifest.markdown_path} "
        f"manifest={manifest.manifest_path}"
    )


if __name__ == "__main__":
    main()
