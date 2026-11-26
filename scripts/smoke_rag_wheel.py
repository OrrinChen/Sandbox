"""Build and exercise the RAG benchmark wheel outside the source checkout."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
OFFLINE_PIP = ["--no-index", "--no-deps", "--no-cache-dir"]
EXPECTED_FAILURES = {"rag_retrieval_miss": 1, "rag_invalid_citation": 1}
METHODS = {"bm25", "dense_proxy", "hybrid", "graph", "full_engine"}
FINANCIAL_METHODS = METHODS | {"hybrid_verified"}
CROSS_SOURCE_METHODS = FINANCIAL_METHODS | {"hybrid_split_verified"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", type=Path, help="Directory for the verified wheel.")
    parser.add_argument("--results-dir", type=Path, help="Directory for the full evaluation report and traces.")
    parser.add_argument("--replay-all-failures", action="store_true", help="Replay every failed full benchmark trace.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--financial", action="store_true", help="Validate the 600-task financial benchmark.")
    mode.add_argument("--challenge", action="store_true", help="Validate the 240-task financial challenge split.")
    mode.add_argument("--cross-source", action="store_true", help="Validate the independent cross-source blind split.")
    mode.add_argument("--reader-comparison", action="store_true", help="Compare readers on all frozen test splits and replay every failure.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sandbox-rag-wheel-") as temporary:
        root = Path(temporary)
        source = root / "source"
        wheelhouse = root / "wheelhouse"
        environment = root / "venv"
        workdir = root / "evaluation"
        replay_dir = root / "replay"
        for directory in (source, workdir, replay_dir):
            directory.mkdir()
        for name in ("pyproject.toml", "README.md"):
            shutil.copyfile(ROOT / name, source / name)
        shutil.copytree(
            ROOT / "src",
            source / "src",
            ignore=shutil.ignore_patterns("*.egg-info", "__pycache__"),
        )

        run_env = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONNOUSERSITE": "1"}
        if os.name == "nt":
            run_env["SystemRoot"] = os.environ["SystemRoot"]
        pip_env = {
            **run_env,
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
        subprocess.run(
            [
                sys.executable, "-m", "pip", "wheel", *OFFLINE_PIP,
                "--no-build-isolation", "--wheel-dir", wheelhouse, ".",
            ],
            cwd=source,
            env=pip_env,
            check=True,
        )
        (wheel,) = wheelhouse.glob("*.whl")
        subprocess.run([sys.executable, "-m", "venv", environment], cwd=workdir, env=pip_env, check=True)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        executable_suffix = ".exe" if os.name == "nt" else ""
        python = scripts / f"python{executable_suffix}"
        cli = scripts / f"sandboxed-agent-eval{executable_suffix}"
        subprocess.run(
            [python, "-m", "pip", "install", *OFFLINE_PIP, wheel],
            cwd=workdir,
            env=pip_env,
            check=True,
        )

        if args.financial or args.challenge or args.cross_source or args.reader_comparison:
            if args.reader_comparison:
                splits = (("test", 480, 80), ("challenge", 240, 80), ("cross_source_test", 80, 80))
            elif args.cross_source:
                splits = (("cross_source_test", 80, 80),)
            elif args.challenge:
                splits = (("challenge", 240, 80),)
            else:
                splits = (("dev", 120, 20), ("test", 480, 80))
            _verify_financial(
                cli, python, workdir, replay_dir, run_env, args.results_dir, args.replay_all_failures, splits,
                compare_readers=args.reader_comparison,
            )
            if args.wheel_dir is not None:
                args.wheel_dir.mkdir(parents=True, exist_ok=True)
                print(f"wheel={shutil.copyfile(wheel, args.wheel_dir.resolve() / wheel.name)}")
            return

        full_dir = args.results_dir.resolve() if args.results_dir is not None else workdir / "results"
        subprocess.run(
            [cli, "rag-benchmark", "--output-dir", full_dir],
            cwd=workdir,
            env={**run_env, "PYTHONHASHSEED": "1"},
            check=True,
        )
        full_runs = _verify_full_results(full_dir)
        subprocess.run(
            [cli, "rag-benchmark", "--smoke", "--output-dir", "smoke"],
            cwd=workdir,
            env={**run_env, "PYTHONHASHSEED": "1"},
            check=True,
        )
        smoke_runs = _load_json(workdir / "smoke" / "summary.json")["runs"]
        if len(smoke_runs) != 3 or sum(run["passed"] for run in smoke_runs) != 1:
            raise SystemExit("Expected one passing RAG run and two failing runs.")

        full_failures = [run for run in full_runs if not run["passed"]]
        failure_by_method = {run["baseline_name"]: run for run in full_failures}
        if failure_by_method.keys() != METHODS:
            raise SystemExit("Expected an evaluated failure for every full benchmark method.")
        replay_runs = full_failures if args.replay_all_failures else list(failure_by_method.values())
        full_passes = [run for run in full_runs if run["passed"]]
        for run in full_passes:
            _verify_replay(cli, run, workdir, replay_dir, run_env)
        replayed_failures: Counter[str] = Counter()
        for run in smoke_runs:
            replayed_failures.update(_verify_replay(cli, run, workdir, replay_dir, run_env))
        if replayed_failures != EXPECTED_FAILURES:
            raise SystemExit(f"Unexpected RAG failures: {dict(replayed_failures)}")
        for run in replay_runs:
            _verify_replay(cli, run, workdir, replay_dir, run_env)

        wheel_label = wheel.name
        if args.wheel_dir is not None:
            args.wheel_dir.mkdir(parents=True, exist_ok=True)
            wheel_label = str(shutil.copyfile(wheel, args.wheel_dir.resolve() / wheel.name))
        print(
            f"wheel={wheel_label} rag_runs={len(full_runs)} failed_runs={len(full_failures)} "
            f"full_failures_replayed={len(replay_runs)} full_passes_replayed={len(full_passes)} "
            "smoke_runs=3 replay_divergences=0"
        )


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Expected the RAG CLI to write {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_financial(cli, python, workdir, replay_dir, run_env, results_dir, replay_all_failures, splits,
                      *, compare_readers=False):
    results = results_dir.resolve() if results_dir is not None else workdir / "financial"
    for split, count, companies in splits:
        cross_source = split == "cross_source_test"
        expected_methods = CROSS_SOURCE_METHODS if cross_source else FINANCIAL_METHODS
        output = results / split
        command = [cli, "financial-benchmark", "--split", split, "--output-dir", output]
        if compare_readers:
            command.append("--compare-readers")
        subprocess.run(command, cwd=workdir, env={**run_env, "PYTHONHASHSEED": "1"}, check=True)
        runs = _load_json(output / "summary.json")["runs"]
        if compare_readers:
            _verify_reader_report(output, runs, split, count, expected_methods)
        else:
            _verify_financial_report(output, runs, split, count, companies, expected_methods)
        failures = [run for run in runs if not run["passed"]]
        passed = next((run for run in runs if run["passed"]), None)
        representatives = {run["baseline_name"]: run for run in failures}
        replay_runs = failures if replay_all_failures or compare_readers else list(representatives.values())
        if failures:
            _verify_replay(cli, failures[0], workdir, replay_dir, run_env)
        if passed is not None:
            _verify_replay(cli, passed, workdir, replay_dir, run_env)
        subprocess.run(
            [python, "-s", "-c", _FINANCIAL_REPLAY, split, replay_dir, str(int(compare_readers))], cwd=replay_dir,
            env={**run_env, "PYTHONHASHSEED": "2"}, check=True, text=True,
            input=json.dumps(replay_runs),
        )
        if compare_readers:
            verification = {
                "split": split,
                "failed_run_count": len(failures),
                "failures_replayed": len(replay_runs),
                "replay_divergences": 0,
                "summary_sha256": sha256((output / "summary.json").read_bytes()).hexdigest(),
                "checks": ["tool_result", "state_diff", "regenerated_reader_answer", "validator_results"],
            }
            (output / "replay_verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        print(f"split={split} tasks={count} runs={len(runs)} passed={len(runs) - len(failures)} "
              f"failures_replayed={len(replay_runs)} replay_divergences=0", flush=True)


def _verify_financial_report(output, runs, split, count, companies, expected_methods):
    report = _load_json(output / "financial_benchmark_report.json")
    methods = Counter(run["baseline_name"] for run in runs)
    pairs = {(run["baseline_name"], run["task_id"]) for run in runs}
    comparisons = report["paired_comparisons"]
    expected_comparisons = {frozenset(pair) for pair in combinations(expected_methods, 2)}
    reported_comparisons = {frozenset((pair["left_method"], pair["right_method"])) for pair in comparisons}
    if (len(runs) != count * len(expected_methods) or len(pairs) != len(runs)
            or len({t for _, t in pairs}) != count or methods != {method: count for method in expected_methods}
            or report["split"] != split or report["task_count"] != count or report["run_count"] != len(runs)
            or report["company_group_count"] != companies or report["bootstrap_group_count"] != companies // 2
            or report["top_k"] != 5
            or report["methods"].keys() != expected_methods or len(comparisons) != len(expected_comparisons)
            or reported_comparisons != expected_comparisons
            or any(pair["paired_task_count"] != count for pair in comparisons)):
        raise SystemExit(f"Invalid installed-wheel financial benchmark report for {split}")
    candidate = report["methods"]["hybrid_verified"]
    if candidate["retrieval_method"] != "hybrid" or candidate["reader_method"] != "full_engine":
        raise SystemExit(f"Unexpected installed-wheel financial candidate policies for {split}")
    if split == "cross_source_test":
        candidate = report["methods"]["hybrid_split_verified"]
        if candidate["retrieval_method"] != "hybrid_split" or candidate["reader_method"] != "full_engine":
            raise SystemExit("Unexpected installed-wheel cross-source candidate policies")


def _verify_reader_report(output, runs, split, count, expected_methods):
    report = _load_json(output / "financial_reader_comparison.json")
    arm_names = expected_methods | {f"{method}_text_only" for method in expected_methods}
    task_ids = {run["task_id"] for run in runs}
    pairs = {(run["baseline_name"], run["task_id"]) for run in runs}
    if (len(task_ids) != count or len(pairs) != len(runs)
            or pairs != {(name, task) for name in arm_names for task in task_ids}
            or report["split"] != split or report["task_count"] != count
            or report["top_k"] != 5 or report["run_count"] != len(runs)
            or report["identical_retrieval_pair_count"] != count * len(expected_methods)
            or report["methods"].keys() != expected_methods):
        raise SystemExit(f"Invalid installed-wheel reader comparison report for {split}")
    metrics = {"strict_pass", "evidence_complete_at_5", "citation_support", "answer_correct"}
    for method, comparison in report["methods"].items():
        if (comparison["structured_baseline"] != method or comparison["text_only_baseline"] != f"{method}_text_only"
                or comparison["identical_retrieval_pair_count"] != count
                or comparison["metrics"].keys() != metrics
                or any(item["paired_task_count"] + item["not_applicable_task_count"] != count
                       for item in comparison["metrics"].values())
                or comparison["metrics"]["evidence_complete_at_5"]["structured_only"] != 0
                or comparison["metrics"]["evidence_complete_at_5"]["text_only_only"] != 0):
            raise SystemExit(f"Invalid installed-wheel reader comparison for {split}/{method}")


_FINANCIAL_REPLAY = """\
import json
from pathlib import Path
import sys
from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.benchmark import task_suite
from sandboxed_agent_eval_harness.tracing import TraceReplay, TraceReplayExecutor

