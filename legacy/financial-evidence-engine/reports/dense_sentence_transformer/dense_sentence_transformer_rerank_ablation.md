# Dense sentence-transformer baseline

Status: `ran`

```bash
FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1 python3 scripts/run_sentence_transformer_baseline.py --config configs/dense_sentence_transformer.yaml
```

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- sentence-transformers: `6.2.0`
- torch: `2.15.0+cpu`
- Device: `cpu`
- Tasks: `60`
- Documents: `320`
- top_k: `5`
- Rerank candidate pool: up to `30`
- Embedding: sentence-transformers encode with normalize_embeddings=True, then cosine retrieval through EmbeddingEvidenceRetriever. Metadata rerank uses the existing MetadataBoostReranker on up to top_k * candidate_pool_multiplier candidates. Not the published verdict-accuracy benchmark.
- Corpus: Same constructed benchmark corpus as the published verdict benchmark: gold evidence specifications plus known distractors. Claim text is copied into both gold and distractor document text.
- Weights: Downloaded at run time from the model id above. Weights are not committed.

This ablation does not report verdict accuracy, numeric correctness, contradiction detection, unsupported-claim rate, answer faithfulness, memo usefulness, latency, or cost. Predictions are marked not_scored. The published full-engine 83.3% and BM25 66.7% figures are verdict accuracies from the existing benchmark, not outputs of this run.

Citation exactness equals evidence recall in this run because every retrieved row is marked cited.

| Method | Evidence recall@5 | Evidence recall@1 | Citation exactness | Fiscal-period correctness | Entity correctness |
| --- | --- | --- | --- | --- | --- |
| bm25 | 199/200 = `0.995` | 60/200 = `0.3` | `0.995` | `0.93` | `0.9666666666666666666666666667` |
| bm25_metadata_rerank | 199/200 = `0.995` | 60/200 = `0.3` | `0.995` | `0.93` | `0.9666666666666666666666666667` |
| dense_minilm | 192/200 = `0.96` | 50/200 = `0.25` | `0.96` | `0.91` | `0.93` |
| dense_minilm_metadata_rerank | 200/200 = `1` | 60/200 = `0.3` | `1` | `0.9366666666666666666666666667` | `0.9733333333333333333333333333` |

## Rerank deltas

Differences of the ratios above. A zero difference means the metric did not move.

- `bm25_metadata_rerank` evidence recall@5 minus `bm25` evidence recall@5 = `0`
- `bm25_metadata_rerank` evidence recall@1 minus `bm25` evidence recall@1 = `0`
- `bm25_metadata_rerank` entity correctness minus `bm25` entity correctness = `0`
- `dense_minilm_metadata_rerank` evidence recall@5 minus `dense_minilm` evidence recall@5 = `0.04`
- `dense_minilm_metadata_rerank` evidence recall@1 minus `dense_minilm` evidence recall@1 = `0.05`
- `dense_minilm_metadata_rerank` entity correctness minus `dense_minilm` entity correctness = `0.0433333333333333333333333333`
