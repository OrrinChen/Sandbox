"""Installed command line for the offline benchmark and replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Optional, Sequence

from sandboxed_agent_eval_harness import __version__
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.benchmark import run_benchmark, task_suite
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.data import SPLITS
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.benchmark import FinancialEvidenceBaseline, rag_task_suite
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.full_benchmark import full_task_suite, run_full_benchmark
from sandboxed_agent_eval_harness.benchmarks.financial_evidence.methods import METHODS
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tracing import TraceReplay, TraceReplayError, TraceReplayExecutionError, TraceReplayExecutor


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="sandboxed-agent-eval", description=__doc__)
    parser.add_argument("--version", action="version", version=f"sandboxed-agent-eval-harness {__version__}")
    commands = parser.add_subparsers(dest="command")
    benchmark = commands.add_parser("rag-benchmark", help="Run the bundled A1 financial evidence cases offline.")
    benchmark.add_argument("--output-dir", type=Path, default=Path("artifacts/rag-benchmark"))
    selection = benchmark.add_mutually_exclusive_group()
    selection.add_argument("--smoke", action="store_true", help="Run the original three regression cases.")
    selection.add_argument("--method", choices=METHODS, action="append", help="Run selected methods. Defaults to all five.")
    financial = commands.add_parser("financial-benchmark", help="Evaluate the frozen synthetic financial disclosure benchmark.")
    financial.add_argument("--split", choices=SPLITS, default="test")
    financial.add_argument("--output-dir", type=Path, required=True)
    financial.add_argument("--compare-readers", action="store_true", help="Compare structured and text-only readers on shared retrieval results.")
    from sandboxed_agent_eval_harness.benchmarks.independent import suite as independent
    independent.add_commands(commands.add_parser("independent-benchmark", help="Evaluate the independent tool-use task suite."))
    replay = commands.add_parser("replay", help="Re-execute a bundled benchmark trace.")
    replay.add_argument("trace", type=Path)
    replay.add_argument("--workspace", type=Path, required=True, help="Parent directory for the replay workspace.")
    args = parser.parse_args(argv)

    if args.command == "independent-benchmark":
        return independent.run(args)
    if args.command == "financial-benchmark":
        summary = run_benchmark(args.split, args.output_dir.resolve(), compare_readers=args.compare_readers)
        print(f"runs={len(summary.runs)} passed={summary.metrics['passed_count']} summary={summary.output_dir / 'summary.json'}")
        return 0
    if args.command == "rag-benchmark":
        output_dir = args.output_dir.resolve()
        if args.smoke:
            summary = run_evaluation(suite=rag_task_suite(), baselines=[FinancialEvidenceBaseline()], output_dir=output_dir)
        else:
            summary = run_full_benchmark(output_dir, tuple(dict.fromkeys(args.method)) if args.method else METHODS)
        print(f"runs={len(summary.runs)} passed={summary.metrics['passed_count']} summary={summary.output_dir / 'summary.json'}")
        return 0
    if args.command == "replay":
        try:
            args.workspace.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="rag-replay-", dir=args.workspace) as workspace:
                metadata = TraceReplay.from_jsonl(args.trace).metadata
                if metadata.get("benchmark_split") in SPLITS:
                    executor = TraceReplayExecutor(suite=task_suite(metadata["benchmark_split"]))
                else:
                    executor = TraceReplayExecutor(suite=rag_task_suite(), additional_suites=[full_task_suite()])
                result = executor.replay(args.trace, Path(workspace) / "sandbox")
        except (OSError, TraceReplayError, TraceReplayExecutionError) as exc:
            parser.exit(1, f"replay failed: {exc}\n")
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0 if result.passed else 1

    print(f"sandboxed-agent-eval-harness {__version__}")
    return 0
