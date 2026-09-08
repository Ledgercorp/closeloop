from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from threading import Event, Thread

import jwt
import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.settings import AuthSettings

import closeloop.lifecycle as lifecycle_module
from closeloop.auth import HmacJwtTokenVerifier, REQUIRED_SCOPE
from closeloop.demo_provider import DemoProvider
from closeloop.http_app import create_app
from closeloop.public_demo_api import PublicDemoRunner


ISSUER = "https://issuer.public-demo.test"
AUDIENCE = "https://closeloop.public-demo.test/mcp"
AUTH_SECRET = "public-demo-auth-secret-that-is-at-least-thirty-two-bytes"


def make_auth():
    settings = AuthSettings(
        issuer_url=ISSUER,
        resource_server_url=AUDIENCE,
        required_scopes=[REQUIRED_SCOPE],
    )
    return settings, HmacJwtTokenVerifier(AUTH_SECRET, ISSUER, AUDIENCE)


def make_client(**kwargs) -> TestClient:
    settings, verifier = make_auth()
    return TestClient(create_app(auth_settings=settings, token_verifier=verifier, **kwargs))


@pytest.mark.parametrize(
    ("scenario", "verdict", "consumer_state", "lifecycle_state"),
    [
        ("healthy", "PASS", "Verified", "VERIFIED"),
        ("false_success", "FAIL", "Not completed", "NOT_COMPLETED"),
        (
            "evidence_outage",
            "INCONCLUSIVE",
            "Awaiting proof",
            "AWAITING_PROOF",
        ),
    ],
)
def test_public_demo_runs_real_server_lifecycle(
    scenario, verdict, consumer_state, lifecycle_state
):
    with make_client() as client:
        response = client.post("/demo/run", json={"scenario": scenario})

    assert response.status_code == 200
    result = response.json()
    assert result["schema_version"] == "closeloop.public-demo-result/v1"
    assert result["server_generated"] is True
    assert result["scenario"] == scenario
    assert result["verification"]["verdict"] == verdict
    assert result["verification"]["consumer_state"] == consumer_state
    assert result["resolution"]["lifecycle_state"] == lifecycle_state
    assert result["execution_claim"]["provider_reported_success"] is True
    assert result["summary"].startswith("In this isolated simulation,")
    assert "your subscription is canceled" not in result["summary"].lower()
    assert "simulat" in result["recommended_next_step"].lower() or "demo" in result[
        "recommended_next_step"
    ].lower()
    assert result["disclosure"] == {
        "provider": "deterministic simulated subscription provider",
        "confirmation": (
            "isolated public-demo confirmation; not a production trusted attestation"
        ),
        "live_alexa_plus": False,
        "live_aws": False,
        "production_action": False,
    }
    assert response.headers["cache-control"] == "no-store"


