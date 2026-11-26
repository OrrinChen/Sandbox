"""Command line interface for the local financial evidence workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

from financial_evidence_engine.case_studies import build_portfolio_case_studies, write_case_study_artifacts
from financial_evidence_engine.demo import run_local_claim_demo
from financial_evidence_engine.evaluation import build_seed_task_set
from financial_evidence_engine.evaluation.hard_cli import add_hard_benchmark_command
from financial_evidence_engine.production import CONFIG_PROFILES, ProductionError, version_artifact
from financial_evidence_engine.reports import build_portfolio_report_package, write_portfolio_report_artifacts
from financial_evidence_engine.retrieval import (
    build_raw_financial_corpus,
    build_retrieval_corpus,
    run_real_retrieval_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the financial-evidence CLI parser."""

    parser = argparse.ArgumentParser(
        prog="financial-evidence",
        description="Local financial due-diligence evidence workflow.",
    )
    parser.add_argument("--profile", choices=tuple(CONFIG_PROFILES), default="local")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify-claim", help="Verify one local claim and emit an auditable memo summary.")
    verify.add_argument("--claim", required=True)
    verify.add_argument("--company", default="AAPL")
    verify.add_argument("--period", default="2024-FY")
    verify.set_defaults(handler=_verify_claim)

    corpus = subparsers.add_parser("build-corpus", help="Build a benchmark or raw local corpus summary.")
    corpus.add_argument("--corpus", choices=("benchmark", "raw"), default="raw")
    corpus.add_argument("--deck-pdf")
    corpus.set_defaults(handler=_build_corpus)

    evaluation = subparsers.add_parser("run-eval", help="Run local retrieval evaluation.")
    evaluation.add_argument("--corpus", choices=("benchmark", "raw"), default="benchmark")
    evaluation.set_defaults(handler=_run_eval)

    add_hard_benchmark_command(subparsers)

    cases = subparsers.add_parser("build-case-studies", help="Generate portfolio case-study artifacts.")
    cases.set_defaults(handler=_build_case_studies)

    report = subparsers.add_parser("build-report", help="Generate the portfolio report artifacts.")
    report.set_defaults(handler=_build_report)

    serve = subparsers.add_parser("serve-demo", help="Start or preview the local Streamlit demo command.")
    serve.add_argument("--dry-run", action="store_true")
    serve.add_argument("--port", type=int, default=8501)
    serve.set_defaults(handler=_serve_demo)

    return parser


def main(argv: Optional[list] = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], Mapping[str, object]] = args.handler
    try:
        payload = dict(handler(args))
        payload["profile"] = CONFIG_PROFILES[args.profile].to_dict()
        payload["network_enabled"] = CONFIG_PROFILES[args.profile].network_enabled
    except ProductionError as error:
        print(json.dumps(error.to_dict(), sort_keys=True))
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


def _verify_claim(args: argparse.Namespace) -> Mapping[str, object]:
    result = run_local_claim_demo(args.claim, args.company, args.period)
    return {
        "command": "verify-claim",
        "claim": result.claim_text,
        "company": result.company_ticker,
        "period": result.fiscal_period,
        "verdict": result.verdict,
        "evidence_count": result.evidence_count,
        "numeric_reconciliation_rows": result.numeric_reconciliation_rows,
        "api_key_required": result.api_key_required,
    }


def _build_corpus(args: argparse.Namespace) -> Mapping[str, object]:
    task_set = build_seed_task_set()
    deck_pdf = Path(args.deck_pdf) if args.deck_pdf else None
    if deck_pdf is not None and not deck_pdf.exists():
        raise ProductionError("missing_pdf", f"Investor-deck PDF does not exist: {deck_pdf}")
    if args.corpus == "raw":
        corpus = build_raw_financial_corpus(task_set, deck_fixture_path=deck_pdf)
        return {
            "command": "build-corpus",
            "corpus": "raw",
            "chunks": len(corpus.chunks),
            "version_hash": corpus.manifest.version_hash,
        }
    corpus = build_retrieval_corpus(task_set)
    return {
        "command": "build-corpus",
        "corpus": "benchmark",
        "documents": len(corpus.documents),
    }


def _run_eval(args: argparse.Namespace) -> Mapping[str, object]:
    task_set = build_seed_task_set()
    result = run_real_retrieval_evaluation(task_set, corpus_mode=args.corpus)
    return {
        "command": "run-eval",
        "corpus": args.corpus,
        "tasks": result.task_count,
        "documents": result.corpus_document_count,
        "methods": len(result.runs),
        "failure_cases": len(result.failure_cases),
    }


def _build_case_studies(args: argparse.Namespace) -> Mapping[str, object]:
    case_studies = build_portfolio_case_studies(build_seed_task_set())
    manifest = write_case_study_artifacts(case_studies)
    return {
        "command": "build-case-studies",
        "case_studies": len(case_studies),
        "json_artifacts": len(manifest.json_artifacts),
        "markdown_artifacts": len(manifest.markdown_artifacts),
    }


def _build_report(args: argparse.Namespace) -> Mapping[str, object]:
    package = build_portfolio_report_package()
    manifest = write_portfolio_report_artifacts(package)
    return {
        "command": "build-report",
        "sections": len(package.sections),
        "pages": package.page_count,
        "pdf": str(manifest.pdf_path),
        "pdf_hash": version_artifact(manifest.pdf_path).content_hash,
    }


def _serve_demo(args: argparse.Namespace) -> Mapping[str, object]:
    app = Path(__file__).resolve().with_name("streamlit_app.py")
    command = [sys.executable, "-m", "streamlit", "run", str(app), f"--server.port={args.port}"]
    if args.dry_run:
        return {
            "command": "serve-demo",
            "dry_run": True,
            "serve_command": command,
        }
    subprocess.run(command, check=True)
    return {
        "command": "serve-demo",
        "dry_run": False,
        "serve_command": command,
    }


if __name__ == "__main__":
    raise SystemExit(main())
