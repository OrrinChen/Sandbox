"""Verify that `streamlit run app.py` starts the local demo server."""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import importlib.util


def main() -> None:
    streamlit = shutil.which("streamlit")
    if streamlit is None and importlib.util.find_spec("streamlit") is None:
        print("streamlit_started=skipped reason=streamlit_not_installed app=app.py")
        return
    command_prefix = [streamlit] if streamlit is not None else [sys.executable, "-m", "streamlit"]

    port = _free_port()
    process = subprocess.Popen(
        command_prefix
        + [
            "run",
            "app.py",
            "--server.headless=true",
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = []
    try:
        started = _wait_for_http(port, process, output)
        if not started:
            tail = "".join(output[-20:]).replace("\n", " | ")
            raise SystemExit(f"streamlit_started=False port={port} output={tail}")
        print(f"streamlit_started=True url=http://127.0.0.1:{port} app=app.py")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_http(port: int, process: subprocess.Popen, output: list) -> bool:
    deadline = time.time() + 20
    while time.time() < deadline:
        if process.poll() is not None:
            if process.stdout is not None:
                output.extend(process.stdout.readlines())
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.5) as response:
                return response.status == 200
        except Exception:
            time.sleep(0.5)
    if process.stdout is not None:
        output.extend(process.stdout.readlines())
    return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    main()
