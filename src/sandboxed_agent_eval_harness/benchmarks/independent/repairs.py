"""Grade a Python repair on input-only probes, keeping expected results in the parent."""

import functools
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

DATA = Path(__file__).parent / "data"
PACKAGE = Path(__file__).resolve().parents[2]
WORKER = r"""
import collections, contextlib, datetime, json, math, os, re, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
sys.path.insert(0, os.getcwd())
def encode(x):
    if x is None or type(x) in (bool,int,str): return x
    if isinstance(x,float): return round(x,7) if math.isfinite(x) else str(x)
    if isinstance(x,(datetime.date,datetime.time,datetime.timedelta)): return [type(x).__name__,str(x)]
    if isinstance(x,dict):
        return ['dict',sorted([[encode(k),encode(v)] for k,v in x.items()],key=repr)]
    if isinstance(x,(set,frozenset)): return ['set',sorted([encode(i) for i in x],key=repr)]
    if isinstance(x,(list,tuple)): return [type(x).__name__,[encode(i) for i in x]]
    if type(x).__name__ in ('generator','map','zip','filter'): return ['list',[encode(i) for i in x]]
    raise ValueError('unsupported result type')
def observe(probe):
    mode = probe.get('observe') if isinstance(probe, dict) else None
    source = probe['source'] if mode else probe
    scope={}
    try:
        exec(source,scope)
        answer = scope['answer']
        if mode == 'boolean_identity':
            return ['boolean', type(answer) is bool, encode(answer)]
        return ['value', encode(answer)]
    except Exception as error:
        result = ['error', type(error).__name__]
        if mode == 'error_argument':
            result.append(error.args[0] if error.args and isinstance(error.args[0], str) else None)
        elif mode == 'error_argument_text':
            result.append(str(error.args[0]) if error.args else None)
        elif mode == 'error_has_message':
            result.append(bool(re.search('.+', str(error))))
        return result
# Execute probes and keep subject.py diagnostics out of the result stream.
with contextlib.redirect_stdout(sys.stderr):
    outputs=[observe(probe) for probe in json.load(sys.stdin)]
sys.stdout.write(json.dumps(outputs,allow_nan=False))
"""


@functools.lru_cache(maxsize=2)
def index(private=False):
    path = DATA / ("repair_keys.json" if private else "repair_tasks.json")
    return {r["task_id"]: r for r in json.loads(path.read_bytes())}


def records():
    return [
        {k: v for k, v in row.items() if k != "starter"} for row in index().values()
    ]


def run_reference(task_id):
    return index(True)[task_id]["reference"]


def run_negative(task_id):
    return index()[task_id]["starter"]


def materialize(task_id, directory):
    r = index()[task_id]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "subject.py").write_text(r["starter"])
    (directory / "task.json").write_text(
        json.dumps({k: v for k, v in r.items() if k != "starter"}, indent=2)
    )


def isolated_command(directory):
    directory = directory.resolve()
    if platform.system() == "Darwin" and Path("/usr/bin/sandbox-exec").exists():
        # Only the submitted module, the interpreter and system libraries are readable.
        profile = (
            "(version 1)(deny default)(allow process-exec)(allow sysctl-read)"
            "(allow mach-lookup)(allow signal (target self))(allow file-read-metadata)"
            '(allow file-read* (literal "/")(subpath "/System")(subpath "/usr")(subpath "/Library/Apple")'
            '(subpath "/Library/Developer/CommandLineTools")(subpath "/private/var/db/timezone")'
            '(literal "/dev/null")(literal "/dev/urandom")(subpath '
            + json.dumps(str(directory))
            + "))(deny file-read* (subpath "
            + json.dumps(str(PACKAGE))
            + "))"
        )
        return [
            "/usr/bin/sandbox-exec",
            "-p",
            profile,
            "/usr/bin/python3",
            "-I",
            "-B",
            "-S",
            "-c",
            WORKER,
        ]
    if platform.system() == "Linux" and shutil.which("bwrap"):
        command = [
            "bwrap",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--ro-bind",
            "/usr",
            "/usr",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--ro-bind",
            str(directory),
            "/work",
            "--chdir",
            "/work",
        ]
        for root in ("/bin", "/lib", "/lib64", "/usr/local"):
            if os.path.exists(root):
                command.extend(["--ro-bind", root, root])
        if any(
            PACKAGE.is_relative_to(Path(root))
            for root in ("/usr", "/bin", "/lib", "/lib64")
        ):
            # A system-wide wheel can put the scorer inside a runtime mount.
            command.extend(["--tmpfs", str(PACKAGE)])
        return command + ["python3", "-I", "-B", "-S", "-c", WORKER]
    raise RuntimeError(
        "Python submissions require macOS sandbox-exec or Linux bubblewrap"
    )


def invoke(code, probes, *, calibration_control=False):
    if not isinstance(code, str) or len(code) > 100_000:
        return None
    with tempfile.TemporaryDirectory(prefix="independent-repair-") as folder:
        directory = Path(folder)
        (directory / "subject.py").write_text(code)
        with tempfile.TemporaryFile() as output:
            try:
                command = isolated_command(directory)
                options = dict(
                    cwd=directory,
                    input=json.dumps(probes).encode(),
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=8,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C", "TZ": "UTC"},
                )
                done = subprocess.run(command, **options)
                if b"sandbox_apply: Operation not permitted" in done.stderr:
                    if not calibration_control:
                        raise RuntimeError(
                            "macOS cannot nest the submission sandbox under this outer sandbox"
                        )
                    # Only calibrate() supplies wheel-owned controls here. The outer sandbox
                    # remains in effect; an arbitrary submission always requires its own profile.
                    done = subprocess.run(command[3:], **options)
                if done.stderr.startswith(b"bwrap:") and done.returncode:
                    raise RuntimeError(
                        "bubblewrap could not initialize the submission sandbox"
                    )
                if done.returncode:
                    return None
                output.seek(0)
                return json.loads(output.read(2_000_000))
            except (subprocess.TimeoutExpired, ValueError, UnicodeError):
                return None


def grade(task_id, candidate):
    key = index(True)[task_id]
    return invoke(candidate, key["probes"]) == key["expected"]


def calibration(task_id):
    key = index(True)[task_id]
    return tuple(
        invoke(source, key["probes"], calibration_control=True) == key["expected"]
        for source in (run_reference(task_id), run_negative(task_id))
    )


def candidate_from_file(path):
    return path.read_text()


def save_candidate(task_id, candidate, path):
    path.write_text(candidate)
