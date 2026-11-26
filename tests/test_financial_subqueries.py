import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark import subqueries


@pytest.mark.parametrize(
    ("query", "first_source", "first_metric", "second_source", "second_metric"),
    [
        ("Aster Energy, FY2025: subtract the deck's lease outlays from the call's deferred cash.",
         "investor_deck", "lease outlays", "transcript", "deferred cash"),
        ("For FY2025, compare Aster Energy's cash receipts in the analyst call versus fees in the slide pack.",
         "transcript", "cash receipts", "investor_deck", "fees"),
        ("Find the gap between contract inflows in the results call and retention charges in the presentation.",
         "transcript", "contract inflows", "investor_deck", "retention charges"),
        ("For FY2025, how much did the call's receivables exceed the deck's customer advances?",
         "transcript", "receivables", "investor_deck", "customer advances"),
    ],
)
def test_explicit_source_clauses_keep_separate_metric_text(query, first_source, first_metric, second_source, second_metric):
    first, second = subqueries.split_query(query)
    assert (first.source_type, second.source_type) == (first_source, second_source)
    assert first_metric in first.text and second_metric not in first.text
    assert second_metric in second.text and first_metric not in second.text


def test_source_searches_share_five_slots_and_use_only_scope_resolved_from_question(monkeypatch):
    docs = [
        {"evidence_id": f"{ticker}-{period}-{source}", "company_ticker": ticker, "company_name": name,
         "fiscal_period": period, "source_type": source}
        for ticker, name in (("AEN", "Aster Energy"), ("AEA", "Aster Energy Advisory"))
        for period in ("FY2025", "FY2026")
        for source in ("transcript", "investor_deck", "sec_filing")
    ]
    calls = []

    def search_full(method, query, top_k, documents, **scope):
        calls.append((method, query, top_k, list(documents), scope))
        return [{"evidence_id": f"{scope['source_types'][0]}-{i}"} for i in range(top_k)]

    monkeypatch.setattr(subqueries, "search_full", search_full)
    hits = subqueries.search_split(
        "Aster Energy in FY2025: take advisory fees from the earnings Q&A less travel charges in the investor slides.",
        5, docs, tickers=["AEA", "AEN"], fiscal_periods=["FY2025", "FY2026"],
        source_types=["transcript", "investor_deck", "sec_filing"],
    )

    assert [call[2] for call in calls] == [3, 2]
    assert [len(call[3]) for call in calls] == [1, 1]
    for method, _, _, candidates, scope in calls:
        assert method == "hybrid"
        assert scope["tickers"] == ["AEN"] and scope["fiscal_periods"] == ["FY2025"]
        assert candidates[0]["source_type"] in scope["source_types"]
    assert [hit["evidence_id"] for hit in hits] == ["transcript-0", "investor_deck-0", "transcript-1", "investor_deck-1", "transcript-2"]


def test_unsplit_question_falls_back_to_hybrid_with_same_budget(monkeypatch):
    query = "What was Aster Energy's travel expense in the investor presentation?"
    observed = []

    def search_full(method, text, top_k, documents, **scope):
        observed.append((method, text, top_k, documents, scope))
        return []

    monkeypatch.setattr(subqueries, "search_full", search_full)
    scope = {"tickers": ["AEN"], "fiscal_periods": ["FY2025"], "source_types": ["investor_deck"]}
    assert subqueries.search_split(query, 5, [], **scope) == []
    assert observed == [("hybrid", query, 5, [], scope)]


@pytest.mark.parametrize(("qualifier", "expected"), [("", {"reported"}), ("forecast ", {"reported", "forecast"})])
def test_reporting_basis_keeps_requested_qualifiers_and_ignores_other_presentations(monkeypatch, qualifier, expected):
    issuer = {"company_ticker": "AEN", "company_name": "Aster Energy", "fiscal_period": "FY2025"}
    documents = [
        {**issuer, "evidence_id": "reported", "metric": "revenue", "source_type": "transcript"},
        {**issuer, "evidence_id": "forecast", "metric": "projected_revenue", "source_type": "transcript"},
        {**issuer, "evidence_id": "segment", "metric": "segment_revenue", "source_type": "transcript"},
        {**issuer, "evidence_id": "charges", "metric": "charges", "source_type": "investor_deck"},
    ]
    monkeypatch.setattr(subqueries, "search_full", lambda method, query, top_k, candidates, **scope: candidates[:top_k])

    hits = subqueries.search_split(
        f"Subtract charges from the investor deck from {qualifier}revenue from the earnings call for Aster Energy in FY2025.",
        5, documents, tickers=["AEN"], fiscal_periods=["FY2025"], source_types=["transcript", "investor_deck"],
    )

    assert {hit["evidence_id"] for hit in hits} == expected | {"charges"}
