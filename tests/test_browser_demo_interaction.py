"""Real-browser regression for the public demo controls.

Runs ``tests/browser_demo_interaction.mjs`` against a live local server with
``window.DecompressionStream`` removed, which reproduces Safari 16.3 and earlier
(iOS 16.3 and earlier) on the bundle loader. The test is skipped when Node.js or
a Playwright browser is unavailable so the suite stays deterministic elsewhere.
Set ``CLOSELOOP_BROWSER_ENGINES=chromium,webkit`` to cover WebKit as well.
"""

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


def _wait_for_health(port: int, process: subprocess.Popen) -> None:
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
def test_public_demo_controls_work_without_decompression_stream(engine, tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    probe = subprocess.run(
        ["node", str(SCRIPT), "--probe", engine], capture_output=True, text=True, timeout=120
    )
    if probe.returncode != 0:
        pytest.skip(f"Playwright {engine} unavailable: {probe.stderr.strip()[-200:]}")

    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)]),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
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
            timeout=300,
        )
    finally:
        server.terminate()
        server.wait(timeout=15)

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["failures"] == []
    assert report["noDecompressionStream"] is True
    assert [post["body"] for post in report["posts"]] == [
        '{"scenario":"healthy"}',
        '{"scenario":"false_success"}',
        '{"scenario":"evidence_outage"}',
        '{"scenario":"healthy"}',
        '{"scenario":"false_success"}',
    ]
    assert all(post["method"] == "POST" for post in report["posts"])
    assert [(o["scenario"], o["status"], o["chip"]) for o in report["outcomes"]] == [
        ("healthy", "Verified", "PASS"),
        ("false_success", "Not completed", "FAIL"),
        ("evidence_outage", "Awaiting proof", "INCONCLUSIVE"),
        ("healthy", "Proof unavailable", ""),
        ("false_success", "Proof unavailable", ""),
    ]