def test_false_success_is_decided_after_provider_and_readback(monkeypatch):
    calls: list[str] = []
    original_cancel = DemoProvider.cancel_subscription
    original_read = DemoProvider.read_cancellation_evidence
    original_verify = lifecycle_module.verify_cancellation

    def cancel(provider):
        calls.append("provider")
        return original_cancel(provider)

    def read(provider):
        calls.append("readback")
        return original_read(provider)

    def verify(receipt, evidence):
        calls.append("verifier")
        return original_verify(receipt, evidence)

    monkeypatch.setattr(DemoProvider, "cancel_subscription", cancel)
    monkeypatch.setattr(DemoProvider, "read_cancellation_evidence", read)
    monkeypatch.setattr(lifecycle_module, "verify_cancellation", verify)

    with make_client() as client:
        result = client.post("/demo/run", json={"scenario": "false_success"}).json()

    assert calls == ["provider", "readback", "verifier"]
    assert result["execution_claim"]["provider_reported_success"] is True
    assert result["independent_read_back"]["auto_renew"] is True
    assert result["verification"]["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "body",
    [
        {"scenario": "healthy", "verdict": "PASS"},
        {"scenario": "healthy", "status": "VERIFIED"},
        {"scenario": "healthy", "success": True},
        {"scenario": "healthy", "evidence": {"auto_renew": False}},
        {"scenario": "healthy", "confirmation_attestation": "token"},
        {"scenario": "healthy", "resolution_id": "production-id"},
        {"scenario": "unknown"},
        {"scenario": True},
        {"scenario": 1},
        {},
        ["healthy"],
    ],
)
def test_public_demo_rejects_every_shape_except_exact_scenario(body):
    with make_client() as client:
        response = client.post("/demo/run", json=body)
    assert response.status_code == 422
    assert set(response.json()) == {"error"}


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        (b"{", 400),
        (b"", 400),
        (b'{"scenario":"healthy","scenario":"false_success"}', 400),
        (b"\xff", 400),
        (json.dumps({"scenario": "healthy", "padding": "x" * 100}).encode(), 413),
    ],
)
def test_public_demo_rejects_malformed_duplicate_and_oversize_bodies(
    body, expected_status
):
    with make_client() as client:
        response = client.post(
            "/demo/run", content=body, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == expected_status
    assert set(response.json()) == {"error"}


def test_public_demo_stream_cap_applies_without_content_length():
    def chunks():
        yield b'{"scenario":"healthy","padding":"'
        yield b"x" * 100
        yield b'"}'

    with make_client() as client:
        response = client.post(
            "/demo/run",
            content=chunks(),
            headers={"Content-Type": "application/json"},
        )
    assert response.request.headers.get("content-length") is None
    assert response.status_code == 413


def test_public_demo_rejects_encoding_cross_origin_and_other_methods():
    with make_client() as client:
        encoded = client.post(
            "/demo/run",
            content=b"not-really-gzip",
            headers={
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )
        cross_origin = client.post(
            "/demo/run",
            json={"scenario": "healthy"},
            headers={"Origin": "https://attacker.example"},
        )
        same_origin = client.post(
            "/demo/run",
            json={"scenario": "healthy"},
            headers={"Origin": "http://testserver"},
        )
        method_results = {
            method: client.request(method, "/demo/run")
            for method in ("GET", "HEAD", "OPTIONS")
        }

    assert encoded.status_code == 415
    assert cross_origin.status_code == 403
    assert "access-control-allow-origin" not in cross_origin.headers
    assert same_origin.status_code == 200
    assert all(response.status_code in {404, 405} for response in method_results.values())


def test_public_demo_never_consults_production_factories(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("production factory must not be consulted")

    monkeypatch.setattr(
        "closeloop.repository.create_repository_from_environment", forbidden
    )
    monkeypatch.setattr(
        "closeloop.confirmation.confirmation_attestation_verifier_from_environment",
        forbidden,
    )
    monkeypatch.setattr("closeloop.mcp_server.create_mcp_server", forbidden)

    result = PublicDemoRunner().run("healthy")
    assert result.verification.verdict == "PASS"


def test_public_demo_response_is_explicit_and_contains_no_capability_material():
    with make_client() as client:
        response = client.post("/demo/run", json={"scenario": "healthy"})

    result = response.json()
    assert set(result) == {
        "schema_version",
        "server_generated",
        "scenario",
        "resolution",
        "execution_claim",
        "independent_read_back",
        "verification",
        "summary",
        "recommended_next_step",
        "disclosure",
    }
    assert set(result["resolution"]) == {
        "resolution_id",
        "action",
        "action_digest",
        "lifecycle_state",
        "requested_at",
        "confirmed_at",
        "executing_at",
        "verifying_at",
        "completed_at",
    }
    serialized = response.text.lower()
    for forbidden in (
        "owner_id",
        '"confirmation_attestation":',
        "token_sha256",
        "confirmation_secret",
        "sqlite",
        "resolution.db",
        "/tmp/",
        "eyj",
    ):
        assert forbidden not in serialized


class FailingRunner:
    def run(self, scenario):
        del scenario
        raise RuntimeError("secret-stack-detail /tmp/private.db")


def test_public_demo_failure_is_generic_and_never_verified():
    with make_client(public_demo_runner=FailingRunner()) as client:
        response = client.post("/demo/run", json={"scenario": "healthy"})
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "demo_unavailable", "message": "Demo proof is unavailable."}
    }
    assert "verified" not in response.text.lower()
    assert "private.db" not in response.text


class BlockingRunner:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def run(self, scenario):
        self.entered.set()
        assert self.release.wait(timeout=5)
        return PublicDemoRunner().run(scenario)


def test_public_demo_timeout_and_saturation_fail_closed_without_queueing():
    runner = BlockingRunner()
    responses = []
    with make_client(
        public_demo_runner=runner,
        public_demo_max_concurrency=1,
        public_demo_timeout_seconds=0.05,
    ) as client:
        first = Thread(
            target=lambda: responses.append(
                client.post("/demo/run", json={"scenario": "healthy"})
            )
        )
        first.start()
        assert runner.entered.wait(timeout=2)
        saturated = client.post("/demo/run", json={"scenario": "false_success"})
        first.join(timeout=2)
        runner.release.set()

    assert saturated.status_code == 429
    assert len(responses) == 1
    assert responses[0].status_code == 503
    assert "Verified" not in responses[0].text


def test_public_demo_path_without_trailing_slash_redirects_to_bundle():
    with make_client() as client:
        response = client.get("/demo", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/demo/"


def _bundle_template() -> str:
    bundle = (
        Path(__file__).parents[1] / "src" / "closeloop" / "public_demo" / "index.html"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'<script type="__bundler/template">\s*(.*?)\s*</script>', bundle, re.DOTALL
    )
    assert match is not None
    return json.loads(match.group(1))


def test_polished_browser_bundle_has_title_language_and_mobile_layout_rules():
    template = _bundle_template()

    assert '<html lang="en">' in template
    assert "<title>CloseLoop demo</title>" in template
    assert "@media (max-width: 640px)" in template
    assert '[role="group"][aria-label="Demo scenarios"]' in template
    assert '[aria-labelledby="lifecycle-heading"] ol' in template
    # Scenario selection and Restart must bring the confirmation card back into view.
    assert "this.focusInteractiveSection();" in template
    assert "prefers-reduced-motion: reduce" in template
    assert 'scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" })' in template


def test_polished_browser_bundle_stores_scripts_uncompressed_for_older_safari():
    """Safari before 16.4 lacks DecompressionStream; the bundle must not depend on it."""

    bundle = (
        Path(__file__).parents[1] / "src" / "closeloop" / "public_demo" / "index.html"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'<script type="__bundler/manifest">\s*(.*?)\s*</script>', bundle, re.DOTALL
    )
    assert match is not None
    manifest = json.loads(match.group(1))

    assert all(entry["compressed"] is False for entry in manifest.values())
    scripts = [entry for entry in manifest.values() if entry["mime"] == "text/javascript"]
    assert len(scripts) == 3
    heads = set()
    for entry in scripts:
        raw = base64.b64decode(entry["data"])
        assert raw[:2] != b"\x1f\x8b"
        heads.add(raw.decode("utf-8")[:40])
    assert any("dc-runtime" in head for head in heads)
    assert sum("@license React" in head for head in heads) == 2


def test_polished_browser_bundle_only_requests_scenario_and_has_no_verifier_logic():
    bundle = (
        Path(__file__).parents[1] / "src" / "closeloop" / "public_demo" / "index.html"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'<script type="__bundler/template">\s*(.*?)\s*</script>', bundle, re.DOTALL
    )
    assert match is not None
    template = json.loads(match.group(1))

    assert "function runProvider" not in template
    assert "function verifyCancellation" not in template
    assert "MAX_EVIDENCE_AGE_SECONDS" not in template
    assert 'const DEMO_API_PATH = "/demo/run"' in template
    assert 'body: JSON.stringify({ scenario })' in template
    assert 'body: JSON.stringify({ scenario, ' not in template
    assert "parseDemoResponse" in template
    assert "Validate the server contract without deriving a verdict from evidence" in template
    assert 'phase: "requesting"' in template
    response_validated_at = template.index("const value = response.data;")
    confirmation_displayed_at = template.index(
        'phase: "executing"', response_validated_at
    )
    assert confirmation_displayed_at > response_validated_at
    pre_validation = template[template.index("confirm() {") : response_validated_at]
    assert 'phase: "executing"' not in pre_validation
    assert "confirmation: this.stamp()" not in pre_validation
    assert "Confirmed — the action is running" not in template
    assert "CloseLoop is executing the confirmed cancellation" not in template
    assert "No confirmation, execution claim, or verdict is displayed" in template
    assert "In this isolated simulation" not in pre_validation
    assert 'statusLabel: error ? "Proof unavailable"' in template
    assert "requestSerial !== this._requestSerial" in template
    assert "this._active" in template
