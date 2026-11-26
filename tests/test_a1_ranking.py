from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_data import load_full_corpus
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.methods import search_full


def test_graph_scopes_candidates_before_cutoff():
    documents = [
        {
            "evidence_id": f"noise-{index}", "text": "revenue forecast",
            "company_ticker": "OTHER", "fiscal_period": "FY2024", "source_type": "transcript",
            "modality": "transcript", "metric": "revenue_guidance",
        }
        for index in range(65)
    ]
    documents.append({
        "evidence_id": "scoped", "text": "year ahead forecast contains a short discussion of operating costs",
        "company_ticker": "EXAMPLE", "fiscal_period": "FY2024", "source_type": "transcript",
        "modality": "transcript", "metric": "revenue_guidance",
    })

    hits = search_full(
        "graph", "revenue forecast", 5, documents,
        tickers=["EXAMPLE"], fiscal_periods=["FY2024"], source_types=["transcript"],
    )

    assert [hit["evidence_id"] for hit in hits] == ["scoped"]


def test_graph_ranks_actual_chart_table_and_xbrl_ahead_of_generic_text():
    documents = load_full_corpus()["documents"]
    hits = search_full(
        "graph", "Compare the NVIDIA FY2024 investor-deck chart to the SEC XBRL fact and filing table.",
        5, documents, tickers=["NVDA"], fiscal_periods=["FY2024"],
        source_types=["investor_deck", "sec_xbrl_companyfacts", "sec_filing"],
    )

    assert len(hits) == 5
    assert {"chart", "table", "xbrl"} <= {hit["modality"] for hit in hits}


def test_graph_keeps_numeric_operands_for_both_compared_issuers():
    documents = load_full_corpus()["documents"]
    hits = search_full(
        "graph", "Compare the FY2024 operating margin for JPMorgan Chase and Walmart. JPM WMT",
        5, documents, tickers=["JPM", "WMT"], fiscal_periods=["FY2024"],
        source_types=["sec_xbrl_companyfacts", "sec_filing"],
    )

    numeric_hits = {
        (hit["company_ticker"], hit["metric"])
        for hit in hits if hit["numeric_value"] is not None
    }
    assert {
        (ticker, metric) for ticker in ("JPM", "WMT") for metric in ("operating_income", "revenue")
    } <= numeric_hits


def test_margin_ranking_keeps_coherent_facts_and_corroborates_the_reference_issuer():
    documents = []
    for ticker in ("NORTH", "SOUTH"):
        common = {"company_ticker": ticker, "fiscal_period": "FY2024", "currency": "USD"}
        for metric, value in (("operating_income", 20), ("revenue", 100)):
            documents.append({
                **common, "evidence_id": f"{ticker}-{metric}", "text": f"{ticker} FY2024 {metric} {value} USD",
                "source_type": "sec_xbrl_companyfacts", "document_id": f"{ticker}-facts",
                "modality": "xbrl", "metric": metric, "numeric_value": value, "unit": "USD",
            })
        documents.append({
            **common, "evidence_id": f"{ticker}-table", "text": f"{ticker} FY2024 operating margin revenue table",
            "source_type": "sec_filing", "document_id": f"{ticker}-filing",
            "modality": "table", "metric": "revenue", "numeric_value": 100, "unit": "USD",
        })
        documents.extend({
            **common, "evidence_id": f"{ticker}-paragraph-{i}",
            "text": f"Was {ticker} FY2024 operating margin higher?",
            "source_type": "sec_filing", "document_id": f"{ticker}-filing",
            "modality": "text", "metric": "revenue", "numeric_value": None,
        } for i in range(5))

    primary_ids = {
        f"{ticker}-{metric}" for ticker in ("NORTH", "SOUTH") for metric in ("operating_income", "revenue")
    }
    for method in ("hybrid", "graph", "full_engine"):
        for subject, peer in (("NORTH", "SOUTH"), ("SOUTH", "NORTH")):
            hits = search_full(
                method, f"Was {subject}'s FY2024 operating margin higher than {peer}'s?",
                5, list(reversed(documents)), tickers=[subject, peer], fiscal_periods=["FY2024"],
                source_types=["sec_xbrl_companyfacts", "sec_filing"],
            )
            assert {hit["evidence_id"] for hit in hits} == primary_ids | {f"{peer}-table"}
