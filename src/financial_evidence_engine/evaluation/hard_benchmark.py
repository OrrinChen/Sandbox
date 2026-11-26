"""Harder synthetic retrieval and verification benchmark.

Issuers, amounts, and passages are fictional. They are not SEC filings.
The original 60-task benchmark is not built or scored here.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import math
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from financial_evidence_engine.reasoning.models import EvidenceReference, Subclaim
from financial_evidence_engine.retrieval.dense_lsa import CorpusTfidfSvdEmbeddingProvider, _cosine
from financial_evidence_engine.retrieval.embeddings import MetadataBoostReranker
from financial_evidence_engine.retrieval.real_baselines import (
    RetrievalCorpusDocument,
    RetrievalResult,
    _bm25_score,
    _average_length,
    _decimal_score,
    _document_frequencies,
    _tokenize,
)
from financial_evidence_engine.validators.fiscal_period_validator import FiscalPeriodValidator
from financial_evidence_engine.validators.numeric_validator import NumericValidator


GENERATOR_ID = "hard-benchmark-v1"
TASK_SET_ID = "hard-benchmark-v1"
SPLIT_DEV_CUTOFF = 77  # first sha256 byte < 77 is dev, about 30 percent
TOLERANCE_USD = Decimal("250000000")
BILLION = Decimal("1000000000")
CONTENT_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "did",
        "for",
        "in",
        "of",
        "on",
        "the",
        "that",
        "to",
        "was",
        "were",
        "its",
        "by",
        "with",
    }
)

_SMALL = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty")


@dataclass(frozen=True)
class Issuer:
    ticker: str
    legal_name: str
    descriptor: str
    fiscal_end: str


ISSUERS: Tuple[Issuer, ...] = (
    Issuer("ARCA", "Arcadia Devices Inc.", "device maker", "September 28"),
    Issuer("BREL", "Boreal Software Inc.", "software vendor", "June 30"),
    Issuer("CIND", "Cinder Compute Inc.", "chip designer", "January 26"),
    Issuer("DORA", "Dora Retail Inc.", "retailer", "December 31"),
    Issuer("ELAN", "Elan Payments Inc.", "payments firm", "December 31"),
    Issuer("FOLD", "Folding Health Inc.", "care provider", "December 31"),
)

# Fictional USD amounts, chosen so each total sits within $120 million of an
# integer billion and adjacent years are at least about $1 billion apart.
REVENUE_USD: Mapping[str, Mapping[int, int]] = {
    "ARCA": {2021: 36_050_000_000, 2022: 40_080_000_000, 2023: 44_120_000_000, 2024: 48_090_000_000},
    "BREL": {2021: 18_040_000_000, 2022: 21_110_000_000, 2023: 24_070_000_000, 2024: 28_060_000_000},
    "CIND": {2021: 13_020_000_000, 2022: 17_080_000_000, 2023: 22_040_000_000, 2024: 32_110_000_000},
    "DORA": {2021: 51_050_000_000, 2022: 54_090_000_000, 2023: 57_040_000_000, 2024: 61_080_000_000},
    "ELAN": {2021: 8_030_000_000, 2022: 9_060_000_000, 2023: 10_040_000_000, 2024: 12_070_000_000},
    "FOLD": {2021: 14_020_000_000, 2022: 15_050_000_000, 2023: 17_080_000_000, 2024: 19_040_000_000},
}

OPERATING_MARGIN: Mapping[str, Decimal] = {
    "ARCA": Decimal("0.28"),
    "BREL": Decimal("0.41"),
    "CIND": Decimal("0.24"),
    "DORA": Decimal("0.06"),
    "ELAN": Decimal("0.15"),
    "FOLD": Decimal("0.12"),
}


@dataclass(frozen=True)
class HardPassage:
    document_id: str
    text: str
    company_ticker: str
    fiscal_period: str
    metric: str
    numeric_value_usd: Optional[Decimal]
    source_type: str


@dataclass(frozen=True)
class HardDocument(HardPassage):
    is_canonical: bool

    def public(self) -> HardPassage:
        return HardPassage(**{field.name: getattr(self, field.name) for field in fields(HardPassage)})


@dataclass(frozen=True)
class HardQuery:
    task_id: str
    claim_text: str
    company_tickers: Tuple[str, ...]
    fiscal_periods: Tuple[str, ...]
    kind: str
    metric: str
    claimed_value_usd: Optional[Decimal]
    tolerance_usd: Decimal
    comparison_left: Optional[Tuple[str, str, str]]
    comparison_right: Optional[Tuple[str, str, str]]
    margin_threshold: Optional[Decimal]


@dataclass(frozen=True)
class HardTask:
    task_id: str
    family: str
    claim_text: str
    company_tickers: Tuple[str, ...]
    fiscal_periods: Tuple[str, ...]
    kind: str
    gold_document_ids: Tuple[str, ...]
    lexical_trap_id: str
    expected_verdict: str
    split: str
    metric: str = "revenue"
    claimed_value_usd: Optional[Decimal] = None
    tolerance_usd: Decimal = TOLERANCE_USD
    comparison_left: Optional[Tuple[str, str, str]] = None
    comparison_right: Optional[Tuple[str, str, str]] = None
    left_should_exceed: Optional[bool] = None
    margin_threshold: Optional[Decimal] = None
    margin_should_exceed: Optional[bool] = None

    def public(self) -> HardQuery:
        return HardQuery(**{field.name: getattr(self, field.name) for field in fields(HardQuery)})


@dataclass(frozen=True)
class HardBenchmark:
    documents: Tuple[HardDocument, ...]
    tasks: Tuple[HardTask, ...]

    def document_by_id(self) -> Mapping[str, HardDocument]:
        return {document.document_id: document for document in self.documents}


def build_hard_benchmark() -> HardBenchmark:
    """Build the labeled corpus and tasks. No randomness."""

    documents: List[HardDocument] = []
    next_id = 1

    def add(text: str, **kwargs: object) -> HardDocument:
        nonlocal next_id
        document = HardDocument(document_id=f"d{next_id:04d}", text=text, **kwargs)  # type: ignore[arg-type]
        next_id += 1
        documents.append(document)
        return document

    canonical: Dict[Tuple[str, int, str], HardDocument] = {}
    for issuer in ISSUERS:
        for year in (2021, 2022, 2023, 2024):
            revenue = _money(REVENUE_USD[issuer.ticker][year])
            operating = _operating_income(issuer.ticker, revenue)
            net_income = (operating * Decimal("0.78")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            values = {"revenue": revenue, "operating_income": operating, "net_income": net_income}
            labels = {
                "revenue": "Net sales",
                "operating_income": "Operating income",
                "net_income": "Net income",
            }
            for metric, value in values.items():
                comparative = ""
                if year < 2024:
                    comparative = f" Comparative column of the fiscal {year + 1} Form 10-K."
                text = (
                    f"{issuer.legal_name} ({issuer.ticker}). Consolidated statements of operations. "
                    f"{labels[metric]} were {_million_line(value)} million USD for the fiscal year "
                    f"ended {issuer.fiscal_end}, {year}. Form 10-K item 8.{comparative}"
                )
                canonical[(issuer.ticker, year, metric)] = add(
                    text,
                    company_ticker=issuer.ticker,
                    fiscal_period=f"FY{year}",
                    metric=metric,
                    numeric_value_usd=value,
                    source_type="sec_filing",
                    is_canonical=True,
                )

    traps: Dict[Tuple[str, int, str], HardDocument] = {}
    for issuer in ISSUERS:
        for year in (2023, 2024):
            revenue = _money(REVENUE_USD[issuer.ticker][year])
            prior = _money(REVENUE_USD[issuer.ticker][year - 1])
            traps[(issuer.ticker, year, "lexical")] = add(
                (
                    f"{issuer.legal_name} brought in {_billion_phrase(prior)} dollars of top-line sales "
                    f"for the fiscal year that closed in {issuer.fiscal_end.split()[0]} {year}, "
                    f"according to a market recap that reused the sales headline."
                ),
                company_ticker=issuer.ticker,
                fiscal_period=f"FY{year}",
                metric="revenue",
                numeric_value_usd=prior,
                source_type="analyst_recap",
                is_canonical=False,
            )
            traps[(issuer.ticker, year, "scale")] = add(
                (
                    f"Data-vendor extract. The {issuer.descriptor} fiscal {year} sales line reads "
                    f"{_million_digits(revenue)} in thousands of USD and was captioned as the revenue total."
                ),
                company_ticker=issuer.ticker,
                fiscal_period=f"FY{year}",
                metric="revenue",
                numeric_value_usd=_money(int(_million_digits(revenue).replace(',', '')) * 1000),
                source_type="data_vendor",
                is_canonical=False,
            )
            traps[(issuer.ticker, year, "calendar")] = add(
                (
                    f"Calendar-year wrap. The {issuer.descriptor} took in {_billion_phrase(prior)} "
                    f"dollars during calendar {year}. This recap is not the fiscal-year statement."
                ),
                company_ticker=issuer.ticker,
                fiscal_period=f"CY{year}",
                metric="revenue",
                numeric_value_usd=prior,
                source_type="analyst_recap",
                is_canonical=False,
            )

    for issuer in ISSUERS:
        for index in range(4):
            add(
                (
                    f"The {issuer.descriptor} told holders that fiscal {2023 + (index % 2)} sales "
                    f"trends would be discussed later. No audited total was printed in note {index + 1}."
                ),
                company_ticker=issuer.ticker,
                fiscal_period=f"FY{2023 + (index % 2)}",
                metric="narrative",
                numeric_value_usd=None,
                source_type="shareholder_letter",
                is_canonical=False,
            )
    for index in range(24):
        issuer = ISSUERS[index % len(ISSUERS)]
        add(
            (
                f"Market wrap {index + 1}. Commentators mentioned revenue, fiscal year, sales, "
                f"and the {issuer.descriptor} without quoting an audited line."
            ),
            company_ticker=issuer.ticker,
            fiscal_period="FY2024",
            metric="narrative",
            numeric_value_usd=None,
            source_type="market_wrap",
            is_canonical=False,
        )

    tasks: List[HardTask] = []
    for issuer in ISSUERS:
        for year in (2023, 2024):
            revenue = _money(REVENUE_USD[issuer.ticker][year])
            prior = _money(REVENUE_USD[issuer.ticker][year - 1])
            gold = canonical[(issuer.ticker, year, "revenue")]
            tasks.append(
                _task(
                    family="paraphrase_support",
                    kind="single_fact",
                    claim_text=(
                        f"Did {issuer.legal_name} bring in {_billion_phrase(revenue)} dollars "
                        f"of top-line sales for the fiscal year that closed in {issuer.fiscal_end.split()[0]} {year}?"
                    ),
                    issuer=issuer,
                    year=year,
                    gold_ids=(gold.document_id,),
                    trap_id=traps[(issuer.ticker, year, "lexical")].document_id,
                    claimed=nearest_billion_usd(revenue),
                )
            )
            tasks.append(
                _task(
                    family="prior_year_contradict",
                    kind="single_fact",
                    claim_text=(
                        f"Did {issuer.legal_name} bring in {_billion_phrase(prior)} dollars "
                        f"of top-line sales for the fiscal year that closed in {issuer.fiscal_end.split()[0]} {year}?"
                    ),
                    issuer=issuer,
                    year=year,
                    gold_ids=(gold.document_id,),
                    trap_id=traps[(issuer.ticker, year, "lexical")].document_id,
                    claimed=nearest_billion_usd(prior),
                )
            )
            tasks.append(
                _task(
                    family="scale_trap_contradict",
                    kind="single_fact",
                    claim_text=(
                        f"Is {issuer.legal_name}'s fiscal {year} top-line total the thousands-denominated "
                        f"reading rather than the millions line in the audited statement?"
                    ),
                    issuer=issuer,
                    year=year,
                    gold_ids=(gold.document_id,),
                    trap_id=traps[(issuer.ticker, year, "scale")].document_id,
                    claimed=traps[(issuer.ticker, year, "scale")].numeric_value_usd,
                    tolerance=Decimal("1"),
                )
            )
            tasks.append(
                _task(
                    family="calendar_trap_contradict",
                    kind="single_fact",
                    claim_text=(
                        f"Did {issuer.legal_name} take in {_billion_phrase(prior)} dollars "
                        f"during calendar {year}, and is that the fiscal-year top-line total?"
                    ),
                    issuer=issuer,
                    year=year,
                    gold_ids=(gold.document_id,),
                    trap_id=traps[(issuer.ticker, year, "calendar")].document_id,
                    claimed=nearest_billion_usd(prior),
                )
            )
        margin = OPERATING_MARGIN[issuer.ticker]
        tasks.append(
            _margin_task(
                issuer=issuer,
                gold_revenue=canonical[(issuer.ticker, 2024, "revenue")],
                gold_operating=canonical[(issuer.ticker, 2024, "operating_income")],
                should_exceed=margin > Decimal("0.20"),
            )
        )

    pairs = (("ARCA", "BREL", True), ("CIND", "BREL", True), ("DORA", "ARCA", True), ("ELAN", "FOLD", False), ("FOLD", "CIND", False))
    by_ticker = {issuer.ticker: issuer for issuer in ISSUERS}
    for left, right, _expected in pairs:
        left_issuer = by_ticker[left]
        right_issuer = by_ticker[right]
        left_value = _money(REVENUE_USD[left][2024])
        right_value = _money(REVENUE_USD[right][2024])
        exceeds = left_value > right_value
        tasks.append(
            HardTask(
                task_id=f"cross-{left}-{right}-2024",
                family="cross_company",
                claim_text=(
                    f"{left_issuer.legal_name} booked more fiscal 2024 top-line sales than {right_issuer.legal_name}."
                ),
                company_tickers=(left, right),
                fiscal_periods=("FY2024",),
                kind="comparison",
                gold_document_ids=(
                    canonical[(left, 2024, "revenue")].document_id,
                    canonical[(right, 2024, "revenue")].document_id,
                ),
                lexical_trap_id=traps[(left, 2024, "lexical")].document_id,
                expected_verdict="support" if exceeds else "contradict",
                split=_split(f"cross-{left}-{right}-2024"),
                comparison_left=(left, "FY2024", "revenue"),
                comparison_right=(right, "FY2024", "revenue"),
                left_should_exceed=exceeds,
            )
        )
    for issuer in ISSUERS:
        task_id = f"missing-{issuer.ticker}-oncology"
        tasks.append(
            HardTask(
                task_id=task_id,
                family="missing_fact_insufficient",
                claim_text=(
                    f"Did {issuer.legal_name} disclose fiscal 2024 oncology segment sales "
                    f"above {_billion_phrase(_money(5_000_000_000))} dollars?"
                ),
                company_tickers=(issuer.ticker,),
                fiscal_periods=("FY2024",),
                kind="single_fact",
                metric="oncology_segment_revenue",
                gold_document_ids=(),
                lexical_trap_id=traps[(issuer.ticker, 2024, "lexical")].document_id,
                expected_verdict="insufficient",
                split=_split(task_id),
                claimed_value_usd=Decimal("5000000000"),
            )
        )

    benchmark = HardBenchmark(documents=tuple(documents), tasks=tuple(tasks))
    _check_construction(benchmark)
    labeled = tuple(_with_oracle_verdict(task, benchmark) for task in benchmark.tasks)
    return HardBenchmark(documents=benchmark.documents, tasks=labeled)


def evaluate_hard_benchmark(
    benchmark: HardBenchmark,
    embed_queries_and_documents: Optional[Callable[[Sequence[str]], Tuple[Tuple[float, ...], ...]]] = None,
    top_ks: Sequence[int] = (1, 5, 10),
    candidate_pool: int = 50,
    *,
    historical_canonical_boost: bool = False,
) -> Mapping[str, object]:
    """Score text retrievers and the metadata-constrained validator path."""

    # Ranking and prediction receive only public projections. This one historical
    # option reproduces the original study's explicit boost for canonical rows.
    canonical_ids = (
        {document.document_id for document in benchmark.documents if document.is_canonical}
        if historical_canonical_boost else set()
    )
    documents = tuple(document.public() for document in benchmark.documents)
    doc_texts = tuple(document.text for document in documents)
    tokenized = tuple(_tokenize(text) for text in doc_texts)
    frequencies = _document_frequencies(tokenized)
    average_length = _average_length(tokenized)
    svd = CorpusTfidfSvdEmbeddingProvider(
        dimension=32,
        max_features=2000,
        min_df=2,
        subspace_iterations=15,
        provider_id="hard-benchmark-tfidf-svd-v1",
    )
    svd_doc_vectors = svd.embed_texts(doc_texts)
    minilm_doc_vectors = None
    minilm_status = "not yet run"
    minilm_reason = "No embedding function was supplied."
    if embed_queries_and_documents is not None:
        minilm_doc_vectors = embed_queries_and_documents(doc_texts)
        minilm_status = "ran"
        minilm_reason = ""

    by_id = {document.document_id: document for document in documents}
    methods = (
        "bm25",
        "bm25_metadata_rerank",
        "dense_lsa",
        "dense_lsa_metadata_rerank",
        "dense_minilm",
        "dense_minilm_metadata_rerank",
        "full_engine",
    )
    per_task: Dict[str, List[Mapping[str, object]]] = {method: [] for method in methods}
    predictions = {method: [] for method in methods}
    for labeled_task in benchmark.tasks:
        task = labeled_task.public()
        scored = {
            "bm25": _bm25_scored(task, documents, tokenized, frequencies, average_length),
            "dense_lsa": _vector_scored(documents, svd_doc_vectors, svd.embed_texts((task.claim_text,))[0]),
            "full_engine": _metadata_scored(task, documents, canonical_ids),
        }
        if minilm_doc_vectors is not None:
            query_vector = embed_queries_and_documents((task.claim_text,))[0]  # type: ignore[misc]
            scored["dense_minilm"] = _vector_scored(documents, minilm_doc_vectors, query_vector)
        else:
            scored["dense_minilm"] = None
        rankings = {name: None if pairs is None else _order(pairs) for name, pairs in scored.items()}
        for base_name in ("bm25", "dense_lsa", "dense_minilm"):
            pairs = scored[base_name]
            rerank_name = f"{base_name}_metadata_rerank"
            if pairs is None:
                rankings[rerank_name] = None
            else:
                rankings[rerank_name] = _rerank(task, pairs, by_id, candidate_pool)
        for method, ranked in rankings.items():
            if ranked is None:
                continue
            predicted = _verdict_from_ranked(task, [by_id[document_id] for document_id in ranked[:5]])
            predictions[method].append({
                "task_id": task.task_id,
                "top_10": ranked[:10],
                "ranking_sha256": hashlib.sha256("\n".join(ranked).encode()).hexdigest(),
                "predicted_verdict": predicted,
            })
            per_task[method].append(_task_score(labeled_task, ranked, predicted, top_ks))

    reported = {}
    for method in methods:
        rows = per_task[method]
        if method.startswith("dense_minilm") and minilm_status != "ran":
            reported[method] = {"status": "not yet run", "reason": minilm_reason}
            continue
        reported[method] = {"status": "ran", **_aggregate(rows)}
    return {
        "generator_id": GENERATOR_ID,
        "task_set_id": TASK_SET_ID,
        "status": "ran",
        "provenance": provenance_record(benchmark),
        "setup": {
            "historical_canonical_boost": historical_canonical_boost,
            "query": "Paraphrased claim text only. Company and fiscal-period fields are not appended to the query.",
            "tie_break": "Higher score, then higher document_id. is_distractor is false for every row.",
            "candidate_pool": candidate_pool,
            "top_ks": list(top_ks),
            "svd": "Same TF-IDF subspace settings as the 60-task CPU run: dimension 32, min_df 2, 15 iterations.",
            "reranker": "Existing MetadataBoostReranker on the candidate pool, using due-diligence target company, fiscal period, sec_filing source, and metric.",
            "verdict": (
                "Among the method's top 5 documents, keep rows whose extracted company, fiscal period, "
                "and metric match the subclaim, take the best-ranked remaining row, then run "
                "FiscalPeriodValidator and NumericValidator. Comparison and margin tasks use the "
                "best-ranked extracted amounts for each required fact. full_engine ranks the whole "
                "corpus by those metadata fields before the same validators."
            ),
            "recall": "Macro-average over test tasks that have at least one grade-2 document. Grade 2 is a required canonical filing.",
            "ndcg": "Macro-average nDCG with grades 2 (required filing) and 0 (everything else), log base 2.",
            "split_reported": "test",
        },
        "methods": reported,
        "predictions": predictions,
    }


def provenance_record(benchmark: HardBenchmark) -> Mapping[str, object]:
    families: Dict[str, int] = {}
    splits: Dict[str, int] = {}
    verdicts: Dict[str, int] = {}
    for task in benchmark.tasks:
        families[task.family] = families.get(task.family, 0) + 1
        splits[task.split] = splits.get(task.split, 0) + 1
        verdicts[task.expected_verdict] = verdicts.get(task.expected_verdict, 0) + 1
    return {
        "construction": "synthetic-and-labeled",
        "real_filings_used": False,
        "edgar_text_reproduced": False,
        "issuers": "Fictional legal names and tickers. Amounts are invented.",
        "license": (
            "Benchmark generator and labels are part of this repository and covered by its MIT license. "
            "The passages are not SEC filings, not EDGAR excerpts, and not factual financial statements."
        ),
        "split": (
            f"sha256(task_id) first byte < {SPLIT_DEV_CUTOFF} is dev (about 30 percent); "
            "the remainder is test. The reported table is the test split. "
            "The dev split was not used to choose a retriever, a cutoff, or a validator."
        ),
        "document_count": len(benchmark.documents),
        "task_count": len(benchmark.tasks),
        "families": dict(sorted(families.items())),
        "splits": dict(sorted(splits.items())),
        "verdicts": dict(sorted(verdicts.items())),
        "canonical_fact_count": sum(1 for document in benchmark.documents if document.is_canonical),
    }


def render_hard_benchmark_markdown(payload: Mapping[str, object]) -> str:
    provenance = payload["provenance"]
    lines = [
        "# Hard benchmark",
        "",
        "Status: `ran`",
        "",
        "This benchmark is separate from the 60-task verdict numbers.",
        "",
        f"- Generator: `{payload['generator_id']}`",
        f"- Construction: `{provenance['construction']}`",
        f"- Real filings used: `{provenance['real_filings_used']}`",
        f"- Documents: `{provenance['document_count']}`",
        f"- Tasks: `{provenance['task_count']}`",
        f"- Test / dev: `{provenance['splits']}`",
        f"- License: {provenance['license']}",
        f"- Split: {provenance['split']}",
        f"- Query: {payload['setup']['query']}",
        f"- SVD: {payload['setup']['svd']}",
        f"- Reranker: {payload['setup']['reranker']}",
        f"- Dense encoder: {payload['setup'].get('dense_encoder', 'not recorded')}",
        "",
        payload["setup"]["verdict"],
        "",
        "Test-split metrics. Recall and nDCG are macro-averages. Verdict accuracy is correct verdicts over all test tasks.",
        "",
        "| Method | Status | Recall@1 | Recall@5 | Recall@10 | nDCG@5 | nDCG@10 | Verdict accuracy |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    methods = payload["methods"]
    for method, metrics in methods.items():
        if metrics.get("status") != "ran":
            lines.append(f"| {method} | not yet run |  |  |  |  |  |  |")
            continue
        test = metrics["test"]
        lines.append(
            "| {method} | ran | {r1} | {r5} | {r10} | {n5} | {n10} | {verdict} |".format(
                method=method,
                r1=_cell(test, "recall_at_1"),
                r5=_cell(test, "recall_at_5"),
                r10=_cell(test, "recall_at_10"),
                n5=_cell(test, "ndcg_at_5"),
                n10=_cell(test, "ndcg_at_10"),
                verdict=_cell(test, "verdict_accuracy"),
            )
        )
    lines.extend(["", "Exact fractions and task counts are in the JSON artifact.", ""])
    return "\n".join(lines)


def _task(
    family: str,
    kind: str,
    claim_text: str,
    issuer: Issuer,
    year: int,
    gold_ids: Tuple[str, ...],
    trap_id: str,
    claimed: Decimal,
    tolerance: Decimal = TOLERANCE_USD,
) -> HardTask:
    task_id = f"{family}-{issuer.ticker}-{year}"
    return HardTask(
        task_id=task_id,
        family=family,
        claim_text=claim_text,
        company_tickers=(issuer.ticker,),
        fiscal_periods=(f"FY{year}",),
        kind=kind,
        gold_document_ids=gold_ids,
        lexical_trap_id=trap_id,
        expected_verdict="",
        split=_split(task_id),
        claimed_value_usd=claimed,
        tolerance_usd=tolerance,
    )


def _margin_task(
    issuer: Issuer,
    gold_revenue: HardDocument,
    gold_operating: HardDocument,
    should_exceed: bool,
) -> HardTask:
    task_id = f"margin-{issuer.ticker}-2024"
    claim = (
        f"After operating costs, {issuer.legal_name} kept more than a fifth of fiscal 2024 sales."
    )
    return HardTask(
        task_id=task_id,
        family="margin_multihop",
        claim_text=claim,
        company_tickers=(issuer.ticker,),
        fiscal_periods=("FY2024",),
        kind="margin",
        metric="operating_income",
        gold_document_ids=(gold_revenue.document_id, gold_operating.document_id),
        lexical_trap_id="",
        expected_verdict="support" if should_exceed else "contradict",
        split=_split(task_id),
        margin_threshold=Decimal("0.20"),
        margin_should_exceed=should_exceed,
    )


def _with_oracle_verdict(task: HardTask, benchmark: HardBenchmark) -> HardTask:
    if task.family == "missing_fact_insufficient":
        verdict = "insufficient"
    else:
        canonical = [document for document in benchmark.documents if document.is_canonical]
        verdict = _verdict_from_ranked(task.public(), canonical)
    return HardTask(
        task_id=task.task_id,
        family=task.family,
        claim_text=task.claim_text,
        company_tickers=task.company_tickers,
        fiscal_periods=task.fiscal_periods,
        kind=task.kind,
        gold_document_ids=task.gold_document_ids,
        lexical_trap_id=task.lexical_trap_id,
        expected_verdict=verdict,
        split=task.split,
        metric=task.metric,
        claimed_value_usd=task.claimed_value_usd,
        tolerance_usd=task.tolerance_usd,
        comparison_left=task.comparison_left,
        comparison_right=task.comparison_right,
        left_should_exceed=task.left_should_exceed,
        margin_threshold=task.margin_threshold,
        margin_should_exceed=task.margin_should_exceed,
    )


def _check_construction(benchmark: HardBenchmark) -> None:
    by_id = benchmark.document_by_id()
    overlaps_gold = []
    overlaps_trap = []
    for task in benchmark.tasks:
        if task.family != "paraphrase_support":
            continue
        gold = by_id[task.gold_document_ids[0]]
        trap = by_id[task.lexical_trap_id]
        if task.claim_text in gold.text or gold.text in task.claim_text:
            raise ValueError("claim text was copied into a gold passage")
        overlaps_gold.append(_content_jaccard(task.claim_text, gold.text))
        overlaps_trap.append(_content_jaccard(task.claim_text, trap.text))
        digits = _million_digits(_money(REVENUE_USD[task.company_tickers[0]][int(task.fiscal_periods[0][2:])]))
        if digits in task.claim_text:
            raise ValueError("paraphrase contains the filing's million digits")
    if sum(overlaps_gold) / len(overlaps_gold) >= sum(overlaps_trap) / len(overlaps_trap):
        raise ValueError("lexical traps are not harder than gold passages on content-word overlap")
    for issuer in ISSUERS:
        for year in (2022, 2023, 2024):
            current = _money(REVENUE_USD[issuer.ticker][year])
            prior = _money(REVENUE_USD[issuer.ticker][year - 1])
            if abs(current - nearest_billion_usd(current)) > Decimal("120000000"):
                raise ValueError("revenue is too far from an integer billion")
            if abs(current - nearest_billion_usd(prior)) <= TOLERANCE_USD:
                raise ValueError("adjacent years are inside the claim tolerance")


def _bm25_scored(task, documents, tokenized, frequencies, average_length) -> List[Tuple[float, str]]:
    query_tokens = _tokenize(task.claim_text)
    scored = []
    for document, tokens in zip(documents, tokenized):
        score = _bm25_score(query_tokens, tokens, frequencies, len(documents), average_length)
        scored.append((score, document.document_id))
    return scored


def _vector_scored(documents, doc_vectors, query_vector) -> List[Tuple[float, str]]:
    return [
        (_cosine(query_vector, doc_vector), document.document_id)
        for document, doc_vector in zip(documents, doc_vectors)
    ]


def _metadata_scored(task: HardQuery, documents: Sequence[HardPassage], historical_canonical_ids) -> List[Tuple[float, str]]:
    metrics = _task_metrics(task)
    scored = []
    for document in documents:
        score = 0
        if document.company_ticker in task.company_tickers:
            score += 2
        if document.fiscal_period in task.fiscal_periods:
            score += 2
        if document.metric in metrics:
            score += 2
        if document.document_id in historical_canonical_ids:
            score += 1
        if document.source_type == "sec_filing":
            score += 1
        scored.append((float(score), document.document_id))
    return scored


def _rerank(
    task: HardQuery,
    scored_pairs: Sequence[Tuple[float, str]],
    by_id: Mapping[str, HardPassage],
    pool: int,
) -> Tuple[str, ...]:
    ordered = _order(scored_pairs)
    score_by_id = {document_id: score for score, document_id in scored_pairs}
    results = []
    for document_id in ordered[:pool]:
        document = by_id[document_id]
        results.append(
            RetrievalResult(
                document=RetrievalCorpusDocument(
                    document_id=document.document_id,
                    task_id=task.task_id,
                    evidence_key=document.document_id,
                    source_type=document.source_type,
                    modality="text",
                    company_ticker=document.company_ticker,
                    fiscal_period=document.fiscal_period,
                    role="passage",
                    text=document.text,
                    metric=document.metric,
                    is_distractor=False,
                ),
                score=_decimal_score(score_by_id[document_id]),
            )
        )
    reranked = MetadataBoostReranker().rerank_metadata(
        results, task.company_tickers, task.fiscal_periods, ("sec_filing",), _task_metrics(task)
    )
    return tuple(result.document.document_id for result in reranked)


def _task_score(task: HardTask, ranked_ids: Sequence[str], predicted: str, top_ks: Sequence[int]) -> Mapping[str, object]:
    grades = {document_id: 2 for document_id in task.gold_document_ids}
    row: Dict[str, object] = {
        "task_id": task.task_id,
        "split": task.split,
        "family": task.family,
        "expected_verdict": task.expected_verdict,
        "predicted_verdict": predicted,
    }
    for k in top_ks:
        row[f"recall_at_{k}"] = _recall(ranked_ids, grades, k)
        row[f"ndcg_at_{k}"] = _ndcg(ranked_ids, grades, k)
    return row


def _aggregate(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    aggregated = {}
    for split in ("test", "dev"):
        subset = [row for row in rows if row["split"] == split]
        aggregated[split] = _aggregate_split(subset)
    return aggregated


def _aggregate_split(rows: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    if not rows:
        return {"task_count": 0}
    verdict_hits = sum(1 for row in rows if row["predicted_verdict"] == row["expected_verdict"])
    payload: Dict[str, object] = {
        "task_count": len(rows),
        "verdict_correct": verdict_hits,
        "verdict_accuracy": _ratio(verdict_hits, len(rows)),
    }
    for key in ("recall_at_1", "recall_at_5", "recall_at_10", "ndcg_at_5", "ndcg_at_10"):
        values = [row[key] for row in rows if row[key] is not None]
        payload[f"{key}_tasks"] = len(values)
        if not values:
            payload[key] = None
        elif key.startswith("recall"):
            payload[key] = _ratio(sum(values), len(values))  # type: ignore[arg-type]
        else:
            payload[key] = f"{(sum(values) / len(values)):.10f}"  # type: ignore[arg-type]
    return payload


def _verdict_from_ranked(task: HardQuery, ranked_documents: Sequence[HardPassage]) -> str:
    if task.kind == "comparison":
        assert task.comparison_left is not None and task.comparison_right is not None
        left = _first_value(ranked_documents, task.comparison_left)
        right = _first_value(ranked_documents, task.comparison_right)
        if left is None or right is None:
            return "insufficient"
        return "support" if left > right else "contradict"
    if task.kind == "margin":
        revenue = _first_value(ranked_documents, (task.company_tickers[0], task.fiscal_periods[0], "revenue"))
        operating = _first_value(ranked_documents, (task.company_tickers[0], task.fiscal_periods[0], "operating_income"))
        if revenue is None or operating is None or revenue == 0:
            return "insufficient"
        return "support" if (operating / revenue) > task.margin_threshold else "contradict"  # type: ignore[operator]
    match = _first_document(ranked_documents, (task.company_tickers[0], task.fiscal_periods[0], task.metric))
    if match is None or match.numeric_value_usd is None or task.claimed_value_usd is None:
        return "insufficient"
    subclaim = Subclaim(
        subclaim_id=task.task_id,
        text=task.claim_text,
        company_ticker=task.company_tickers[0],
        fiscal_period=task.fiscal_periods[0],
        metric=task.metric,
        expected_value=task.claimed_value_usd,
        expected_currency="USD",
        tolerance=task.tolerance_usd,
    )
    evidence = EvidenceReference(
        evidence_id=match.document_id,
        document_id=match.document_id,
        company_ticker=match.company_ticker,
        fiscal_period=match.fiscal_period,
        page_or_section="passage",
        raw_text=match.text,
        source_span_label=match.source_type,
        normalized_metric=match.metric,
        numeric_value=match.numeric_value_usd,
        unit="USD",
        currency="USD",
    )
    period_check = FiscalPeriodValidator().validate(subclaim, evidence)
    if period_check.status != "pass":
        return "insufficient"
    numeric_check = NumericValidator().validate(subclaim, evidence)
    if numeric_check.status == "pass":
        return "support"
    return "contradict"


def _first_document(documents: Sequence[HardPassage], key: Tuple[str, str, str]) -> Optional[HardPassage]:
    ticker, period, metric = key
    for document in documents:
        if document.company_ticker == ticker and document.fiscal_period == period and document.metric == metric:
            return document
    return None


def _first_value(documents: Sequence[HardPassage], key: Tuple[str, str, str]) -> Optional[Decimal]:
    document = _first_document(documents, key)
    if document is None:
        return None
    return document.numeric_value_usd


def _requirement_keys(task: HardQuery) -> Tuple[Tuple[str, str, str], ...]:
    if task.kind == "comparison":
        assert task.comparison_left is not None and task.comparison_right is not None
        return (task.comparison_left, task.comparison_right)
    if task.kind == "margin":
        ticker = task.company_tickers[0]
        period = task.fiscal_periods[0]
        return ((ticker, period, "revenue"), (ticker, period, "operating_income"))
    return ((task.company_tickers[0], task.fiscal_periods[0], task.metric),)


def _task_metrics(task: HardQuery) -> Tuple[str, ...]:
    return tuple(metric for _ticker, _period, metric in _requirement_keys(task))


def _order(scored: Sequence[Tuple[float, str]]) -> Tuple[str, ...]:
    return tuple(document_id for _score, document_id in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True))


def _recall(ranked_ids: Sequence[str], grades: Mapping[str, int], k: int) -> Optional[Decimal]:
    gold = [document_id for document_id, grade in grades.items() if grade >= 2]
    if not gold:
        return None
    hits = sum(1 for document_id in ranked_ids[:k] if grades.get(document_id, 0) >= 2)
    return Decimal(hits) / Decimal(len(gold))


def _ndcg(ranked_ids: Sequence[str], grades: Mapping[str, int], k: int) -> Optional[float]:
    if not any(grade > 0 for grade in grades.values()):
        return None
    relevances = [grades.get(document_id, 0) for document_id in ranked_ids[:k]]
    ideal = sorted(grades.values(), reverse=True)
    ideal_dcg = _dcg(ideal, k)
    if ideal_dcg == 0:
        return None
    return _dcg(relevances, k) / ideal_dcg


def _dcg(relevances: Sequence[int], k: int) -> float:
    total = 0.0
    for index, relevance in enumerate(relevances[:k], start=1):
        total += (2 ** relevance - 1) / math.log2(index + 1)
    return total


def _content_jaccard(left: str, right: str) -> float:
    left_tokens = {token for token in _tokenize(left) if token not in CONTENT_STOP}
    right_tokens = {token for token in _tokenize(right) if token not in CONTENT_STOP}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _split(task_id: str) -> str:
    first_byte = int(hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:2], 16)
    if first_byte < SPLIT_DEV_CUTOFF:
        return "dev"
    return "test"


def _money(value: int) -> Decimal:
    return Decimal(value)


def nearest_billion_usd(value: Decimal) -> Decimal:
    billions = (value / BILLION).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return billions * BILLION


def _billion_phrase(value: Decimal) -> str:
    billions = int((value / BILLION).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if billions < 20:
        word = _SMALL[billions]
    else:
        tens, ones = divmod(billions, 10)
        word = _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_SMALL[ones]}"
    return f"about {word} billion"


def _million_digits(value: Decimal) -> str:
    millions = int((value / Decimal("1000000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{millions:,}"


def _million_line(value: Decimal) -> str:
    return _million_digits(value)


def _operating_income(ticker: str, revenue: Decimal) -> Decimal:
    return (revenue * OPERATING_MARGIN[ticker]).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _ratio(numerator: int, denominator: int) -> str:
    return str(Decimal(numerator) / Decimal(denominator))


def _cell(metrics: Mapping[str, object], key: str) -> str:
    value = metrics.get(key)
    if value is None:
        return ""
    if key.startswith("ndcg"):
        return f"{Decimal(str(value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"
    if key == "verdict_accuracy" or key.startswith("recall"):
        count_key = "task_count" if key == "verdict_accuracy" else f"{key}_tasks"
        correct_key = "verdict_correct" if key == "verdict_accuracy" else None
        if correct_key:
            return f"{metrics[correct_key]}/{metrics[count_key]} = `{value}`"
        return f"`{value}`"
    return f"`{value}`"
