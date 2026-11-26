"""Fresh Luna workbook recording using the CLI's official final-message output."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

import run_workbook_access_luna as luna

host = luna.host
MODEL = luna.MODEL
DEFAULT_ROOT = host.STUDY / "luna_complete"
INCIDENT_SHA = "04c26ed1afefa2253dcfdbe420ec5c3c8deb90533af3bd24a5d04f699ee1f157"


def registration(root, create=False):
    if root.resolve().is_relative_to(luna.DEFAULT_ROOT.resolve()) or any(
        root.resolve().is_relative_to(p.resolve())
        for p in (luna.PARENT, luna.paired.MID, luna.shared.PARENT)
    ):
        raise ValueError("Use a separate fresh Luna study directory")
    incident = luna.DEFAULT_ROOT / "collection_incident.json"
    if host.digest(incident) != INCIDENT_SHA:
        raise ValueError("Stopped Luna campaign incident changed")
    old = host.load(incident)
    if (
        host.digest(luna.DEFAULT_ROOT / "registration.json")
        != old["registration_sha256"]
    ):
        raise ValueError("Stopped Luna campaign registration changed")
    for category in ("prior_accepted_turns_sha256", "prior_completed_batches_sha256"):
        for name, expected in old[category].items():
            if host.digest(luna.DEFAULT_ROOT / name) != expected:
                raise ValueError(f"Stopped Luna campaign artifact changed: {name}")
    # Import public input packets and the engine identity directly from the paired
    # study. No turn or submission file is copied into the new study directory.
    cfg = luna.registration(luna.DEFAULT_ROOT)
    if create:
        import openpyxl

        if host.load(luna.PARENT / "engine.json") != {
            **luna.shared.engine.engine_info(),
            "openpyxl": openpyxl.__version__,
        }:
            raise ValueError("Formal model runtime changed")
    for name in [
        Path("engine.json"),
        *(Path("inputs") / f"{batch}.json" for batch in cfg["groups"]),
    ]:
        luna.shared.checked_copy(luna.PARENT / name, root / name, create)
    cfg = {
        **cfg,
        "version": "workbook-access-luna-official-final-v1",
        "stopped_luna_incident_sha256": INCIDENT_SHA,
        "official_final_driver_sha256": host.digest(Path(__file__)),
        "selection": "Fresh complete study of all 100 workbooks in both arms. The "
        "stopped campaign contributes zero turns and zero submissions. The official "
        "codex exec --output-last-message file must match the last completed public "
        "assistant message. Earlier public messages are archived without using their "
        "contents to choose a response. All other runtime, inspection and submission "
        "rules match the frozen parent. No content-based retries. Failed final slots "
        "are graded as missing. Seal the full campaign before Luna scoring.",
    }
    luna.shared.bound(root / "registration.json", cfg, create)
    return cfg


def event_receipt(stdout, cli_final, exit_code):
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors="replace")
    receipt = {
        "exit_code": exit_code,
        "thread_ids": [],
        "items": [],
        "completed_usage": [],
        "cli_final": cli_final,
        "external_tool_events": [],
        "error_events": 0,
    }
    for line in (stdout or "").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            kind = event["type"]
        except (TypeError, ValueError, KeyError):
            receipt["error_events"] += 1
            continue
        if kind == "thread.started":
            receipt["thread_ids"].append(event.get("thread_id"))
        elif kind == "turn.completed":
            receipt["completed_usage"].append(event.get("usage"))
        elif kind.startswith("item."):
            item = event["item"]
            typ = item.get("type")
            if typ not in ("agent_message", "reasoning"):
                receipt["external_tool_events"].append({"event": kind, "item": typ})
            if kind == "item.completed":
                entry = {"type": typ, "phase": item.get("phase")}
                if typ == "agent_message":
                    entry["text"] = item.get("text")
                receipt["items"].append(entry)
        elif kind in ("error", "turn.failed"):
            receipt["error_events"] += 1
    return receipt


def final_event_stream(stdout, official, error_type):
    """Select by the CLI-defined final position only; preserve every non-message event."""
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    positions = [
        i
        for i, e in enumerate(events)
        if e["type"] == "item.completed" and e["item"]["type"] == "agent_message"
    ]
    if not positions or official is None:
        raise error_type("Official final output or final assistant event is missing")
    final = events[positions[-1]]["item"]["text"]
    if official not in (final, final + "\n"):
        raise error_type("Official output disagrees with the final assistant event")
    # An unexpected model marker may occur on an earlier public message. Keep
    # it in the original adapter's model consistency checks during normalization.
    selected = []
    for i, e in enumerate(events):
        if i not in positions[:-1]:
            selected.append(e)
        elif e.get("model"):
            selected.append({"type": "turn.started", "model": e["model"]})
    return "\n".join(json.dumps(e) for e in selected)


def capture(prompt):
    engine = luna.shared.private_copy(luna.shared.engine)
    engine.MODELS = (MODEL,)
    strict = engine._read_events
    attempts = []
    with tempfile.TemporaryDirectory(prefix="luna-host-final-") as temp:
        output = Path(temp) / "final.txt"

        def run(cmd, **kwargs):
            output.unlink(missing_ok=True)
            args = [*cmd[:-1], "--output-last-message", str(output), cmd[-1]]
            try:
                result = subprocess.run(args, **kwargs)
            except subprocess.TimeoutExpired as exc:
                attempts.append(event_receipt(exc.stdout, None, None))
                raise
            official = output.read_text(encoding="utf-8") if output.is_file() else None
            attempts.append(event_receipt(result.stdout, official, result.returncode))
            return result

        def parse(stdout, *, model, exit_code, diagnostic):
            # Transport errors retain the frozen client's retry decision. A completed
            # response is never rerun because its formatting or contents disappoint.
            if exit_code == 0 and attempts[-1]["completed_usage"]:
                if (
                    len(attempts[-1]["thread_ids"]) != 1
                    or len(attempts[-1]["completed_usage"]) != 1
                ):
                    raise engine.PolicyTurnError(
                        "Expected one completed turn and one thread"
                    )
                stdout = final_event_stream(
                    stdout, attempts[-1]["cli_final"], engine.PolicyTurnError
                )
            return strict(
                stdout, model=model, exit_code=exit_code, diagnostic=diagnostic
            )

        engine.subprocess = SimpleNamespace(
            run=run, TimeoutExpired=subprocess.TimeoutExpired
        )
        engine._read_events = parse
        try:
            response = engine.ask(MODEL, prompt)
        except (engine.PolicyTurnError, ValueError, KeyError) as exc:
            completed = any(a["completed_usage"] for a in attempts)
            return {
                "status": "protocol_rejected" if completed else "infrastructure_error",
                "diagnostic": str(exc),
                "attempts": attempts,
            }
    return {"status": "accepted", "response": response, "attempts": attempts}


def slot_summary(saved):
    item = {k: saved["binding"][k] for k in ("arm", "batch", "stage")}
    attempts = saved["cli_events"]
    ids = [i for a in attempts for i in a["thread_ids"]]
    usages = [u for a in attempts for u in a["completed_usage"] if isinstance(u, dict)]
    count = sum(i["type"] == "agent_message" for a in attempts for i in a["items"])
    return {
        **item,
        "status": saved["status"],
        "usage": usages[0] if len(usages) == 1 else None,
        "thread_id": ids[-1] if ids else None,
        "message_count": count,
    }


def collector():
    runner = luna.shared.private_copy(host)

    def turn(root, batch, model, arm, stage, prompt, allow_record):
        name = host.NAMES[stage]
        path = root / "turns" / model / arm / batch / (name + ".json")
        binding = {
            "model": model,
            "arm": arm,
            "batch": batch,
            "stage": name,
            "prompt_sha256": host.text_hash(prompt),
            "registration_sha256": host.digest(root / "registration.json"),
        }
        if not path.exists() and allow_record:
            intent = root / "call_intents" / arm / batch / (name + ".json")
            if intent.exists():
                if host.load(intent) != binding:
                    raise ValueError("Interrupted Luna intent has a different prompt")
                item = {"status": "interrupted_unknown", "attempts": []}
            else:
                host.seal(intent, binding)
                item = capture(prompt)
            saved = {
                "binding": binding,
                "status": item["status"],
                "cli_events": item["attempts"],
            }
            if item["status"] == "accepted":
                saved["response"] = item["response"]
            elif "diagnostic" in item:
                saved["diagnostic"] = item["diagnostic"]
            host.seal(path, saved)
        saved = host.load(path)
        if (
            saved["binding"] != binding
            or host.load(root / "call_intents" / arm / batch / (name + ".json"))
            != binding
        ):
            raise ValueError("Luna turn is not bound to this prompt")
        if saved["status"] == "accepted":
            data = saved["cli_events"][-1]
            messages = [
                i["text"] for i in data["items"] if i["type"] == "agent_message"
            ]
            resp = saved["response"]
            if (
                not messages
                or data["cli_final"] not in (messages[-1], messages[-1] + "\n")
                or resp["raw"] != messages[-1]
                or data["thread_ids"] != [resp["thread_id"]]
                or data["completed_usage"] != [resp["usage"]]
                or data["exit_code"] != 0
                or any(a["external_tool_events"] for a in saved["cli_events"])
            ):
                raise ValueError(
                    "Official final, provider receipt or tool isolation diverged"
                )
            return host.round_record(root, batch, model, arm, stage, prompt, False)
        if saved["status"] not in (
            "protocol_rejected",
            "infrastructure_error",
            "interrupted_unknown",
        ):
            raise ValueError("Unknown Luna turn status")
        return {"raw": "", "usage": slot_summary(saved)["usage"] or {}}, host.digest(
            path
        )

    runner.round_record = turn
    return runner


def accounting(root, cfg):
    slots = [
        slot_summary(
            host.load(root / "turns" / model / arm / batch / (stage + ".json"))
        )
        for (batch, _), model, arm in host.jobs(cfg)
        for stage in host.NAMES
    ]
    ids = [s["thread_id"] for s in slots if s["thread_id"]]
    if len(slots) != 150 or len(ids) != len(set(ids)):
        raise ValueError("Luna stage missing or thread reused")
    return {"slots": slots}


def lock(root, cfg):
    return {
        **host.lock_value(root, cfg),
        "collection_accounting_sha256": host.digest(
            root / "collection_accounting.json"
        ),
    }


def record(root):
    cfg = registration(root, create=True)
    runner = collector()
    with ThreadPoolExecutor(max_workers=luna.shared.WORKERS) as pool:
        calls = [
            pool.submit(runner.experiment, root, group, model, arm, True)
            for group, model, arm in host.jobs(cfg)
        ]
        for call in calls:
            call.result()
    host.seal(root / "collection_accounting.json", accounting(root, cfg))
    host.seal(root / "prediction_lock.json", lock(root, cfg))
    print("Sealed 200 fresh Luna submissions", flush=True)


def verified_records(root):
    root = Path(root)
    cfg = registration(root)
    luna.shared.bound(root / "collection_accounting.json", accounting(root, cfg), False)
    luna.shared.bound(root / "prediction_lock.json", lock(root, cfg), False)
    runner = collector()
    return [
        r
        for group, model, arm in host.jobs(cfg)
        for r in runner.experiment(root, group, model, arm, False)
    ]


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("record", "verify"))
    cli.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = cli.parse_args()
    if args.action == "record":
        record(args.root)
    else:
        print(f"Verified {len(verified_records(args.root))} fresh Luna submissions")
