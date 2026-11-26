from dataclasses import replace
import json
from pathlib import Path

from financial_evidence_engine.cli import main
from financial_evidence_engine.evaluation.hard_benchmark import (
    HardBenchmark,
    build_hard_benchmark,
    evaluate_hard_benchmark,
)

ARCHIVE = (
    Path(__file__).resolve().parents[1]
    / "legacy"
    / "financial-evidence-engine"
    / "experiments"
    / "hard_benchmark"
    / "hard_benchmark.json"
)


def test_active_rankings_and_verdicts_ignore_frozen_labels_and_canonical_flags():
    original = build_hard_benchmark()
    altered = HardBenchmark(
        tuple(replace(d, is_canonical=not d.is_canonical) for d in original.documents),
        tuple(
            replace(
                t,
                expected_verdict="perturbed",
                gold_document_ids=(),
                family="perturbed",
                lexical_trap_id="perturbed",
                left_should_exceed=False,
                margin_should_exceed=False,
            )
            for t in original.tasks
        ),
    )
    first = evaluate_hard_benchmark(original)
    second = evaluate_hard_benchmark(altered)
    assert first["predictions"] == second["predictions"]
    assert first["methods"]["full_engine"]["test"]["verdict_correct"] == 47
    assert second["methods"]["full_engine"]["test"]["verdict_correct"] == 0
    for method, rows in first["predictions"].items():
        assert len(rows) == (0 if method.startswith("dense_minilm") else 65)
    assert not hasattr(original.documents[0].public(), "is_canonical")
    for private in (
        "expected_verdict",
        "gold_document_ids",
        "family",
        "lexical_trap_id",
        "left_should_exceed",
    ):
        assert not hasattr(original.tasks[0].public(), private)


def test_installed_command_exports_separate_inputs_and_reproduces_cpu_methods(tmp_path):
    assert main(["hard-benchmark", "--output-dir", str(tmp_path)]) == 0
    reports = {p.stem: json.loads(p.read_text()) for p in tmp_path.glob("*.json")}
    assert len(reports["public_documents"]) == 156
    assert (
        len(reports["public_questions"]) == len(reports["scorer_labels"]["tasks"]) == 65
    )
    assert all("is_canonical" not in d for d in reports["public_documents"])
    assert all("expected_verdict" not in q for q in reports["public_questions"])
    # The reference is the untouched report from the separate upstream release.
    old = json.loads(ARCHIVE.read_text())["methods"]
    methods = reports["hard_benchmark"]["methods"]
    for name, row in methods.items():
        if name.startswith("dense_minilm"):
            assert row["status"] == "not yet run"
        else:
            assert row == old[name]
    assert reports["hard_benchmark"]["setup"]["historical_canonical_boost"] is False
    assert main(["hard-benchmark", "--minilm-model", str(tmp_path / "absent")]) == 2


def test_bm25_rankings_match_across_process_hash_seeds():
    import os
    import subprocess
    import sys

    check = """
from financial_evidence_engine.evaluation.hard_benchmark import (
    _average_length, _bm25_scored, _document_frequencies, _order, _tokenize, build_hard_benchmark,
)
bench = build_hard_benchmark()
docs = [d.public() for d in bench.documents]
tokens = [_tokenize(d.text) for d in docs]
freq = _document_frequencies(tokens)
length = _average_length(tokens)
for task in bench.tasks:
    print(_order(_bm25_scored(task.public(), docs, tokens, freq, length)))
"""
    src = str(Path(__file__).resolve().parents[1] / "src")
    outcomes = [
        subprocess.check_output(
            [sys.executable, "-c", check],
            env={**os.environ, "PYTHONPATH": src, "PYTHONHASHSEED": seed},
        )
        for seed in ("1", "31")
    ]
    assert outcomes[0] == outcomes[1]
