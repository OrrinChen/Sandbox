"""Parse and render the single-action tool-use protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Mapping

from sandboxed_agent_eval_harness.schemas import JsonDict


_TAG_RE = re.compile(r"<(tool_call|finish)>\s*(.*?)\s*</\1>", re.DOTALL)


@dataclass(frozen=True)
class ParsedAction:
    type: str
    name: str = ""
    arguments: JsonDict = field(default_factory=dict)
    final_answer: str = ""
    reported_metrics: JsonDict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "type": self.type,
            "name": self.name,
            "arguments": dict(self.arguments),
            "final_answer": self.final_answer,
            "reported_metrics": dict(self.reported_metrics),
            "error": self.error,
        }


def render_action(action: Mapping[str, Any] | ParsedAction) -> str:
    payload = action.to_dict() if isinstance(action, ParsedAction) else dict(action)
    action_type = payload.get("type")
    if action_type == "tool_call":
        body = {"name": payload.get("name", ""), "arguments": payload.get("arguments", {})}
        return "<tool_call>\n" + json.dumps(body, sort_keys=True) + "\n</tool_call>"
    if action_type == "finish":
        body = {
            "final_answer": payload.get("final_answer", ""),
            "reported_metrics": payload.get("reported_metrics", {}),
        }
        return "<finish>\n" + json.dumps(body, sort_keys=True) + "\n</finish>"
    raise ValueError(f"cannot render action type: {action_type}")


def parse_action(action: str | Mapping[str, Any] | ParsedAction) -> ParsedAction:
    if isinstance(action, ParsedAction):
        return action
    if isinstance(action, Mapping):
        return _from_mapping(action)
    if not isinstance(action, str):
        return ParsedAction(type="invalid", error="action must be a string or object")
    matches = list(_TAG_RE.finditer(action))
    if len(matches) != 1:
        return ParsedAction(type="invalid", error="expected exactly one <tool_call> or <finish> block")
    return _from_tag(matches[0].group(1), matches[0].group(2))


def parse_transcript(text: str) -> list[ParsedAction]:
    """Parse a full completion into ordered actions.

    A transcript may contain several tool calls and at most one finish, and the
    finish must be the last action. Malformed text returns a single invalid action.
    """

    if not isinstance(text, str) or not text.strip():
        return [ParsedAction(type="invalid", error="empty completion")]
    matches = list(_TAG_RE.finditer(text))
    if not matches:
        return [ParsedAction(type="invalid", error="no action tags in completion")]
    actions = [_from_tag(match.group(1), match.group(2)) for match in matches]
    if any(action.type == "invalid" for action in actions):
        return [ParsedAction(type="invalid", error="malformed action tag in completion")]
    finish_indexes = [index for index, action in enumerate(actions) if action.type == "finish"]
    if len(finish_indexes) > 1 or (finish_indexes and finish_indexes[-1] != len(actions) - 1):
        return [ParsedAction(type="invalid", error="finish must be the only terminal action and must be last")]
    return actions


def _from_mapping(payload: Mapping[str, Any]) -> ParsedAction:
    action_type = payload.get("type")
    if action_type == "tool_call":
        name = payload.get("name", payload.get("tool_name", ""))
        arguments = payload.get("arguments", {})
        if not isinstance(name, str) or not name.strip() or not isinstance(arguments, Mapping):
            return ParsedAction(type="invalid", error="tool_call requires a name and an arguments object")
        return ParsedAction(type="tool_call", name=name, arguments=dict(arguments))
    if action_type == "finish":
        final_answer = payload.get("final_answer", "")
        reported_metrics = payload.get("reported_metrics", {})
        if not isinstance(final_answer, str) or not isinstance(reported_metrics, Mapping):
            return ParsedAction(type="invalid", error="finish requires a string final_answer and a metrics object")
        return ParsedAction(
            type="finish",
            final_answer=final_answer,
            reported_metrics=dict(reported_metrics),
        )
    return ParsedAction(type="invalid", error="action type must be tool_call or finish")


def _from_tag(tag: str, body: str) -> ParsedAction:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ParsedAction(type="invalid", error=f"{tag} body is not valid JSON")
    if not isinstance(payload, dict):
        return ParsedAction(type="invalid", error=f"{tag} body must be a JSON object")
    if tag == "tool_call":
        return _from_mapping(
            {"type": "tool_call", "name": payload.get("name"), "arguments": payload.get("arguments", {})}
        )
    return _from_mapping(
        {
            "type": "finish",
            "final_answer": payload.get("final_answer", ""),
            "reported_metrics": payload.get("reported_metrics", {}),
        }
    )
