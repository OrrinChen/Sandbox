"""Model adapter primitives for real and recorded model-output studies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
import urllib.request

from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec


Transport = Callable[[str, Mapping[str, str], Mapping[str, Any], int], Mapping[str, Any]]


class ModelAdapterError(ValueError):
    """Raised when model adapter configuration or output is invalid."""


class RecordedModelAdapter:
    """Replay fixture-safe model plans captured from a previous model run."""

    def __init__(
        self,
        name: str,
        model: str,
        prompt_version: str,
        records: Sequence[Mapping[str, Any]],
    ) -> None:
        self.name = _non_empty_string(name, "name")
        self.model = _non_empty_string(model, "model")
        self.prompt_version = _non_empty_string(prompt_version, "prompt_version")
        self._records = {_record_task_id(record): _normalize_record(record) for record in records}
        if not self._records:
            raise ModelAdapterError("RecordedModelAdapter requires at least one task record")

    @classmethod
    def from_file(cls, path: Path | str, adapter_name: Optional[str] = None) -> "RecordedModelAdapter":
        adapters = load_recorded_model_adapters(path)
        if adapter_name is None:
            return adapters[0]
        for adapter in adapters:
            if adapter.name == adapter_name:
                return adapter
        raise ModelAdapterError(f"recorded adapter not found: {adapter_name}")

    def task_ids(self) -> list[str]:
        return sorted(self._records)

    def plan_for(self, task_id: str) -> JsonDict:
        try:
            return dict(self._records[task_id])
        except KeyError as exc:
            raise ModelAdapterError(f"recorded output missing task_id: {task_id}") from exc


class OpenAIResponsesAdapter:
    """Minimal OpenAI Responses API adapter with injectable transport for tests.

    The default path is opt-in and requires an API key. Project tests use the
    injectable transport path, so default validation remains network-free.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 30,
        transport: Optional[Transport] = None,
    ) -> None:
        self.api_key = _non_empty_string(api_key, "api_key")
        self.model = _non_empty_string(model, "model")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or _urllib_transport

    def generate(self, task: TaskSpec) -> JsonDict:
        payload = {
            "model": self.model,
            "input": _model_plan_prompt(task),
        }
        response = self.transport(
            f"{self.base_url}/responses",
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload,
            self.timeout_seconds,
        )
        record = _parse_model_record(response)
        record.setdefault("task_id", task.task_id)
        return _normalize_record(record)


def load_recorded_model_adapters(path: Path | str) -> list[RecordedModelAdapter]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ModelAdapterError("recorded model output fixture must contain an object")
    raw_adapters = payload.get("adapters")
    if not isinstance(raw_adapters, list) or not raw_adapters:
        raise ModelAdapterError("recorded model output fixture must define adapters")
    adapters = []
    for adapter in raw_adapters:
        if not isinstance(adapter, Mapping):
            raise ModelAdapterError("recorded adapter entries must be objects")
        adapters.append(
            RecordedModelAdapter(
                name=_non_empty_string(adapter.get("name"), "name"),
                model=_non_empty_string(adapter.get("model"), "model"),
                prompt_version=_non_empty_string(adapter.get("prompt_version"), "prompt_version"),
                records=_required_list(adapter.get("records"), "records"),
            )
        )
    return adapters


def _model_plan_prompt(task: TaskSpec) -> str:
    return "\n".join(
        [
            "Return only JSON for a tool-use plan with keys:",
            "final_answer, final_answer_passed, reported_metrics, tool_calls.",
            "tool_calls must be an array of {tool_name, arguments}.",
            f"Task id: {task.task_id}",
            f"Instruction: {task.instruction}",
            f"Available tools: {', '.join(task.available_tools)}",
            f"Visible files: {', '.join(task.visible_files) if task.visible_files else 'none'}",
        ]
    )


def _parse_model_record(response: Mapping[str, Any]) -> JsonDict:
    output_text = response.get("output_text")
    if not isinstance(output_text, str):
        output_text = _nested_output_text(response)
    if not output_text:
        raise ModelAdapterError("model response did not include output_text")
    try:
        record = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ModelAdapterError("model output_text must be JSON") from exc
    if not isinstance(record, dict):
        raise ModelAdapterError("model output JSON must be an object")
    return record


def _nested_output_text(response: Mapping[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "".join(chunks)


def _normalize_record(record: Mapping[str, Any]) -> JsonDict:
    task_id = _record_task_id(record)
    final_answer = _non_empty_string(record.get("final_answer"), "final_answer")
    tool_calls = _required_list(record.get("tool_calls"), "tool_calls")
    normalized_tool_calls = []
    for call in tool_calls:
        if not isinstance(call, Mapping):
            raise ModelAdapterError("tool_calls entries must be objects")
        normalized_tool_calls.append(
            {
                "tool_name": _non_empty_string(call.get("tool_name"), "tool_name"),
                "arguments": _optional_mapping(call.get("arguments", {}), "arguments"),
                "result": _optional_mapping(call.get("result", {}), "result"),
            }
        )
    reported_metrics = record.get("reported_metrics", {})
    if not isinstance(reported_metrics, Mapping):
        raise ModelAdapterError("reported_metrics must be an object")
    return {
        "task_id": task_id,
        "final_answer": final_answer,
        "final_answer_passed": bool(record.get("final_answer_passed", bool(final_answer))),
        "tool_calls": normalized_tool_calls,
        "reported_metrics": dict(reported_metrics),
        "turns": _non_negative_int(record.get("turns", max(1, len(normalized_tool_calls) + 1)), "turns"),
        "latency_seconds": _non_negative_float(record.get("latency_seconds", 0.0), "latency_seconds"),
        "cost": _non_negative_float(record.get("cost", 0.0), "cost"),
        "timed_out": bool(record.get("timed_out", False)),
    }


def _urllib_transport(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout_seconds: int,
) -> JsonDict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ModelAdapterError("OpenAI response must contain a JSON object")
    return data


def _record_task_id(record: Mapping[str, Any]) -> str:
    return _non_empty_string(record.get("task_id"), "task_id")


def _required_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelAdapterError(f"{field_name} must be a list")
    return list(value)


def _optional_mapping(value: Any, field_name: str) -> JsonDict:
    if not isinstance(value, Mapping):
        raise ModelAdapterError(f"{field_name} must be an object")
    return dict(value)


def _non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelAdapterError(f"{field_name} must be a non-empty string")
    return value


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ModelAdapterError(f"{field_name} must be a non-negative integer")
    return value


def _non_negative_float(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ModelAdapterError(f"{field_name} must be a non-negative number")
    return float(value)
