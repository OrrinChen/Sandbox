# Sandbox benchmarks

Sandbox exposes the evaluation harness and financial RAG benchmarks through one Python package, `sandboxed-agent-eval-harness`, and one command, `sandboxed-agent-eval`. The table identifies the unit of evaluation for each result.

| Study | What was compared | Recorded outcome |
| --- | --- | --- |
| Independent tool use | Direct and self-checked submissions on 500 held-out tasks from 284 source groups. The 100 development tasks come from 56 disjoint groups. SQL queries, Python repairs and spreadsheet formulas run against held-out data. | Direct 469/500, self-check 465/500. Both missed 30 tasks, all workbooks. [Report and paired results](scripts/independent_600/summary_zh.md) |
| Workbook access | A 100-task subset of the independent test set. Each model got the same starting cells, two inspection rounds and at most four read-only lookups per task. In one condition the search covered the initial excerpt, in the other it covered the public workbook. | Fixed excerpt / full workbook passes were Sol 65/67, Terra 76/76 and Luna 44/55, each out of 100. None of Luna's 16 full-view-only passes returned a new nonempty cell on that task. Each condition was run once. [Three-model report](scripts/workbook_access/luna_complete/results/summary_zh.md) · [Per-task decisions and lookup records](scripts/workbook_access/luna_complete/results/per_workbook_pairs.csv) |
| A1 financial RAG regression | 60 questions, 482 fixture chunks and five retrieval methods. Each method returns up to five chunks. Only the scorer reads the labels. | One of 300 task-method combinations passed the original strict checks. The source corpus covers 140 of 200 labeled evidence requirements. [Installed-wheel replay receipt](scripts/independent_600/legacy_a1_wheel_replay.json) |
| Synthetic financial RAG | 120 development and 480 frozen test questions grouped by issuer and source document. Additional splits evaluate broader search scopes and questions requiring two sources. | Reports give same-question retrieval, citation and answer metrics. The structured-operand and text-only reader comparison uses the same top five retrieved passages. [Packaged benchmarks](src/sandboxed_agent_eval_harness/benchmarks/financial_benchmark/) |
| Historical early warning | 108 formal issuers over 20 quarters. Text, revenue-trend and combined readers committed alerts ahead of the target fiscal quarter. | Of 2,160 scheduled observations, 1,629 could be scored, with 52 distinct eligible declines. The combined reader caught 24, versus 16 for text and six for trend, with 164, 112 and 108 false alerts respectively. [Preregistered protocol](scripts/t30_watch/protocol.json) · [Full historical report](scripts/t30_watch/formal/results/summary_zh.md) |

The original 64-task harness study uses five recorded behavior profiles. Its validator comparison and the Agentic RL environment are documented in the [main README](README.md). The earlier stand-alone Financial Evidence Engine includes its own claim-verification demo and a separate 65-claim hard retrieval set. [Original project snapshot](https://github.com/OrrinChen/multimodal_FEE/tree/bf52440cc3f36b898a0c69ab5d0b25f5a5cea8f8)

## Offline reproduction

Run the following from the repository root. For the published independent and workbook results, install the exact wheel used for grading into a fresh environment. Its SHA-256 is `59ca9397dbae0d95a4c179fd6b92ecb1ac886c47af164a0d4f5664aece96009a`. [Archived wheel](artifacts/independent-600-wheel/sandboxed_agent_eval_harness-0.1.0-py3-none-any.whl)

```bash
bench_venv="$(mktemp -d)/venv"
python3.11 -m venv "$bench_venv"
wheel=artifacts/independent-600-wheel/sandboxed_agent_eval_harness-0.1.0-py3-none-any.whl
"$bench_venv/bin/python" -m pip install --no-index --no-deps "$wheel"
"$bench_venv/bin/sandboxed-agent-eval" independent-benchmark verify
"$bench_venv/bin/sandboxed-agent-eval" independent-benchmark list --split dev
"$bench_venv/bin/sandboxed-agent-eval" rag-benchmark --output-dir artifacts/a1-replay
"$bench_venv/bin/sandboxed-agent-eval" financial-benchmark --split test --compare-readers --output-dir artifacts/financial-readers
```

For the synthetic stress tests, select `--split challenge` or `--split cross_source_test` on the last command. Each run writes the scores and execution traces under its output directory. The A1 regression grades the reader's answer and citations; replay checks whether re-executing the trace reproduces the verdict.

To regrade the 500 independent tasks, install LibreOffice Calc locally and make `soffice` available on `PATH`. Python repairs run under macOS `sandbox-exec` or Linux `bubblewrap`. Network-denied wheel grading on Linux also requires permission to create an unprivileged user and network namespace with `unshare`. The host Python used by the workbook tools needs `openpyxl` (the recorded version is 3.1.5). With these prerequisites installed:

```bash
PYTHONPATH=src python3 scripts/verify_independent_recordings.py --out scripts/independent_600/comparison --installed-python "$bench_venv/bin/python"
PYTHONPATH=src python3 scripts/run_workbook_access_luna_complete.py verify
PYTHONPATH=src python3 scripts/score_workbook_luna.py --wheel "$wheel"
```

The first command checks both submissions on each of 500 tasks. The next two replay Luna's queries and grade the sealed comparison. The installed wheel reproduces the 600 previous workbook verdicts, scores 200 Luna submissions and re-executes all 101 Luna failures. These commands use saved model responses. New model calls are only needed to collect a new study.

## Task sources and licenses

Sandbox's own software is distributed under the [MIT License](LICENSE). The repository also contains third-party material with its own terms.

- **SpreadsheetBench.** Zeyao Ma, Bohan Zhang, Jing Zhang, Jifan Yu, Xiaokang Zhang, Xiaohan Zhang, Sijia Luo, Xi Wang and Jie Tang created the dataset. Shortcut.AI / Fundamental Research Labs contributed the verified subset. Sandbox selected 120 formula-edit tasks, projected cells, added grading material, and recorded workbook excerpts and returned cells alongside model outputs. The adapted fixtures and those reproduced questions, cell values and projections in the independent-study and workbook-study records are distributed under CC BY-SA 4.0. [Upstream dataset](https://huggingface.co/datasets/KAKA22/SpreadsheetBench/tree/ab0b742b0fc95b946f212d80ac7771b5531272e4) · [Attribution and changes](src/sandboxed_agent_eval_harness/benchmarks/independent/sheet_data/LICENSE.txt) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Exercism Python.** Sixty repair tasks adapt exercises from the Exercism Python track, copyright © 2021 Exercism, under MIT. Sandbox added defective starting implementations and executable grading probes. The release records the upstream exercise path for each adaptation. [Pinned upstream revision](https://github.com/exercism/python/tree/479f11b44b02337b0413e805b948491c2179615a) · [Exercism license](src/sandboxed_agent_eval_harness/benchmarks/independent/data/LICENSE.exercism.txt)

The independent release groups source problems before splitting them into development and test sets. Upstream workbooks and exercises are publicly available, so a pretrained model may already have encountered them.
