"""Run the original 65-claim study with an optional, locally stored CPU encoder."""

import argparse
import json
from hashlib import sha256
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from financial_evidence_engine.evaluation.hard_benchmark import (
    build_hard_benchmark,
    evaluate_hard_benchmark,
    render_hard_benchmark_markdown,
)
from financial_evidence_engine.production import ProductionError


def add_hard_benchmark_command(subparsers):
    parser = subparsers.add_parser(
        "hard-benchmark", help="Evaluate the 65 synthetic historical claims."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("hard-benchmark-results")
    )
    parser.add_argument(
        "--minilm-model",
        type=Path,
        metavar="LOCAL_DIRECTORY",
        help="Run the two MiniLM methods with a local all-MiniLM-L6-v2 snapshot.",
    )
    parser.add_argument(
        "--historical-canonical-boost",
        action="store_true",
        help="Reproduce the published full-engine row using its canonical-document annotation.",
    )
    parser.set_defaults(handler=run_hard_benchmark)


def run_hard_benchmark(args: argparse.Namespace):
    encoder = None
    note = "not yet run. No local MiniLM directory was supplied."
    if args.minilm_model is not None:
        model_path = args.minilm_model.resolve()
        if not (model_path / "modules.json").is_file():
            raise ProductionError(
                "missing_encoder",
                "Pass a local all-MiniLM-L6-v2 directory containing modules.json.",
            )
        weights = model_path / "model.safetensors"
        if not weights.is_file():
            raise ProductionError(
                "missing_encoder_weights",
                "The pinned MiniLM snapshot requires model.safetensors.",
            )
        digest = sha256()
        with weights.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if (
            digest.hexdigest()
            != "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db"
        ):
            raise ProductionError(
                "unexpected_encoder_weights",
                "The weights differ from the audited MiniLM snapshot.",
            )
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ProductionError(
                "missing_encoder_dependency",
                "Install sentence-transformers to run MiniLM.",
            ) from exc
        model = SentenceTransformer(
            str(model_path),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
        )

        def encoder(texts):
            return model.encode(
                list(texts), normalize_embeddings=True, show_progress_bar=False
            ).tolist()

        note = (
            f"sentence-transformers/all-MiniLM-L6-v2; weights SHA-256 {digest.hexdigest()}; sentence-transformers {version('sentence-transformers')}; "
            f"torch {version('torch')}; device cpu; normalize_embeddings=True."
        )

    benchmark = build_hard_benchmark()
    result = evaluate_hard_benchmark(
        benchmark, encoder, historical_canonical_boost=args.historical_canonical_boost
    )
    result["setup"]["dense_encoder"] = note
    result["setup"]["verdict"] += (
        " Historical replay grants full_engine a one-point canonical-document bonus."
        if args.historical_canonical_boost
        else " Active ranking and prediction receive public fields only."
    )
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    documents = [asdict(document.public()) for document in benchmark.documents]
    questions = [
        {**asdict(task.public()), "split": task.split} for task in benchmark.tasks
    ]
    labels = {
        "canonical_document_ids": [
            item.document_id for item in benchmark.documents if item.is_canonical
        ],
        "tasks": [
            {
                "task_id": task.task_id,
                "evidence": task.gold_document_ids,
                "verdict": task.expected_verdict,
            }
            for task in benchmark.tasks
        ],
    }
    for name, value in (
        ("public_documents", documents),
        ("public_questions", questions),
        ("scorer_labels", labels),
        ("hard_benchmark", result),
    ):
        (output / f"{name}.json").write_text(
            json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    (output / "hard_benchmark.md").write_text(
        render_hard_benchmark_markdown(result), encoding="utf-8"
    )
    return {
        "command": "hard-benchmark",
        "documents": len(documents),
        "tasks": len(questions),
        "splits": result["provenance"]["splits"],
        "output_dir": str(output),
        "minilm": result["methods"]["dense_minilm"]["status"],
        "historical_canonical_boost": args.historical_canonical_boost,
    }
