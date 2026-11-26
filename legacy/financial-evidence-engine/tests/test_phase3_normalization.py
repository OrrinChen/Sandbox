from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from financial_evidence_engine.config import CompanyUniverseEntry, CompanyUniverseIndex
from financial_evidence_engine.data.models import DocumentMetadata


def _apple() -> CompanyUniverseEntry:
    return CompanyUniverseEntry(
        ticker="AAPL",
        name="Apple Inc.",
        cik="0000320193",
        sector="Technology Hardware",
        fiscal_year=2024,
        required_documents=("10-K", "XBRL company facts"),
    )


def _microsoft() -> CompanyUniverseEntry:
    return CompanyUniverseEntry(
        ticker="MSFT",
        name="Microsoft Corporation",
        cik="0000789019",
        sector="Software",
        fiscal_year=2024,
        required_documents=("10-K", "XBRL company facts"),
    )


def _document() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="AAPL:sec_filing:10-K:2024:000032019324000123",
        company="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        source_type="sec_filing",
        filing_type="10-K",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 9, 28),
        publication_date=date(2024, 11, 1),
        filing_date=date(2024, 11, 1),
        source_url="https://example.com/aapl-20240928.htm",
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        version_hash="0" * 64,
        accession_number="0000320193-24-000123",
    )


def test_entity_resolver_links_name_ticker_and_cik_without_cross_company_mismatch():
    from financial_evidence_engine.normalization.entity_linking import EntityResolutionError, EntityResolver

    resolver = EntityResolver(CompanyUniverseIndex.from_companies((_apple(), _microsoft())))

    assert resolver.resolve("aapl").ticker == "AAPL"
    assert resolver.resolve("Apple Inc.").cik == "0000320193"
    assert resolver.resolve("320193").name == "Apple Inc."
    assert resolver.resolve("Microsoft Corporation").ticker == "MSFT"

    with pytest.raises(EntityResolutionError, match="different companies"):
        resolver.ensure_same_company(resolver.resolve("AAPL"), resolver.resolve("MSFT"))


def test_fiscal_period_resolver_keeps_fiscal_calendar_and_frequency_separate():
    from financial_evidence_engine.normalization.fiscal_period_resolver import (
        FiscalPeriodMismatchError,
        FiscalPeriodResolver,
    )

    resolver = FiscalPeriodResolver()

    fy2023 = resolver.parse("FY2023")
    cy2023 = resolver.parse("CY2023")
    q2_fy2024 = resolver.parse("Q2 FY2024")
    document_period = resolver.from_document(_document())

    assert fy2023.year == 2023
    assert fy2023.basis == "fiscal"
    assert fy2023.period == "FY"
    assert cy2023.basis == "calendar"
    assert q2_fy2024.period == "Q2"
    assert q2_fy2024.frequency == "quarterly"
    assert document_period.period_end_date == date(2024, 9, 28)

    with pytest.raises(FiscalPeriodMismatchError, match="basis"):
        resolver.ensure_same_period(fy2023, cy2023)

    with pytest.raises(FiscalPeriodMismatchError, match="frequency"):
        resolver.ensure_same_period(fy2023, q2_fy2024)


def test_metric_alias_mapper_handles_common_financial_synonyms():
    from financial_evidence_engine.normalization.metric_mapper import MetricAliasMapper

    mapper = MetricAliasMapper()

    assert mapper.normalize("revenue") == "revenue"
    assert mapper.normalize("Net sales") == "revenue"
    assert mapper.normalize("total net sales") == "revenue"
    assert mapper.normalize("Operating income") == "operating_income"
    assert mapper.normalize("EBIT") == "operating_income"
    assert mapper.normalize("earnings") == "net_income"
    assert mapper.normalize("us-gaap:NetIncomeLoss") == "net_income"
    assert mapper.normalize("nonexistent metric") is None


def test_unit_and_currency_normalizer_converts_scales_to_base_currency_amounts():
    from financial_evidence_engine.normalization.unit_normalizer import UnitNormalizer

    normalizer = UnitNormalizer()

    billions = normalizer.normalize(Decimal("391.035"), "USD billions")
    millions = normalizer.normalize(Decimal("391035"), "$ millions")
    thousands = normalizer.normalize(Decimal("391035000"), "US dollars in thousands")

    assert billions.currency == "USD"
    assert billions.scale == "billions"
    assert billions.value == Decimal("391035000000")
    assert millions.value == Decimal("391035000000")
    assert thousands.value == Decimal("391035000000")


def test_comparison_guardrails_reject_wrong_period_scale_and_company():
    from financial_evidence_engine.normalization.entity_linking import EntityResolver
    from financial_evidence_engine.normalization.fiscal_period_resolver import FiscalPeriodResolver
    from financial_evidence_engine.normalization.guardrails import (
        FinancialObservation,
        NormalizationGuardrailError,
        ensure_comparable,
    )
    from financial_evidence_engine.normalization.metric_mapper import MetricAliasMapper
    from financial_evidence_engine.normalization.unit_normalizer import UnitNormalizer

    entity_resolver = EntityResolver(CompanyUniverseIndex.from_companies((_apple(), _microsoft())))
    period_resolver = FiscalPeriodResolver()
    metric_mapper = MetricAliasMapper()
    unit_normalizer = UnitNormalizer()

    apple_revenue = FinancialObservation(
        company=entity_resolver.resolve("AAPL"),
        fiscal_period=period_resolver.parse("FY2024"),
        metric=metric_mapper.normalize_required("total net sales"),
        amount=unit_normalizer.normalize(Decimal("391.035"), "USD billions"),
    )
    apple_revenue_thousands = FinancialObservation(
        company=entity_resolver.resolve("Apple Inc."),
        fiscal_period=period_resolver.parse("FY2024"),
        metric=metric_mapper.normalize_required("revenue"),
        amount=unit_normalizer.normalize(Decimal("391035000"), "USD thousands"),
    )
    apple_q4_revenue = FinancialObservation(
        company=entity_resolver.resolve("AAPL"),
        fiscal_period=period_resolver.parse("Q4 FY2024"),
        metric="revenue",
        amount=unit_normalizer.normalize(Decimal("94.93"), "USD billions"),
    )
    microsoft_revenue = FinancialObservation(
        company=entity_resolver.resolve("MSFT"),
        fiscal_period=period_resolver.parse("FY2024"),
        metric="revenue",
        amount=unit_normalizer.normalize(Decimal("245.122"), "USD billions"),
    )
    apple_unscaled_revenue = FinancialObservation(
        company=entity_resolver.resolve("AAPL"),
        fiscal_period=period_resolver.parse("FY2024"),
        metric="revenue",
        amount=unit_normalizer.normalize(Decimal("391.035"), "USD"),
    )

    assert ensure_comparable(apple_revenue, apple_revenue_thousands) is None

    with pytest.raises(NormalizationGuardrailError, match="period"):
        ensure_comparable(apple_revenue, apple_q4_revenue)

    with pytest.raises(NormalizationGuardrailError, match="company"):
        ensure_comparable(apple_revenue, microsoft_revenue)

    with pytest.raises(NormalizationGuardrailError, match="scale"):
        ensure_comparable(apple_revenue, apple_unscaled_revenue)