executor = TraceReplayExecutor(suite=task_suite(sys.argv[1]))
for index, run in enumerate(json.load(sys.stdin)):
    trace_path = run['trace_path']
    if sys.argv[3] == '1':
        arm = 'text-only' if run['baseline_name'].endswith('_text_only') else 'structured'
        prompt_version = TraceReplay.from_jsonl(trace_path).metadata.get('prompt_version')
        if prompt_version != f'financial-benchmark-reader-comparison-{arm}-v1':
            raise SystemExit(f'Missing reader comparison prompt version in {trace_path}: {prompt_version}')
    result = executor.replay(trace_path, Path(sys.argv[2]) / sys.argv[1] / str(index))
    if not result.passed or result.replayed_tool_calls != 1 or result.validator_results != run['validator_results']:
        raise SystemExit(f"Financial replay differs for {run['trace_path']}: {result.divergences}")
"""


def _verify_full_results(output_dir: Path) -> list[dict]:
    runs = _load_json(output_dir / "summary.json")["runs"]
    report = _load_json(output_dir / "rag_report.json")
    pairs = {(run["baseline_name"], run["task_id"]) for run in runs}
    task_ids = {task_id for _, task_id in pairs}
    if len(runs) != 300 or len(task_ids) != 60 or pairs != {(method, task_id) for method in METHODS for task_id in task_ids}:
        raise SystemExit("Expected 60 distinct tasks with one run for each of the five methods.")
    if (
        report["task_count"] != 60 or report["run_count"] != 300 or report["corpus_documents"] != 482
        or report["corpus_coverage"]["evidence_requirements_total"] != 200 or report["top_k"] != 5
        or report["methods"].keys() != METHODS or any(item["task_count"] != 60 for item in report["methods"].values())
        or any(not report[key] for key in ("task_set_id", "task_version", "corpus_version", "upstream_commit"))
    ):
        raise SystemExit("The full RAG report did not describe the expected tasks, methods, or corpus.")

    for run in runs:
        trace_path = output_dir.parent / run["trace_path"]
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        tool_results = [event["payload"] for event in events if event["event_type"] == "tool_result"]
        if len(tool_results) != 1 or tool_results[0]["tool_name"] != "rag.search":
            raise SystemExit(f"Expected one completed RAG search in {trace_path}")
        result = tool_results[0]["result"]
        (score,) = run["validator_results"]
        details = score["details"]
        absent = set(details["absent_from_corpus_requirement_ids"])
        outside = set(details["outside_top_k_requirement_ids"])
        if absent & outside or absent | outside != set(details["missing_requirement_ids"]):
            raise SystemExit(f"Invalid evidence gap breakdown in {trace_path}")
        hit_ids = [hit["evidence_id"] for hit in result["hits"]]
        scores = [hit["score"] for hit in result["hits"]]
        if (
            result["method"] != run["baseline_name"] or result["corpus_version"] != report["corpus_version"]
            or result["top_k"] != 5 or not 1 <= len(hit_ids) <= 5 or len(set(hit_ids)) != len(hit_ids)
            or scores != sorted(scores, reverse=True) or any(score <= 0 for score in scores)
            or any(not hit["evidence_id"].startswith("raw:") or not hit["text"] for hit in result["hits"])
        ):
            raise SystemExit(f"Unexpected ranked RAG output in {trace_path}")
    return runs


def _verify_replay(cli: Path, run: dict, workdir: Path, replay_dir: Path, run_env: dict) -> list[str]:
    trace_path = workdir / run["trace_path"]
    result = subprocess.run(
        [cli, "replay", trace_path, "--workspace", replay_dir],
        cwd=replay_dir,
        env={**run_env, "PYTHONHASHSEED": "2"},
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"Replay command failed for {trace_path}:\n{result.stderr}{result.stdout}")
    replay = json.loads(result.stdout)
    if not replay["passed"] or replay["divergences"] or replay["replayed_tool_calls"] != 1:
        raise SystemExit(f"Trace did not replay cleanly: {trace_path}\n{result.stdout}")
    validators = replay["validator_results"]
    failures = [validator["failure_type"] for validator in validators if not validator["passed"]]
    if validators != run["validator_results"] or run["passed"] != (not failures):
        raise SystemExit(f"Replayed validator results differ for {trace_path}\n{result.stdout}")
    return failures


if __name__ == "__main__":
    main()
