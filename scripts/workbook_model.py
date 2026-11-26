"""Run a single workbook policy turn using the signed-in Codex CLI."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

MODELS = ("gpt-6.2-astra", "gpt-6.2-sol")
EFFORT = "medium"
# Both tiers get the same headroom for provider backoff during rate limiting.
TIMEOUT = 600
DISABLED = (
    "shell_tool",
    "unified_exec",
    "plugins",
    "apps",
    "memories",
    "multi_agent",
    "multi_agent_v2",
    "image_generation",
)
TRANSIENT = re.compile(
    r"timeout|timed? out|connection|reconnect|stream disconnect|temporarily "
    r"unavailable|too many requests|\b(?:429|500|502|503|504)\b",
    re.I,
)


class PolicyTurnError(RuntimeError):
    """The run cannot be used as a policy turn."""


class TransportError(PolicyTurnError):
    """A transient infrastructure failure with no completed participant response."""


def engine_info():
    output = subprocess.check_output(["codex", "--version"], text=True, timeout=10)
    return {
        "cli": output.strip(),
        "effort": EFFORT,
        "disabled_features": list(DISABLED),
        "model_provenance": "explicit Codex CLI --model selection",
        "timeout_seconds": TIMEOUT,
    }


def _read_events(stdout, *, model, exit_code, diagnostic):
    thread, replies, completed, usage = None, [], False, None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event["type"]
        actual = event.get("model")
        if actual and actual != model:
            raise PolicyTurnError(f"Model changed from {model} to {actual}")
        if kind.startswith("item."):
            item = event["item"]
            if item["type"] not in ("agent_message", "reasoning"):
                raise PolicyTurnError(f"Undeclared tool or action: {item['type']}")
            if item["type"] == "agent_message" and kind == "item.completed":
                replies.append(item["text"])
        elif kind == "thread.started":
            thread = event["thread_id"]
        elif kind == "turn.completed":
            completed = True
            usage = event.get("usage")
        elif kind in ("error", "turn.failed"):
            diagnostic += "\n" + str(event.get("error", event.get("message", "")))
        elif kind != "turn.started":
            raise PolicyTurnError(f"Unrecognized Codex event: {kind}")
    if not completed or exit_code:
        if not replies and not completed and TRANSIENT.search(diagnostic):
            raise TransportError(
                "Transient CLI failure before a completed model response"
            )
        raise PolicyTurnError(f"CLI turn did not finish cleanly (exit {exit_code})")
    if not thread or len(replies) != 1:
        raise PolicyTurnError("Expected one completed message in one isolated thread")
    if (
        not isinstance(usage, dict)
        or not all(
            isinstance(v, int) and not isinstance(v, bool) and v >= 0
            for v in usage.values()
        )
        or not {"input_tokens", "output_tokens"} <= usage.keys()
    ):
        raise PolicyTurnError("Missing CLI token usage")
    return {
        "model": model,
        "model_provenance": "explicit Codex CLI --model selection",
        "thread_id": thread,
        "raw": replies[0],
        "usage": usage,
        "external_tool_calls": 0,
    }


def ask(model: str, prompt: str) -> dict:
    if model not in MODELS:
        raise ValueError(f"Model outside this study: {model}")
    with tempfile.TemporaryDirectory(prefix="workbook-policy-") as temp:
        cmd = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "-C",
            temp,
            "-s",
            "read-only",
            "-m",
            model,
            "-c",
            f'model_reasoning_effort="{EFFORT}"',
            "-c",
            'web_search="disabled"',
            "-c",
            'approval_policy="never"',
        ]
        for feature in DISABLED:
            cmd += ["--disable", feature]
        cmd += ["--json", "-"]
        retry_notices = 0
        rate_limit_notices = 0
        for attempt in (1, 2):
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    cwd=Path(temp),
                    text=True,
                    capture_output=True,
                    timeout=TIMEOUT,
                    encoding="utf-8",
                )
                # Count explicit provider retry notices only. stderr itself stays private.
                for line in result.stderr.splitlines():
                    if "retrying sampling request" in line.lower():
                        retry_notices += 1
                        rate_limit_notices += bool(re.search(r"\b429\b", line))
                record = _read_events(
                    result.stdout,
                    model=model,
                    exit_code=result.returncode,
                    diagnostic=result.stderr,
                )
            except subprocess.TimeoutExpired as exc:
                # A timeout may occur after the provider generated a response. Do not
                # treat an incomplete or unobserved stream as an unused model turn.
                raise PolicyTurnError(
                    "Timed out with uncertain response state"
                ) from exc
            except TransportError:
                if attempt == 1:
                    continue
                raise
            record["cli_retry_notices"] = retry_notices
            record["cli_429_retry_notices"] = rate_limit_notices
            record["transport_attempts"] = attempt
            return record
    raise AssertionError("unreachable")
