"""Executable fixture-backed tool adapters."""

from __future__ import annotations

import csv
import io
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Mapping, Optional

from sandboxed_agent_eval_harness.sandbox import FileSystemSandbox, LocalWorkspaceBackend, SandboxBackendError, SandboxTimeoutError
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec
from sandboxed_agent_eval_harness.tools.registry import ToolRegistry, default_tool_registry


class ToolExecutionError(RuntimeError):
    """Raised when a fixture-backed tool cannot execute deterministically."""


class FixtureToolExecutor:
    """Execute default fixture-backed tools against local fixtures and a workspace sandbox."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        fixture_root: Optional[Path | str] = None,
        backend: Optional[LocalWorkspaceBackend] = None,
    ) -> None:
        self.registry = registry or default_tool_registry()
        self.fixture_root = Path(fixture_root) if fixture_root is not None else Path(__file__).resolve().parents[3]
        self.backend = backend or LocalWorkspaceBackend()

    @property
    def sandbox_backend_name(self) -> str:
        return self.backend.name

    def create_sandbox(self, task: TaskSpec, workspace: Path | str) -> FileSystemSandbox:
        return self.backend.create_sandbox(task, Path(workspace), fixture_root=self.fixture_root)

    def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        sandbox: FileSystemSandbox,
    ) -> JsonDict:
        validated_arguments = self.registry.validate_input(tool_name, arguments)
        if tool_name == "financial_statement.lookup":
            result = self._financial_statement_lookup(validated_arguments)
        elif tool_name == "transcript.search":
            result = self._transcript_search(validated_arguments)
        elif tool_name == "csv.read":
            result = self._csv_read(validated_arguments, sandbox)
        elif tool_name == "csv.group_metrics":
            result = self._csv_group_metrics(validated_arguments, sandbox)
        elif tool_name == "code.patch":
            result = self._code_patch(validated_arguments, sandbox)
        elif tool_name == "python.unit_tests":
            result = self._python_unit_tests(validated_arguments, sandbox)
        elif tool_name == "optimization.solve_newsvendor":
            result = self._optimization_solve_newsvendor(validated_arguments, sandbox)
        elif tool_name == "load_market_data":
            result = self._load_market_data(validated_arguments, sandbox)
        elif tool_name == "run_backtest":
            result = self._run_backtest(validated_arguments, sandbox)
        elif tool_name == "read_strategy_report":
            result = self._read_strategy_report(validated_arguments, sandbox)
        elif tool_name == "risk_check":
            result = self._risk_check(validated_arguments, sandbox)
        elif tool_name == "compare_artifacts":
            result = self._compare_artifacts(validated_arguments, sandbox)
        else:
            raise ToolExecutionError(f"no executable fixture adapter for tool: {tool_name}")
        return self.registry.validate_output(tool_name, result)

    def _financial_statement_lookup(self, arguments: Mapping[str, Any]) -> JsonDict:
        for fixture_path in sorted((self.fixture_root / "fixtures" / "finance").glob("*.json")):
            fixture = _load_json(fixture_path)
            if (
                fixture.get("ticker") == arguments["ticker"]
                and fixture.get("fiscal_year") == arguments["fiscal_year"]
                and fixture.get("statement") == arguments["statement"]
            ):
                return {
                    "ticker": fixture["ticker"],
                    "fiscal_year": fixture["fiscal_year"],
                    "statement": fixture["statement"],
                    "source": fixture["source_id"],
                    "values": dict(fixture["values"]),
                }
        raise ToolExecutionError(f"no financial statement fixture matched arguments: {dict(arguments)}")

    def _transcript_search(self, arguments: Mapping[str, Any]) -> JsonDict:
        query_terms = str(arguments["query"]).lower().split()
        for fixture_path in sorted((self.fixture_root / "fixtures" / "finance").glob("*.json")):
            fixture = _load_json(fixture_path)
            if fixture.get("ticker") != arguments["ticker"] or fixture.get("fiscal_period") != arguments["fiscal_period"]:
                continue
            matches = [
                dict(match)
                for match in fixture.get("matches", [])
                if all(term in match.get("text", "").lower() for term in query_terms)
            ]
            if matches:
                return {
                    "ticker": fixture["ticker"],
                    "fiscal_period": fixture["fiscal_period"],
                    "source": fixture["source_id"],
                    "matches": matches,
                }
        raise ToolExecutionError(f"no transcript fixture matched arguments: {dict(arguments)}")

    def _csv_read(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        rows = _read_csv_rows(sandbox.read_text(arguments["path"]))
        return {
            "path": arguments["path"],
            "columns": list(rows.fieldnames),
            "rows": len(rows.records),
        }

    def _csv_group_metrics(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        rows = _read_csv_rows(sandbox.read_text(arguments["path"]))
        metric = arguments["metric"]
        output_path = arguments["output_path"]
        if metric == "revenue":
            output = _revenue_summary(rows.records, arguments["group_by"])
        elif metric == "churn_rate":
            output = _churn_rate_summary(rows.records, arguments["group_by"])
        elif metric == "stockout_risk":
            output = _stockout_report(rows.records)
        else:
            raise ToolExecutionError(f"unsupported csv metric: {metric}")
        sandbox.write_text(output_path, output)
        return {
            "rows": max(0, len(output.splitlines()) - 1),
            "output_path": output_path,
        }

    def _code_patch(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        replacements = arguments["replacements"]
        if not isinstance(replacements, list):
            raise ToolExecutionError("code.patch replacements must be a list")
        contents = sandbox.read_text(arguments["path"])
        applied = 0
        for replacement in replacements:
            if not isinstance(replacement, Mapping):
                raise ToolExecutionError("code.patch replacement entries must be objects")
            old = replacement.get("old")
            new = replacement.get("new")
            if not isinstance(old, str) or not isinstance(new, str):
                raise ToolExecutionError("code.patch replacement old/new values must be strings")
            if old not in contents:
                raise ToolExecutionError(f"replacement text not found in {arguments['path']}: {old}")
            contents = contents.replace(old, new, 1)
            applied += 1
        sandbox.write_text(arguments["path"], contents)
        return {
            "path": arguments["path"],
            "replacements_applied": applied,
        }

    def _python_unit_tests(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        test_path = str(arguments["test_path"])
        sandbox.read_text(test_path)
        timeout_seconds = int(arguments.get("timeout_seconds", 5))
        code = f"""
