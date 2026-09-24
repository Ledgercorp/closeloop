"""Browser regression for the persistent public resolution experience."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
SCRIPT = Path(__file__).with_name("browser_demo_interaction.mjs")
ENGINES = [
    engine.strip()
    for engine in os.environ.get("CLOSELOOP_BROWSER_ENGINES", "chromium").split(",")
    if engine.strip()
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_health(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("demo server exited before becoming healthy")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("demo server did not become healthy")


@pytest.mark.parametrize("engine", ENGINES)
def test_persistent_demo_and_three_outcomes_in_browser(engine: str, tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    probe = subprocess.run(
        ["node", str(SCRIPT), "--probe", engine],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if probe.returncode != 0:
        pytest.skip(f"Playwright {engine} unavailable: {probe.stderr.strip()[-200:]}")

    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)]),
    }
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(port, server)
        result = subprocess.run(
            [
                "node",
                str(SCRIPT),
                f"http://127.0.0.1:{port}",
                engine,
                "--no-decompression-stream",
            ],
            capture_output=True,
            text=True,
            timeout=240,
        )
    finally:
        server.terminate()
        server.wait(timeout=15)

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["failures"] == []
    assert report["noDecompressionStream"] is True
    assert [(item["scenario"], item["state"], item["verdict"]) for item in report["outcomes"]] == [
        ("persistent_resolution", "VERIFIED", "PASS"),
        ("terminal_failure", "NOT_COMPLETED", "FAIL"),
        ("evidence_outage", "AWAITING_PROOF", "INCONCLUSIVE"),
    ]
    assert [post["body"] for post in report["posts"]] == [
        '{"scenario":"persistent_resolution"}',
        '{"scenario":"terminal_failure"}',
        '{"scenario":"evidence_outage"}',
    ]
    assert all(post["method"] == "POST" for post in report["posts"])
