"""Raw financial document chunk corpus for retrieval evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from financial_evidence_engine.bundled import DECK_FIXTURE
from financial_evidence_engine.evaluation.task_set import DueDiligenceTaskSet
from financial_evidence_engine.extraction import DeckDocumentMetadata, extract_deck_chart_evidence


COMPANY_NAMES: Mapping[str, str] = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "AMZN": "Amazon",
    "GOOGL": "Alphabet",
    "META": "Meta",
    "JPM": "JPMorgan Chase",
    "WMT": "Walmart",
    "TSLA": "Tesla",
    "NFLX": "Netflix",
}

SEC_SECTIONS: Tuple[str, ...] = (
    "Item 1 - Business",
    "Item 1A - Risk Factors",
    "Item 7 - MD&A",
    "Item 8 - Financial Statements",
)

RAW_CREATED_AT = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
DEFAULT_DECK_FIXTURE_PATH = DECK_FIXTURE


@dataclass(frozen=True)
class ChunkProvenance:
    """Source coordinates for a raw document chunk."""

    company_ticker: str
    company_name: str
    source_type: str
    document_id: str
    fiscal_period: str
    section_or_page: str
    source_span_start: int
    source_span_end: int
    source_hash: str
    source_url: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "company_ticker": self.company_ticker,
            "company_name": self.company_name,
            "source_type": self.source_type,
            "document_id": self.document_id,
            "fiscal_period": self.fiscal_period,
            "section_or_page": self.section_or_page,
            "source_span_start": self.source_span_start,
            "source_span_end": self.source_span_end,
            "source_hash": self.source_hash,
            "source_url": self.source_url,
        }


@dataclass(frozen=True)
class DocumentChunk:
    """One searchable raw chunk with provenance and stable identity."""

    chunk_id: str
    chunk_type: str
    text: str
    provenance: ChunkProvenance
    chunk_hash: str
    normalized_metric: Optional[str] = None
    numeric_value: Optional[Decimal] = None
    unit: Optional[str] = None
    currency: Optional[str] = None

    @property
    def modality(self) -> str:
        return {
            "sec_filing_paragraph": "text",
            "sec_filing_section": "text",
            "sec_filing_table": "table",
            "xbrl_fact": "xbrl",
            "transcript_turn": "transcript",
            "deck_page": "text",
            "deck_chart": "chart",
        }.get(self.chunk_type, "text")

    def to_dict(self) -> Mapping[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "text": self.text,
            "provenance": self.provenance.to_dict(),
            "chunk_hash": self.chunk_hash,
            "normalized_metric": self.normalized_metric,
            "numeric_value": str(self.numeric_value) if self.numeric_value is not None else None,
            "unit": self.unit,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class ChunkIndexManifest:
    """Aggregate counts and version hash for a chunk index."""

    corpus_id: str
    chunk_count: int
    source_type_counts: Mapping[str, int]
    chunk_type_counts: Mapping[str, int]
    company_counts: Mapping[str, int]
    fiscal_period_counts: Mapping[str, int]
    version_hash: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "corpus_id": self.corpus_id,
            "chunk_count": self.chunk_count,
            "source_type_counts": dict(self.source_type_counts),
            "chunk_type_counts": dict(self.chunk_type_counts),
            "company_counts": dict(self.company_counts),
            "fiscal_period_counts": dict(self.fiscal_period_counts),
            "version_hash": self.version_hash,
        }


@dataclass(frozen=True)
class CorpusVersionManifest:
    """Version manifest for a raw corpus build."""

    corpus_id: str
    corpus_mode: str
    created_at: datetime
    source_document_count: int
    chunk_count: int
    chunk_index: ChunkIndexManifest
    version_hash: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "corpus_id": self.corpus_id,
            "corpus_mode": self.corpus_mode,
            "created_at": self.created_at.isoformat(),
            "source_document_count": self.source_document_count,
            "chunk_count": self.chunk_count,
            "chunk_index": self.chunk_index.to_dict(),
            "version_hash": self.version_hash,
        }


@dataclass(frozen=True)
class RawFinancialCorpus:
    """Raw financial document chunks plus manifest."""

    chunks: Tuple[DocumentChunk, ...]
    manifest: CorpusVersionManifest

    def to_retrieval_corpus(self):
        """Adapt raw chunks to the existing retrieval corpus interface."""

        from financial_evidence_engine.retrieval.real_baselines import RetrievalCorpus, RetrievalCorpusDocument

        documents = tuple(
            RetrievalCorpusDocument(
                document_id=chunk.chunk_id,
                task_id="raw_corpus",
                evidence_key=chunk.chunk_id,
                source_type=chunk.provenance.source_type,
                modality=chunk.modality,
                company_ticker=chunk.provenance.company_ticker,
                fiscal_period=chunk.provenance.fiscal_period,
                role=chunk.provenance.section_or_page,
                text=chunk.text,
                metric=chunk.normalized_metric,
                is_distractor=False,
            )
            for chunk in self.chunks
        )
        return RetrievalCorpus(documents=documents)

    def to_dict(self) -> Mapping[str, object]:
        return {
            "manifest": self.manifest.to_dict(),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }


class RawCorpusBuilder:
    """Build a deterministic raw-corpus fixture from local source-like documents."""

    def __init__(self, deck_fixture_path: Optional[Path] = None) -> None:
        self.deck_fixture_path = _resolve_deck_fixture_path(deck_fixture_path)

    def build(self, task_set: DueDiligenceTaskSet) -> RawFinancialCorpus:
        tickers = _task_tickers(task_set)
        chunks: List[DocumentChunk] = []
        source_documents = 0

        for index, ticker in enumerate(tickers):
            chunks.extend(_sec_filing_chunks(ticker, index))
            chunks.extend(_xbrl_fact_chunks(ticker, index))
            chunks.extend(_transcript_chunks(ticker, index))
            source_documents += 3

        deck_chunks = _deck_chunks(self.deck_fixture_path)
        if deck_chunks:
            chunks.extend(deck_chunks)
            source_documents += 1

        manifest = _manifest(tuple(chunks), source_documents)
        return RawFinancialCorpus(chunks=tuple(chunks), manifest=manifest)


def build_raw_financial_corpus(
    task_set: DueDiligenceTaskSet,
    deck_fixture_path: Optional[Path] = None,
) -> RawFinancialCorpus:
    """Build the deterministic Phase 11 raw financial corpus."""

    return RawCorpusBuilder(deck_fixture_path=deck_fixture_path).build(task_set)


def _resolve_deck_fixture_path(deck_fixture_path: Optional[Path]) -> Optional[Path]:
    if deck_fixture_path is not None:
        return deck_fixture_path
    if DEFAULT_DECK_FIXTURE_PATH.exists():
        return DEFAULT_DECK_FIXTURE_PATH
    return None


def _task_tickers(task_set: DueDiligenceTaskSet) -> Tuple[str, ...]:
    tickers: List[str] = []
    for task in task_set.tasks:
        for ticker in task.company_tickers:
            if ticker not in tickers:
                tickers.append(ticker)
    return tuple(tickers)


def _sec_filing_chunks(ticker: str, company_index: int) -> Tuple[DocumentChunk, ...]:
    company_name = COMPANY_NAMES.get(ticker, ticker)
    document_id = f"{ticker}:raw_sec_filing:10-K:2024"
    source_url = f"fixture://raw/sec/{ticker}-2024-10k.txt"
    section_texts = {
        section: _section_paragraphs(ticker, company_name, section, company_index)
        for section in SEC_SECTIONS
    }
    filing_text = "\n\n".join(
        f"{section}\n" + "\n".join(paragraphs)
        for section, paragraphs in section_texts.items()
    )
    source_hash = _hash(filing_text)
    chunks: List[DocumentChunk] = []

    for section, paragraphs in section_texts.items():
        section_text = "\n".join(paragraphs)
        section_start = filing_text.find(section_text)
        section_end = section_start + len(section_text)
        chunks.append(
            _chunk(
                chunk_type="sec_filing_section",
                text=section_text,
                ticker=ticker,
                company_name=company_name,
                source_type="sec_filing",
                document_id=document_id,
                section_or_page=section,
                start=section_start,
                end=section_end,
                source_hash=source_hash,
                source_url=source_url,
                metric=_section_metric(section),
            )
        )
        for paragraph in paragraphs:
            start = filing_text.find(paragraph)
            end = start + len(paragraph)
            chunks.append(
                _chunk(
                    chunk_type="sec_filing_paragraph",
                    text=paragraph,
                    ticker=ticker,
                    company_name=company_name,
                    source_type="sec_filing",
                    document_id=document_id,
                    section_or_page=section,
                    start=start,
                    end=end,
                    source_hash=source_hash,
                    source_url=source_url,
                    metric=_section_metric(section),
                )
            )

    table_text = (
        f"{company_name} FY2024 filing table: revenue {100 + company_index * 7} USD billions; "
        f"operating income {20 + company_index * 3} USD billions."
    )
    chunks.append(
        _chunk(
            chunk_type="sec_filing_table",
            text=table_text,
            ticker=ticker,
            company_name=company_name,
            source_type="sec_filing",
            document_id=document_id,
            section_or_page="Item 8 - Financial Statements / filing table",
            start=max(filing_text.find("Item 8"), 0),
            end=max(filing_text.find("Item 8"), 0) + len(table_text),
            source_hash=source_hash,
            source_url=source_url,
            metric="revenue",
            numeric_value=Decimal(str(100 + company_index * 7)),
            unit="billions",
            currency="USD",
        )
    )
    return tuple(chunks)


def _section_paragraphs(
    ticker: str,
    company_name: str,
    section: str,
    company_index: int,
) -> Tuple[str, ...]:
    topics = (
        "revenue recognition and product demand",
        "operating income, margin, and expense discipline",
        "fiscal-period comparability and annual filing context",
        "segment contribution and customer concentration",
        "supply chain and demand risk exposure",
        "foreign currency and unit scale disclosure",
        "management commentary requiring numeric support",
        "table values that must reconcile to XBRL facts",
        "citation scope for due-diligence evidence",
    )
    return tuple(
        (
            f"{company_name} ({ticker}) FY2024 {section} paragraph {index + 1}: "
            f"raw filing text discusses {topic}; this paragraph is indexed from a source-like "
            f"annual report fixture and is not a gold or distractor retrieval spec. "
            f"Reference value marker {company_index + 1}-{index + 1}."
        )
        for index, topic in enumerate(topics)
    )


def _xbrl_fact_chunks(ticker: str, company_index: int) -> Tuple[DocumentChunk, ...]:
    company_name = COMPANY_NAMES.get(ticker, ticker)
    document_id = f"{ticker}:raw_xbrl_companyfacts:2024:FY"
    source_url = f"fixture://raw/xbrl/{ticker}-companyfacts-2024.json"
    facts = (
        ("revenue", Decimal(str(100000000000 + company_index * 7000000000)), "us-gaap:Revenues"),
        ("operating_income", Decimal(str(20000000000 + company_index * 3000000000)), "us-gaap:OperatingIncomeLoss"),
        ("operating_expense", Decimal(str(30000000000 + company_index * 2000000000)), "us-gaap:OperatingExpenses"),
        ("risk_exposure", Decimal(str(1 + company_index)), "dei:EntityCommonStockSharesOutstanding"),
    )
    source_text = "\n".join(f"{taxonomy}={value}" for _, value, taxonomy in facts)
    source_hash = _hash(source_text)
    chunks = []
    for index, (metric, value, taxonomy) in enumerate(facts):
        text = f"{taxonomy} FY2024 FY = {value} USD for {company_name} ({ticker})."
        chunks.append(
            _chunk(
                chunk_type="xbrl_fact",
                text=text,
                ticker=ticker,
                company_name=company_name,
                source_type="sec_xbrl_companyfacts",
                document_id=document_id,
                section_or_page=taxonomy,
                start=index,
                end=index + 1,
                source_hash=source_hash,
                source_url=source_url,
                metric=metric,
                numeric_value=value,
                unit="USD",
                currency="USD",
            )
        )
    return tuple(chunks)


def _transcript_chunks(ticker: str, company_index: int) -> Tuple[DocumentChunk, ...]:
    company_name = COMPANY_NAMES.get(ticker, ticker)
    document_id = f"{ticker}:raw_transcript:2024:Q4"
    source_url = f"fixture://raw/transcripts/{ticker}-fy2024-q4.txt"
    turns = (
        (
            "Prepared Remarks / Chief Executive Officer",
            "operating_margin",
            f"{company_name} management said FY2024 demand was resilient but noted that narrative claims require filing support.",
        ),
        (
            "Prepared Remarks / Chief Financial Officer",
            "revenue_guidance",
            f"{company_name} discussed FY2024 revenue guidance, actual revenue, and the need to reconcile guidance to reported results.",
        ),
        (
            "Question and Answer / Analyst",
            "risk_exposure",
            f"Analysts asked {company_name} about FY2024 risk exposure, supply constraints, and whether the 10-K contradicted optimism.",
        ),
    )
    transcript_text = "\n".join(text for _, _, text in turns)
    source_hash = _hash(transcript_text)
    chunks = []
    for index, (section, metric, text) in enumerate(turns):
        start = transcript_text.find(text)
        chunks.append(
            _chunk(
                chunk_type="transcript_turn",
                text=f"{section}: {text} Marker {company_index + 1}-{index + 1}.",
                ticker=ticker,
                company_name=company_name,
                source_type="transcript",
                document_id=document_id,
                section_or_page=section,
                start=start,
                end=start + len(text),
                source_hash=source_hash,
                source_url=source_url,
                metric=metric,
            )
        )
    return tuple(chunks)


def _deck_chunks(deck_fixture_path: Optional[Path]) -> Tuple[DocumentChunk, ...]:
    if deck_fixture_path is None or not deck_fixture_path.exists():
        return ()

    deck = DeckDocumentMetadata(
        document_id="NVDA:raw_investor_deck:FY2024:data_center_fixture",
        company="NVIDIA",
        ticker="NVDA",
        fiscal_year=2024,
        fiscal_quarter="FY",
        period_end_date=date(2024, 1, 28),
        publication_date=date(2024, 2, 21),
        source_url=f"fixture://{deck_fixture_path.name}",
        retrieved_at=RAW_CREATED_AT,
        version_hash=_hash(deck_fixture_path.read_bytes().decode("latin-1", errors="ignore")),
        deck_title="NVIDIA FY2024 Investor Presentation",
    )
    result = extract_deck_chart_evidence(deck, deck_fixture_path)
    source_hash = deck.version_hash
    chunks: List[DocumentChunk] = []
    for page in result.pages:
        chunks.append(
            _chunk(
                chunk_type="deck_page",
                text=page.text,
                ticker=deck.ticker,
                company_name=deck.company,
                source_type="investor_deck",
                document_id=deck.document_id,
                section_or_page=f"Page {page.page_number}",
                start=page.source_span.start,
                end=page.source_span.end,
                source_hash=source_hash,
                source_url=deck.source_url,
            )
        )
    for chart in result.chart_evidence:
        chunks.append(
            _chunk(
                chunk_type="deck_chart",
                text=chart.extracted_text,
                ticker=chart.company_ticker,
                company_name=chart.company,
                source_type="investor_deck",
                document_id=chart.document_id,
                section_or_page=f"Page {chart.page_number} / {chart.chart_title}",
                start=chart.source_span.start,
                end=chart.source_span.end,
                source_hash=source_hash,
                source_url=deck.source_url,
                metric=chart.metric,
                numeric_value=chart.numeric_value,
                unit=chart.unit,
                currency=chart.currency,
            )
        )
    return tuple(chunks)


def _chunk(
    chunk_type: str,
    text: str,
    ticker: str,
    company_name: str,
    source_type: str,
    document_id: str,
    section_or_page: str,
    start: int,
    end: int,
    source_hash: str,
    source_url: str,
    metric: Optional[str] = None,
    numeric_value: Optional[Decimal] = None,
    unit: Optional[str] = None,
    currency: Optional[str] = None,
) -> DocumentChunk:
    safe_start = max(start, 0)
    safe_end = max(end, safe_start + 1)
    chunk_hash = _hash("|".join((document_id, chunk_type, section_or_page, text, str(metric or ""))))
    chunk_id = f"raw:{source_type}:{ticker}:FY2024:{chunk_type}:{chunk_hash[:12]}"
    return DocumentChunk(
        chunk_id=chunk_id,
        chunk_type=chunk_type,
        text=text,
        provenance=ChunkProvenance(
            company_ticker=ticker,
            company_name=company_name,
            source_type=source_type,
            document_id=document_id,
            fiscal_period="FY2024",
            section_or_page=section_or_page,
            source_span_start=safe_start,
            source_span_end=safe_end,
            source_hash=source_hash,
            source_url=source_url,
        ),
        chunk_hash=chunk_hash,
        normalized_metric=metric,
        numeric_value=numeric_value,
        unit=unit,
        currency=currency,
    )


def _section_metric(section: str) -> Optional[str]:
    if section == "Item 7 - MD&A":
        return "revenue"
    if section == "Item 1A - Risk Factors":
        return "risk_exposure"
    if section == "Item 8 - Financial Statements":
        return "revenue"
    return None


def _manifest(chunks: Tuple[DocumentChunk, ...], source_document_count: int) -> CorpusVersionManifest:
    source_counts = _counts(chunk.provenance.source_type for chunk in chunks)
    chunk_type_counts = _counts(chunk.chunk_type for chunk in chunks)
    company_counts = _counts(chunk.provenance.company_ticker for chunk in chunks)
    fiscal_period_counts = _counts(chunk.provenance.fiscal_period for chunk in chunks)
    index_hash = _hash("|".join(chunk.chunk_hash for chunk in chunks))
    index = ChunkIndexManifest(
        corpus_id="phase11_raw_financial_document_corpus",
        chunk_count=len(chunks),
        source_type_counts=source_counts,
        chunk_type_counts=chunk_type_counts,
        company_counts=company_counts,
        fiscal_period_counts=fiscal_period_counts,
        version_hash=index_hash,
    )
    version_hash = _hash(f"{index_hash}|{source_document_count}|{len(chunks)}")
    return CorpusVersionManifest(
        corpus_id=index.corpus_id,
        corpus_mode="raw",
        created_at=RAW_CREATED_AT,
        source_document_count=source_document_count,
        chunk_count=len(chunks),
        chunk_index=index,
        version_hash=version_hash,
    )


def _counts(values: Iterable[str]) -> Mapping[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