import json
import pathlib
import sys
import traceback

test_path = pathlib.Path({test_path!r})
sys.path.insert(0, str(pathlib.Path.cwd() / test_path.parent))
namespace = {{}}
exec(test_path.read_text(), namespace)
tests = [
    (name, value)
    for name, value in sorted(namespace.items())
    if name.startswith("test_") and callable(value)
]
failures = []
for name, test in tests:
    try:
        test()
    except Exception:
        failures.append({{"name": name, "traceback": traceback.format_exc()}})
print(json.dumps({{"passed": not failures, "tests_run": len(tests), "failures": len(failures)}}))
"""
        try:
            completed = self.backend.run_python(code, workspace=sandbox.workspace, timeout_seconds=timeout_seconds)
        except (SandboxBackendError, SandboxTimeoutError) as exc:
            raise ToolExecutionError(str(exc)) from exc
        if completed.returncode != 0:
            return {"passed": False, "tests_run": 0, "failures": 1}
        try:
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise ToolExecutionError(f"unit test runner did not emit JSON: {completed.stdout}") from exc
        if not isinstance(payload, dict):
            raise ToolExecutionError("unit test runner JSON payload must be an object")
        return {
            "passed": bool(payload.get("passed")),
            "tests_run": int(payload.get("tests_run", 0)),
            "failures": int(payload.get("failures", 0)),
        }

    def _optimization_solve_newsvendor(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        fixture = json.loads(sandbox.read_text(arguments["path"]))
        if not isinstance(fixture, dict):
            raise ToolExecutionError("newsvendor fixture must be a JSON object")
        demand = sorted(int(value) for value in fixture["demand_scenarios"])
        underage_cost = float(fixture["underage_cost"])
        overage_cost = float(fixture["overage_cost"])
        critical_fractile = underage_cost / (underage_cost + overage_cost)
        order_quantity = demand[-1]
        for index, candidate in enumerate(demand, start=1):
            if index / len(demand) >= critical_fractile:
                order_quantity = candidate
                break
        expected_overage = sum(max(order_quantity - value, 0) for value in demand) / len(demand)
        expected_shortage = sum(max(value - order_quantity, 0) for value in demand) / len(demand)
        expected_cost = round(overage_cost * expected_overage + underage_cost * expected_shortage, 6)
        service_level = sum(1 for value in demand if value <= order_quantity) / len(demand)
        result = {
            "output_path": arguments["output_path"],
            "order_quantity": int(order_quantity),
            "service_level": float(service_level),
            "expected_cost": float(expected_cost),
            "source": str(fixture.get("source_id", "newsvendor-fixture")),
        }
        sandbox.write_text(arguments["output_path"], json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    def _load_market_data(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        artifact = _load_sandbox_json(sandbox, arguments["artifact_path"])
        rows = artifact.get("rows", [])
        columns = artifact.get("columns", [])
        if not isinstance(rows, list) or not isinstance(columns, list):
            raise ToolExecutionError("LOB artifact rows and columns must be lists")
        return {
            "artifact_id": str(artifact["artifact_id"]),
            "symbol": str(artifact["symbol"]),
            "rows": len(rows),
            "start_ts": str(artifact["start_ts"]),
            "end_ts": str(artifact["end_ts"]),
            "has_future_return_column": "future_return" in columns,
        }

    def _run_backtest(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        market_data = _load_sandbox_json(sandbox, arguments["market_data_path"])
        config = _load_sandbox_json(sandbox, arguments["config_path"])
        include_costs = bool(config.get("include_costs"))
        use_future_returns = bool(config.get("use_future_returns"))
        has_future_return = "future_return" in market_data.get("columns", [])
        lookahead_detected = use_future_returns or has_future_return
        gross_pnl = 1050.0 + (200.0 if lookahead_detected else 0.0)
        fees = 230.0 if include_costs else 0.0
        result = {
            "strategy_id": str(arguments["strategy_id"]),
            "config_id": str(config.get("config_id", "trading-config")),
            "gross_pnl": float(gross_pnl),
            "net_pnl": float(gross_pnl - fees),
            "fees": float(fees),
            "sharpe": 2.1 if lookahead_detected else 1.42,
            "max_drawdown": 0.12 if lookahead_detected else 0.071,
            "costs_included": include_costs,
            "lookahead_detected": bool(lookahead_detected),
            "output_path": str(arguments["output_path"]),
            "source": f"backtest-{config.get('config_id', 'trading-config')}",
        }
        sandbox.write_text(arguments["output_path"], json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    def _read_strategy_report(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        report = _load_sandbox_json(sandbox, arguments["report_path"])
        metrics = report.get("metrics", {})
        warnings = report.get("warnings", [])
        if not isinstance(metrics, dict) or not isinstance(warnings, list):
            raise ToolExecutionError("strategy report metrics must be an object and warnings must be a list")
        return {
            "source": str(report["source"]),
            "strategy_id": str(report["strategy_id"]),
            "recommended_strategy": str(report["recommended_strategy"]),
            "metrics": dict(metrics),
            "warnings": list(warnings),
        }

    def _risk_check(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        backtest = _load_sandbox_json(sandbox, arguments["backtest_path"])
        limits = _load_sandbox_json(sandbox, arguments["limits_path"])
        max_drawdown = float(backtest["max_drawdown"])
        limit_max_drawdown = float(limits["max_drawdown"])
        violations = []
        if max_drawdown > limit_max_drawdown:
            violations.append({"metric": "max_drawdown", "actual": max_drawdown, "limit": limit_max_drawdown})
        return {
            "passed": not violations,
            "violations": violations,
            "max_drawdown": max_drawdown,
            "limit_max_drawdown": limit_max_drawdown,
            "source": str(limits.get("source", "risk-limits-fixture")),
        }

    def _compare_artifacts(self, arguments: Mapping[str, Any], sandbox: FileSystemSandbox) -> JsonDict:
        gross = _load_sandbox_json(sandbox, arguments["gross_path"])
        cost_aware = _load_sandbox_json(sandbox, arguments["cost_aware_path"])
        gross_pnl = float(gross["gross_pnl"])
        cost_aware_pnl = float(cost_aware["net_pnl"])
        return {
            "gross_pnl": gross_pnl,
            "cost_aware_pnl": cost_aware_pnl,
            "fee_drag": round(gross_pnl - cost_aware_pnl, 6),
            "winner": "cost_aware" if cost_aware.get("costs_included") else "gross",
            "sources": [str(gross.get("source", "gross-artifact")), str(cost_aware.get("source", "cost-aware-artifact"))],
        }


class _CsvRows:
    def __init__(self, fieldnames: list[str], records: list[dict[str, str]]) -> None:
        self.fieldnames = fieldnames
        self.records = records


def _load_json(path: Path) -> JsonDict:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolExecutionError(f"could not load fixture: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(f"fixture must contain a JSON object: {path}")
    return payload


def _load_sandbox_json(sandbox: FileSystemSandbox, path: str) -> JsonDict:
    try:
        payload = json.loads(sandbox.read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolExecutionError(f"could not load sandbox JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolExecutionError(f"sandbox JSON must contain an object: {path}")
    return payload


def _read_csv_rows(contents: str) -> _CsvRows:
    reader = csv.DictReader(io.StringIO(contents))
    fieldnames = list(reader.fieldnames or [])
    records = [dict(row) for row in reader]
    if not fieldnames:
        raise ToolExecutionError("CSV fixture has no header")
    return _CsvRows(fieldnames=fieldnames, records=records)


def _revenue_summary(records: list[dict[str, str]], group_by: str) -> str:
    totals: OrderedDict[str, int] = OrderedDict()
    for row in records:
        group_value = row[group_by]
        totals[group_value] = totals.get(group_value, 0) + int(row["revenue"])
    lines = [f"{group_by},revenue"]
    lines.extend(f"{group_value},{total}" for group_value, total in totals.items())
    return "\n".join(lines) + "\n"


def _churn_rate_summary(records: list[dict[str, str]], group_by: str) -> str:
    totals: OrderedDict[str, int] = OrderedDict()
    churned: OrderedDict[str, int] = OrderedDict()
    for row in records:
        group_value = row[group_by]
        totals[group_value] = totals.get(group_value, 0) + 1
        churned[group_value] = churned.get(group_value, 0) + (1 if row["status"] == "churned" else 0)
    lines = [f"{group_by},churn_rate"]
    lines.extend(f"{group_value},{churned[group_value] / total:g}" for group_value, total in totals.items())
    return "\n".join(lines) + "\n"


def _stockout_report(records: list[dict[str, str]]) -> str:
    at_risk = [
        row
        for row in records
        if int(row["on_hand"]) < int(row["reorder_point"])
    ]
    lines = ["sku,on_hand,reorder_point"]
    lines.extend(f"{row['sku']},{row['on_hand']},{row['reorder_point']}" for row in at_risk)
    return "\n".join(lines) + "\n"
