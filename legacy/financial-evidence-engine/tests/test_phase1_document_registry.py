from datetime import date, datetime, timezone

from financial_evidence_engine.config import CompanyUniverseEntry


def _apple() -> CompanyUniverseEntry:
    return CompanyUniverseEntry(
        ticker="AAPL",
        name="Apple Inc.",
        cik="0000320193",
        sector="Technology Hardware",
        fiscal_year=2024,
        required_documents=("10-K", "XBRL company facts"),
    )


def _submissions_payload():
    return {
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-24-000123",
                    "0000320193-24-000095",
                ],
                "filingDate": [
                    "2024-11-01",
                    "2024-08-02",
                ],
                "reportDate": [
                    "2024-09-28",
                    "2024-06-29",
                ],
                "form": [
                    "10-K",
                    "10-Q",
                ],
                "primaryDocument": [
                    "aapl-20240928.htm",
                    "aapl-20240629.htm",
                ],
            }
        }
    }


def _companyfacts_payload():
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                                "end": "2024-09-28",
                                "val": 391035000000,
                                "accn": "0000320193-24-000123",
                            }
                        ]
                    }
                }
            }
        },
    }


def test_document_registry_builds_sec_10k_and_xbrl_metadata():
    from financial_evidence_engine.data.document_registry import build_registry_for_company

    documents = build_registry_for_company(
        company=_apple(),
        submissions_payload=_submissions_payload(),
        companyfacts_payload=_companyfacts_payload(),
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
    )

    assert [document.source_type for document in documents] == [
        "sec_filing",
        "sec_xbrl_companyfacts",
    ]
    assert [document.filing_type for document in documents] == ["10-K", "XBRL company facts"]
    assert {document.ticker for document in documents} == {"AAPL"}
    assert {document.cik for document in documents} == {"0000320193"}
    assert {document.fiscal_year for document in documents} == {2024}
    assert {document.fiscal_quarter for document in documents} == {"FY"}
    assert {document.period_end_date for document in documents} == {date(2024, 9, 28)}
    assert {document.publication_date for document in documents} == {date(2024, 11, 1)}
    assert all(len(document.version_hash) == 64 for document in documents)
    assert documents[0].source_url.endswith(
        "/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"
    )


def test_document_registry_keeps_filing_date_and_fiscal_period_separate():
    from financial_evidence_engine.data.document_registry import build_registry_for_company

    submissions_payload = _submissions_payload()
    submissions_payload["filings"]["recent"]["filingDate"][0] = "2025-01-31"
    submissions_payload["filings"]["recent"]["reportDate"][0] = "2024-12-31"
    companyfacts_payload = _companyfacts_payload()
    companyfacts_payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["filed"] = "2025-01-31"
    companyfacts_payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["end"] = "2024-12-31"

    documents = build_registry_for_company(
        company=_apple(),
        submissions_payload=submissions_payload,
        companyfacts_payload=companyfacts_payload,
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
    )

    filing = documents[0]
    assert filing.publication_date == date(2025, 1, 31)
    assert filing.filing_date == date(2025, 1, 31)
    assert filing.period_end_date == date(2024, 12, 31)
    assert filing.publication_date != filing.period_end_date


def test_documents_align_by_company_and_fiscal_period():
    from financial_evidence_engine.data.document_registry import (
        align_documents_by_company_period,
        build_registry_for_company,
    )

    documents = build_registry_for_company(
        company=_apple(),
        submissions_payload=_submissions_payload(),
        companyfacts_payload=_companyfacts_payload(),
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
    )

    aligned = align_documents_by_company_period(documents)

    assert list(aligned.keys()) == [("AAPL", 2024, "FY")]
    assert [document.source_type for document in aligned[("AAPL", 2024, "FY")]] == [
        "sec_filing",
        "sec_xbrl_companyfacts",
    ]


def test_source_cache_writes_payload_with_stable_version_hash(tmp_path):
    from financial_evidence_engine.data.cache import SourceCache

    cache = SourceCache(tmp_path)

    first = cache.write_json(
        "sec/submissions/AAPL.json",
        {"b": 2, "a": 1},
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
    )
    second = cache.write_json(
        "sec/submissions/AAPL-reordered.json",
        {"a": 1, "b": 2},
        retrieved_at=datetime(2026, 4, 30, 9, 5, tzinfo=timezone.utc),
    )

    assert first.version_hash == second.version_hash
    assert first.payload_path == tmp_path / "sec/submissions/AAPL.json"
    assert first.metadata_path.is_file()
    assert cache.read_json("sec/submissions/AAPL.json") == {"a": 1, "b": 2}


def test_company_universe_index_resolves_ticker_and_cik():
    from financial_evidence_engine.config import CompanyUniverseIndex

    index = CompanyUniverseIndex.from_companies((_apple(),))

    assert index.cik_for_ticker("aapl") == "0000320193"
    assert index.ticker_for_cik("320193") == "AAPL"
    assert index.company_for_ticker("AAPL").name == "Apple Inc."


def test_sec_client_uses_required_user_agent_and_public_endpoints():
    from financial_evidence_engine.data.sec_client import SecClient

    calls = []

    def fake_transport(url, headers):
        calls.append((url, headers))
        return {"ok": True}

    client = SecClient(user_agent="research@example.com", transport=fake_transport)

    assert client.fetch_submissions("0000320193") == {"ok": True}
    assert client.fetch_companyfacts("0000320193") == {"ok": True}
    assert calls == [
        (
            "https://data.sec.gov/submissions/CIK0000320193.json",
            {"User-Agent": "research@example.com", "Accept-Encoding": "gzip, deflate"},
        ),
        (
            "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            {"User-Agent": "research@example.com", "Accept-Encoding": "gzip, deflate"},
        ),
    ]


def test_ingest_sec_company_fetches_caches_and_registers_documents(tmp_path):
    from financial_evidence_engine.data.cache import SourceCache
    from financial_evidence_engine.data.ingestion import ingest_sec_company

    class FakeSecClient:
        def __init__(self):
            self.calls = []

        def fetch_submissions(self, cik):
            self.calls.append(("submissions", cik))
            return _submissions_payload()

        def fetch_companyfacts(self, cik):
            self.calls.append(("companyfacts", cik))
            return _companyfacts_payload()

    client = FakeSecClient()
    cache = SourceCache(tmp_path)

    result = ingest_sec_company(
        company=_apple(),
        sec_client=client,
        cache=cache,
        retrieved_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
    )

    assert client.calls == [
        ("submissions", "0000320193"),
        ("companyfacts", "0000320193"),
    ]
    assert (tmp_path / "sec/submissions/AAPL.json").is_file()
    assert (tmp_path / "sec/companyfacts/AAPL.json").is_file()
    assert [document.source_type for document in result.documents] == [
        "sec_filing",
        "sec_xbrl_companyfacts",
    ]
    assert result.cached_payloads["submissions"].version_hash
    assert result.cached_payloads["companyfacts"].version_hash
