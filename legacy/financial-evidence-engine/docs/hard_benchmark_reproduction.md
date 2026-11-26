# Reproducing the 65-claim study

The generator creates 156 synthetic passages and 65 claims from six fictional issuers. The published split contains 18 development and 47 test claims. Every verdict uses the first five retrieved passages. The original [construction description](hard_benchmark.md), [published metrics](../experiments/hard_benchmark/hard_benchmark.json) and [published report](../reports/hard_benchmark/hard_benchmark.md) belong to the historical study. Its source is pinned to [the upstream commit](https://github.com/OrrinChen/multimodal_FEE/tree/bf52440cc3f36b898a0c69ab5d0b25f5a5cea8f8).

## Run with the installed wheel

Five methods use the standard library. This command writes the public passages, public claims, scorer labels, detailed rankings, predicted verdicts and split metrics to the specified directory.

```bash
financial-evidence hard-benchmark --output-dir output/hard-active
```

To include the two MiniLM rows, install the optional encoder and acquire its pinned public model files while online. Store the downloaded snapshot outside the repository. The original report used sentence-transformers 6.2.0 and PyTorch 2.15.0+cpu. The migration check used sentence-transformers 6.2.0 and PyTorch 2.15.0 on a macOS CPU. [Model revision](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41)

```bash
python -m pip install 'sentence-transformers==6.2.0' 'torch==2.15.0'
hf download sentence-transformers/all-MiniLM-L6-v2 \
  --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 --local-dir /tmp/minilm-benchmark \
  --include '1_Pooling/config.json' 'config.json' 'config_sentence_transformers.json' \
  'modules.json' 'model.safetensors' 'sentence_bert_config.json' 'special_tokens_map.json' \
  'tokenizer.json' 'tokenizer_config.json' 'vocab.txt'
```

With those files on disk, both runs can execute with network access disabled. Run the verification command at the unified repository root. It joins all 455 task–method pairs and checks the historical replay against the upstream metrics on both splits.

```bash
HF_HUB_OFFLINE=1 financial-evidence hard-benchmark \
  --minilm-model /tmp/minilm-benchmark --output-dir output/hard-active
HF_HUB_OFFLINE=1 financial-evidence hard-benchmark --historical-canonical-boost \
  --minilm-model /tmp/minilm-benchmark --output-dir output/hard-historical
python legacy/financial-evidence-engine/scripts/verify_hard_migration.py \
  output/hard-active output/hard-historical
```

## Interpreting the full-engine score

The historical full engine awarded one additional ranking point to a document marked canonical by the generator. The normal command ranks using public company, period, metric and source-type fields. Only the historical switch restores that point. The reranker receives public metadata and the prediction step receives the claim and five public passages. The scorer checks the predicted verdict against expected labels and computes evidence recall and nDCG from the gold document IDs. Task IDs and synthetic source types remain observable features of the historical dataset.

All 72 fixture documents marked canonical also have public source type `sec_filing`. The other 84 documents have distinct source types. This makes the full-engine result sensitive to the ease of identifying evidence from those fields. The test split has 47 verdicts and 44 cases with evidence eligible for retrieval metrics. [Migration receipt](../experiments/hard_benchmark/unified/verification.json)

The wheel reproduced every published metric for all seven methods on both splits. Across the 455 task–method pairs, the two fresh modes produced identical full-ranking hashes, top-ten lists and verdicts. Independently inverting all 156 canonical flags and perturbing every task's expected outcome and evidence IDs also preserved all 455 active predictions. The upstream archive supplies aggregate metrics for comparison. The per-task rankings were recorded in the new runs. [Active results](../reports/hard_benchmark/unified.md) · [Per-task decisions](../experiments/hard_benchmark/unified/hard_benchmark.json) · [Label perturbation check](../experiments/hard_benchmark/unified/label_isolation_check.json)
