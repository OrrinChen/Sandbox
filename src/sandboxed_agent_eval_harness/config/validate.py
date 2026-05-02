"""CLI for validating project config against runtime surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.config.project import ProjectConfigValidationError, validate_project_config


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate project config files against runtime surfaces.")
    parser.add_argument("--config-dir", type=Path, help="Directory containing project config files.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report.")
    args = parser.parse_args(argv)

    try:
        report = validate_project_config(config_dir=args.config_dir)
    except ProjectConfigValidationError as exc:
        print(f"config_validation=failed reason={exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        summary = report.to_dict()
        print(
            "config_validation=passed "
            f"tools={summary['tool_count']} "
            f"validators={summary['validator_count']} "
            f"task_suites={summary['task_suite_count']} "
            f"eval_runs={summary['eval_run_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
