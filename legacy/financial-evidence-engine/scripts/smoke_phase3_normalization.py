"""Smoke check for the Phase 3 financial normalization layer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_evidence_engine.config import CompanyUniverseIndex, load_company_universe
from financial_evidence_engine.normalization import (
    EntityResolver,
    FinancialObservation,
    FiscalPeriodResolver,
    MetricAliasMapper,
    UnitNormalizer,
    ensure_comparable,
)


def main() -> None:
    companies = load_company_universe(Path("configs/companies.yaml"))
    entity_resolver = EntityResolver(CompanyUniverseIndex.from_companies(companies))
    period_resolver = FiscalPeriodResolver()
    metric_mapper = MetricAliasMapper()
    unit_normalizer = UnitNormalizer()

    left = FinancialObservation(
        company=entity_resolver.resolve("AAPL"),
        fiscal_period=period_resolver.parse("FY2024"),
        metric=metric_mapper.normalize_required("total net sales"),
        amount=unit_normalizer.normalize(Decimal("391.035"), "USD billions"),
        source="table",
    )
    right = FinancialObservation(
        company=entity_resolver.resolve("Apple Inc."),
        fiscal_period=period_resolver.parse("FY2024"),
        metric=metric_mapper.normalize_required("revenue"),
        amount=unit_normalizer.normalize(Decimal("391035000"), "USD thousands"),
        source="xbrl",
    )

    ensure_comparable(left, right)
    print(
        "company=AAPL period=FY2024 metric=revenue "
        f"left_amount={left.amount.value} right_amount={right.amount.value} comparable=True"
    )


if __name__ == "__main__":
    main()
