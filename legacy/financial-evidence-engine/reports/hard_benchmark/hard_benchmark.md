# Hard benchmark

Status: `ran`

This benchmark is separate from the 60-task verdict numbers.

- Generator: `hard-benchmark-v1`
- Construction: `synthetic-and-labeled`
- Real filings used: `False`
- Documents: `156`
- Tasks: `65`
- Test / dev: `{'dev': 18, 'test': 47}`
- License: Benchmark generator and labels are part of this repository and covered by its MIT license. The passages are not SEC filings, not EDGAR excerpts, and not factual financial statements.
- Split: sha256(task_id) first byte < 77 is dev (about 30 percent); the remainder is test. The reported table is the test split. The dev split was not used to choose a retriever, a cutoff, or a validator.
- Query: Paraphrased claim text only. Company and fiscal-period fields are not appended to the query.
- SVD: Same TF-IDF subspace settings as the 60-task CPU run: dimension 32, min_df 2, 15 iterations.
- Reranker: Existing MetadataBoostReranker on the candidate pool, using due-diligence target company, fiscal period, sec_filing source, and metric.
- Dense encoder: ran sentence-transformers/all-MiniLM-L6-v2; sentence-transformers 6.2.0; torch 2.15.0+cpu; device cpu; normalize_embeddings=True. Weights are not committed.

Among the method's top 5 documents, keep rows whose extracted company, fiscal period, and metric match the subclaim, take the best-ranked remaining row, then run FiscalPeriodValidator and NumericValidator. Comparison and margin tasks use the best-ranked extracted amounts for each required fact. full_engine ranks the whole corpus by those metadata fields before the same validators.

Test-split metrics. Recall and nDCG are macro-averages. Verdict accuracy is correct verdicts over all test tasks.

| Method | Status | Recall@1 | Recall@5 | Recall@10 | nDCG@5 | nDCG@10 | Verdict accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | ran | `0.01136363636363636363636363636` | `0.1590909090909090909090909091` | `0.2045454545454545454545454545` | 0.0976 | 0.1156 | 18/47 = `0.3829787234042553191489361702` |
| bm25_metadata_rerank | ran | `0.01136363636363636363636363636` | `0.1818181818181818181818181818` | `0.2272727272727272727272727273` | 0.1074 | 0.1265 | 18/47 = `0.3829787234042553191489361702` |
| dense_lsa | ran | `0.06818181818181818181818181818` | `0.1818181818181818181818181818` | `0.2840909090909090909090909091` | 0.1389 | 0.1767 | 15/47 = `0.3191489361702127659574468085` |
| dense_lsa_metadata_rerank | ran | `0.1704545454545454545454545455` | `0.8181818181818181818181818182` | `1` | 0.5259 | 0.5828 | 19/47 = `0.4042553191489361702127659574` |
| dense_minilm | ran | `0` | `0.4659090909090909090909090909` | `0.8295454545454545454545454545` | 0.2057 | 0.3409 | 9/47 = `0.1914893617021276595744680851` |
| dense_minilm_metadata_rerank | ran | `0.6136363636363636363636363636` | `0.9659090909090909090909090909` | `1` | 0.8642 | 0.8774 | 33/47 = `0.7021276595744680851063829787` |
| full_engine | ran | `0.8977272727272727272727272727` | `1` | `1` | 1.0000 | 1.0000 | 47/47 = `1` |

Exact fractions and task counts are in the JSON artifact.
