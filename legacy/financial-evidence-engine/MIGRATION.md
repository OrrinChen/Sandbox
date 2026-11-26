# Using the Financial Evidence Engine in Sandbox

Sandbox packages the engine, evaluator and Streamlit app in the `sandboxed-agent-eval-harness` distribution. Existing code can still import `financial_evidence_engine`. This directory contains the evidence, reports and research commands from the former `OrrinChen/multimodal_FEE` repository. [Original release tree](https://github.com/OrrinChen/multimodal_FEE/tree/bf52440cc3f36b898a0c69ab5d0b25f5a5cea8f8)

## Install and run

From the Sandbox checkout, install the package and enter the working directory for the original research scripts. The `demo` extra supplies Streamlit for the interactive app and Pillow for the screenshot script. The `dev` extra supplies the test runner.

```bash
python3 -m pip install -e ".[dev,demo]"
cd legacy/financial-evidence-engine
financial-evidence verify-claim --claim 'Apple FY2024 revenue was $391.035 billion.'
financial-evidence build-corpus --corpus raw
financial-evidence run-eval --corpus benchmark
python3 -m streamlit run app.py
```

The installed `financial-evidence --help` lists the current commands. The original checkout commands that take relative filenames, such as `make portfolio-demo`, use the layout in this directory. The figure, table and report builders write to their original relative destinations. Use a scratch checkout when comparing the regenerated artifacts with the committed reports.

## Reproduce prior experiments

| Task | Command or reference |
| --- | --- |
| Claim, corpus, evaluation, case studies, report and GUI CLI smoke checks | `python3 scripts/smoke_cli_workflow.py` |
| Graph, source extraction, normalization, numeric reconciliation and memo checks | [Individual smoke commands](VALIDATION.md) |
| Screenshot and data-platform pipeline | `make portfolio-demo` |
| Case-level traces, including SQLite replay | `python3 scripts/smoke_trace_reproducibility.py` |
| 60-task CPU retrieval experiment | `make dense-lsa` |
| 65-claim study with an 18-claim development split and a 47-claim test split | `python3 scripts/run_hard_benchmark.py --json-out /tmp/fee-hard.json --markdown-out /tmp/fee-hard.md` |
| 120 adversarial tasks and missed cases | `python3 scripts/smoke_adversarial_evaluation.py` |
| Historical test suite | `python3 -m pytest tests` |

The archived MiniLM run recorded `sentence-transformers==6.2.0`, `torch==2.15.0+cpu` and the model ID `sentence-transformers/all-MiniLM-L6-v2`. Its weights were downloaded at run time. The archive contains the metrics and runtime description but no weights or model revision hash. For a new neural run, install the root `dense` extra, make the model available locally and set `FINANCIAL_EVIDENCE_ENABLE_LOCAL_EMBEDDINGS=1`. The 65-claim runner accepts `--json-out` and `--markdown-out` so that new results can be saved separately. [Archived MiniLM settings](experiments/dense_sentence_transformer/dense_sentence_transformer_rerank_ablation.json) · [65-claim results](reports/hard_benchmark/hard_benchmark.md)

## Source and artifact map

| Former location | Location in this repository |
| --- | --- |
| `src/financial_evidence_engine/` | [Canonical import package](../../src/financial_evidence_engine/) |
| `app.py`, `tests/` and `tests/fixtures/` | [App launcher](app.py) and [tests and fixtures](tests/) |
| `configs/` and `scripts/` | [Configuration](configs/) and [research scripts](scripts/) |
| `experiments/` | [Recorded evaluations and SQLite trace](experiments/) |
| `reports/`, `docs/` and `PORTFOLIO.md` | [Published tables and reports](reports/), [documentation](docs/) and [portfolio summary](PORTFOLIO.md) |
| `pyproject.toml` and `.github/workflows/ci.yml` | [Active package metadata](../../pyproject.toml) and [repository CI](../../.github/workflows/). Original metadata and workflow are retained in [upstream](upstream/). |
| `LICENSE` | [Original MIT notice](LICENSE) |

The inventory maps all 194 tracked files in the final upstream revision to their locations here and records their original Git blob hashes. A hash identifies the original bytes, including for files adapted to the unified installation. [File inventory](upstream/files.json)
