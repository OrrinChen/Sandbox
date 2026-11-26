"""Report generation package."""

from .data_platform import DataPlatformArtifactManifest, write_data_platform_artifacts
from .final_report import (
    ChartSpec,
    FinalReportPackage,
    REPRODUCIBILITY_COMMANDS,
    ReportTable,
    build_final_report_package,
)
from .memo import (
    DueDiligenceMemo,
    EvidenceTableRow,
    MemoClaim,
    MemoConclusion,
    MemoIssue,
    NumericReconciliationRow,
    build_due_diligence_memo,
)
from .portfolio_report import (
    FigureSpec,
    PortfolioReportArtifactManifest,
    PortfolioReportPackage,
    PortfolioReportSection,
    TableSpec,
    build_portfolio_report_package,
    write_portfolio_report_artifacts,
)

__all__ = [
    "ChartSpec",
    "DataPlatformArtifactManifest",
    "DueDiligenceMemo",
    "EvidenceTableRow",
    "FigureSpec",
    "FinalReportPackage",
    "MemoClaim",
    "MemoConclusion",
    "MemoIssue",
    "NumericReconciliationRow",
    "PortfolioReportArtifactManifest",
    "PortfolioReportPackage",
    "PortfolioReportSection",
    "REPRODUCIBILITY_COMMANDS",
    "ReportTable",
    "TableSpec",
    "build_due_diligence_memo",
    "build_final_report_package",
    "build_portfolio_report_package",
    "write_portfolio_report_artifacts",
    "write_data_platform_artifacts",
]
