"""Credentials-gated live provider workflow for recorded fixture creation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Sequence

from sandboxed_agent_eval_harness.models import GenericHTTPModelAdapter, OpenAIResponsesAdapter
from sandboxed_agent_eval_harness.models.adapters import Transport
from sandboxed_agent_eval_harness.schemas import JsonDict
from sandboxed_agent_eval_harness.tasks import task_suite_by_name


PROMPT_VERSION = "live-provider-workflow-v1"


class LiveProviderWorkflowError(ValueError):
    """Raised when a live provider workflow request is unsafe or malformed."""


def run_live_provider_workflow(
    *,
    live: bool,
    model_provider: str = "openai",
    output_dir: Path | str = "artifacts/live_runs/manual",
    suite_name: str = "smoke",
    max_tasks: int = 1,
    max_cost_usd: float = 1.0,
    record_output: bool = False,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_key_env: Optional[str] = None,
    endpoint: Optional[str] = None,
    timeout_seconds: int = 30,
    transport: Optional[Transport] = None,
) -> JsonDict:
    if not live:
        raise LiveProviderWorkflowError("live provider workflow requires --live")
    if max_tasks <= 0:
        raise LiveProviderWorkflowError("max_tasks must be positive")
    if max_cost_usd < 0:
        raise LiveProviderWorkflowError("max_cost_usd must be non-negative")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    credential_env = _api_key_env(model_provider, api_key_env)
    resolved_key = api_key or os.environ.get(credential_env)
    if not resolved_key:
        summary = _summary(
            status="skipped",
            reason="missing_credentials",
            model_provider=model_provider,
            model=model or _default_model(model_provider),
            suite=suite_name,
            max_tasks=max_tasks,
            max_cost_usd=max_cost_usd,
            api_key_env=credential_env,
            record_count=0,
            estimated_cost_usd=0.0,
            artifacts={},
        )
        _write_json(output_path / "summary.json", summary)
        return summary

    adapter = _build_adapter(
        model_provider=model_provider,
        api_key=resolved_key,
        model=model or _default_model(model_provider),
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    suite = task_suite_by_name(suite_name)
    records: list[JsonDict] = []
    raw_records: list[JsonDict] = []
    estimated_cost = 0.0
    status = "completed"
    reason = ""

    for task in suite.tasks[:max_tasks]:
        record = adapter.generate(task)
        record_cost = float(record.get("cost", 0.0))
        estimated_cost += record_cost
        records.append(record)
        raw_records.append(
            {
                "task_id": task.task_id,
                "model_provider": model_provider,
                "model": adapter.model,
                "prompt_version": PROMPT_VERSION,
                "record": record,
            }
        )
        if estimated_cost > max_cost_usd:
            status = "cost_limit_exceeded"
            reason = "max_cost_usd_exceeded"
            break

    artifacts: JsonDict = {}
    if record_output and raw_records:
        raw_path = output_path / "raw_outputs.jsonl"
        raw_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in raw_records))
        candidate_path = output_path / "recorded_fixture_candidate.json"
        _write_json(
            candidate_path,
            _recorded_fixture_candidate(
                provider=model_provider,
                model=adapter.model,
                records=records,
            ),
        )
        artifacts["raw_outputs_jsonl"] = str(raw_path)
        artifacts["recorded_fixture_candidate_json"] = str(candidate_path)

    summary = _summary(
        status=status,
        reason=reason,
        model_provider=model_provider,
        model=adapter.model,
        suite=suite_name,
        max_tasks=max_tasks,
        max_cost_usd=max_cost_usd,
        api_key_env=credential_env,
        record_count=len(records),
        estimated_cost_usd=round(estimated_cost, 6),
        artifacts=artifacts,
    )
    _write_json(output_path / "summary.json", summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a credentials-gated live provider smoke workflow.")
    parser.add_argument("--model-provider", default="openai", choices=["openai", "generic_http"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--suite", default="smoke", choices=["smoke", "benchmark"])
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=1.0)
    parser.add_argument("--record-output", action="store_true")
    parser.add_argument("--output-dir", default="artifacts/live_runs/manual")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env")
    parser.add_argument("--endpoint")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args(argv)

    try:
        summary = run_live_provider_workflow(
            live=args.live,
            model_provider=args.model_provider,
            output_dir=args.output_dir,
            suite_name=args.suite,
            max_tasks=args.max_tasks,
            max_cost_usd=args.max_cost_usd,
            record_output=args.record_output,
            model=args.model,
            api_key_env=args.api_key_env,
            endpoint=args.endpoint,
            timeout_seconds=args.timeout_seconds,
        )
    except LiveProviderWorkflowError as exc:
        reason = "live_flag_required" if "requires --live" in str(exc) else "configuration_error"
        print(f"status=failed_closed reason={reason} message={exc}")
        return 2

    print(
        f"status={summary['status']} "
        f"reason={summary.get('reason', '')} "
        f"provider={summary['model_provider']} "
        f"records={summary['record_count']} "
        f"estimated_cost_usd={summary['estimated_cost_usd']:.6f}"
    )
    return 0


def _build_adapter(
    *,
    model_provider: str,
    api_key: str,
    model: str,
    endpoint: Optional[str],
    timeout_seconds: int,
    transport: Optional[Transport],
) -> OpenAIResponsesAdapter | GenericHTTPModelAdapter:
    if model_provider == "openai":
        return OpenAIResponsesAdapter(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
    if model_provider == "generic_http":
        if not endpoint:
            raise LiveProviderWorkflowError("generic_http provider requires --endpoint")
        return GenericHTTPModelAdapter(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
    raise LiveProviderWorkflowError(f"unknown live provider: {model_provider}")


def _api_key_env(model_provider: str, override: Optional[str]) -> str:
    if override:
        return override
    if model_provider == "openai":
        return "OPENAI_API_KEY"
    if model_provider == "generic_http":
        return "GENERIC_HTTP_API_KEY"
    raise LiveProviderWorkflowError(f"unknown live provider: {model_provider}")


def _default_model(model_provider: str) -> str:
    if model_provider == "openai":
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if model_provider == "generic_http":
        return os.environ.get("GENERIC_HTTP_MODEL", "generic-live-model")
    raise LiveProviderWorkflowError(f"unknown live provider: {model_provider}")


def _summary(
    *,
    status: str,
    reason: str,
    model_provider: str,
    model: str,
    suite: str,
    max_tasks: int,
    max_cost_usd: float,
    api_key_env: str,
    record_count: int,
    estimated_cost_usd: float,
    artifacts: JsonDict,
) -> JsonDict:
    return {
        "status": status,
        "reason": reason,
        "model_provider": model_provider,
        "model": model,
        "suite": suite,
        "max_tasks": max_tasks,
        "max_cost_usd": max_cost_usd,
        "api_key_env": api_key_env,
        "record_count": record_count,
        "estimated_cost_usd": estimated_cost_usd,
        "artifacts": dict(artifacts),
    }


def _recorded_fixture_candidate(*, provider: str, model: str, records: Sequence[JsonDict]) -> JsonDict:
    return {
        "fixture_id": f"live-{provider}-recorded-candidate",
        "source": "credentials-gated-live-provider-workflow",
        "adapters": [
            {
                "name": f"live_{provider}_recorded_candidate",
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "records": [dict(record) for record in records],
            }
        ],
    }


def _write_json(path: Path, payload: JsonDict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
