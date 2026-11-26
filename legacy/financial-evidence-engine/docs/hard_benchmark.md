# Hard benchmark construction

This set is separate from the 60-task, 320-document verdict benchmark. It exists because that corpus copies each claim into the passages, so recall@5 sits on the ceiling for BM25 and TF-IDF SVD.

## Provenance and license

- Construction: synthetic and labeled. `build_hard_benchmark()` in `src/financial_evidence_engine/evaluation/hard_benchmark.py` is the generator. Generator id: `hard-benchmark-v1`.
- No SEC EDGAR filing text is reproduced. No real company totals are used.
- Issuers are fictional: Arcadia Devices, Boreal Software, Cinder Compute, Dora Retail, Elan Payments, and Folding Health. Tickers ARCA, BREL, CIND, DORA, ELAN, and FOLD are labels inside this benchmark, not listings.
- Amounts are invented USD totals. Each revenue figure is within $120 million of an integer billion, and adjacent fiscal years are more than the $250 million claim tolerance apart.
- The generator, passages, and labels are part of this repository and covered by its MIT license. They are not financial statements and not investment advice.

## What is in the corpus

156 passages:

- 72 canonical filing lines (6 issuers, fiscal 2021–2024, revenue, operating income, and net income). Wording is "Net sales were 48,090 million USD...", not the claim's "about forty-eight billion" phrasing.
- Lexical traps for fiscal 2023 and 2024 revenue: a market recap that repeats the claim's wording with the prior year's amount.
- Scale traps: the same digits captioned as thousands of USD.
- Calendar-year recaps that are not the fiscal-year statement.
- Shareholder letters and market wraps that mention sales and a fiscal year without an audited total.

## What is in the questions

65 claims. The retrieval query is the claim sentence only. Company and fiscal-period fields are not appended to the query string. Those fields are available to the existing metadata reranker, as the due-diligence target.

Families:

- Paraphrased support, with the legal name kept and the amount stated in words.
- Prior-year amount asserted as the current fiscal year.
- Thousands-denominated reading asserted as the revenue total.
- Calendar-year amount asserted as the fiscal-year total.
- Multi-hop margin: operating income and revenue are in two filings; the claim says more than a fifth was kept after operating costs.
- Cross-company: one issuer's fiscal 2024 sales exceeded another's. Both filings are required.
- Missing oncology segment sales. No such passage exists. The label is `insufficient`.

Content-word overlap is higher between the paraphrase and its lexical trap than between the paraphrase and the canonical filing. The generator checks that before it returns.

## Split

`sha256(task_id)` first byte below 77 is dev (about 30 percent). The rest is test. The published hard-benchmark table is the test split only. The dev split was not used to choose a retriever, a cutoff, or a validator.

## How a verdict is produced

Labels apply `FiscalPeriodValidator` and `NumericValidator` to the canonical filings. A retriever's verdict uses the same validators on the best-ranked top-5 passage that matches company, fiscal period, and metric. Comparison and margin claims use the best-ranked extracted amounts for each required fact. `full_engine` first ranks every passage by those metadata fields, then runs the same validators. On this corpus that rank places the canonical filing first, so its verdict agreement is a check of the index plus the validators, not a text-ranking score.

Recall and nDCG use grade 2 for each required canonical filing and grade 0 otherwise. Tasks with no required filing (the missing-fact family) are left out of recall and nDCG and kept in verdict accuracy.
