from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .confirmation import (
    CONFIRMATION_CONTRACT_VERSION,
    HmacJwtConfirmationAttestationVerifier,
)
from .demo_provider import DemoProvider
from .lifecycle import ResolutionService
from .repository import SqlResolutionRepository


PUBLIC_DEMO_RESULT_SCHEMA = "closeloop.public-demo-result/v1"
PUBLIC_DEMO_SCENARIOS = frozenset({"healthy", "false_success", "evidence_outage"})
PUBLIC_DEMO_INTENT = "Cancel my subscription and make sure I will not be charged again."
PUBLIC_DEMO_MAX_BODY_BYTES = 96
PUBLIC_DEMO_MAX_CONCURRENCY = 4
PUBLIC_DEMO_TIMEOUT_SECONDS = 5.0

_DEMO_CONFIRMATION_ISSUER = "urn:closeloop:public-demo:ephemeral"
_DEMO_CONFIRMATION_AUDIENCE = "urn:closeloop:public-demo"
_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
_PRESENTATION_SUMMARIES = {
    "PASS": (
        "In this isolated simulation, the server-side verifier confirmed that the simulated "
        "subscription is canceled: auto-renew is off and an effective billing end date is visible."
    ),
    "FAIL": (
        "In this isolated simulation, the provider reported success, but independent read-back "
        "shows auto-renew is still enabled. CloseLoop therefore reports that the task is not done."
    ),
    "INCONCLUSIVE": (
        "In this isolated simulation, the cancellation may have run, but the account state could "
        "not be read independently. CloseLoop will not turn missing evidence into a success claim."
    ),
}
_PRESENTATION_NEXT_STEPS = {
    "PASS": "The isolated demo requires no further action.",
    "FAIL": "The simulated task was not completed; rerun the demo only if you want to try again.",
    "INCONCLUSIVE": "The simulated proof is unavailable; rerun the demo to check again.",
}

DemoScenario = Literal["healthy", "false_success", "evidence_outage"]
DemoVerdict = Literal["PASS", "FAIL", "INCONCLUSIVE"]
DemoConsumerState = Literal["Verified", "Not completed", "Awaiting proof"]
DemoLifecycleState = Literal["VERIFIED", "NOT_COMPLETED", "AWAITING_PROOF"]


class _StrictResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PublicDemoResolution(_StrictResponseModel):
    resolution_id: str = Field(min_length=36, max_length=36)
    action: Literal["cancel_subscription"]
    action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    lifecycle_state: DemoLifecycleState
    requested_at: str = Field(min_length=1, max_length=64)
    confirmed_at: str = Field(min_length=1, max_length=64)
    executing_at: str = Field(min_length=1, max_length=64)
    verifying_at: str = Field(min_length=1, max_length=64)
    completed_at: str = Field(min_length=1, max_length=64)


class PublicDemoExecutionClaim(_StrictResponseModel):
    source: Literal["demo_provider.cancel_subscription"]
    request_reference: str = Field(min_length=1, max_length=64)
    provider_reported_success: bool
    message: str = Field(max_length=200)
    observed_at: str = Field(min_length=1, max_length=64)


class PublicDemoReadBack(_StrictResponseModel):
    source: Literal["demo_provider.read_cancellation_evidence"]
    account_readable: bool
    auto_renew: bool | None
    effective_end_date: str | None = Field(default=None, max_length=10)
    freshness_seconds: int | None = Field(default=None, ge=0, le=30)
    observed_at: str = Field(min_length=1, max_length=64)


class PublicDemoVerification(_StrictResponseModel):
    verifier: Literal["closeloop.verify_cancellation/v1"]
    verdict: DemoVerdict
    consumer_state: DemoConsumerState
    reason: str = Field(min_length=1, max_length=500)
    evaluated_at: str = Field(min_length=1, max_length=64)


class PublicDemoDisclosure(_StrictResponseModel):
    provider: Literal["deterministic simulated subscription provider"]
    confirmation: Literal[
        "isolated public-demo confirmation; not a production trusted attestation"
    ]
    live_alexa_plus: Literal[False]
    live_aws: Literal[False]
    production_action: Literal[False]


class PublicDemoResult(_StrictResponseModel):
    schema_version: Literal["closeloop.public-demo-result/v1"]
    server_generated: Literal[True]
    scenario: DemoScenario
    resolution: PublicDemoResolution
    execution_claim: PublicDemoExecutionClaim
    independent_read_back: PublicDemoReadBack
    verification: PublicDemoVerification
    summary: str = Field(min_length=1, max_length=500)
    recommended_next_step: str = Field(min_length=1, max_length=500)
    disclosure: PublicDemoDisclosure

    @model_validator(mode="after")
    def terminal_tuple_is_consistent(self) -> PublicDemoResult:
        expected = {
            "PASS": ("Verified", "VERIFIED"),
            "FAIL": ("Not completed", "NOT_COMPLETED"),
            "INCONCLUSIVE": ("Awaiting proof", "AWAITING_PROOF"),
        }[self.verification.verdict]
        actual = (self.verification.consumer_state, self.resolution.lifecycle_state)
        if actual != expected:
            raise ValueError("terminal result tuple is inconsistent")
        return self


class PublicDemoRunnerProtocol(Protocol):
    def run(self, scenario: DemoScenario) -> PublicDemoResult: ...


class PublicDemoRunner:
    """Run one isolated simulation through the production lifecycle and verifier.

    This runner never consults production repository, provider, authentication, or
    confirmation configuration. Its ephemeral confirmation capability proves only
    that the public demo button initiated this isolated simulated run.
    """

    def run(self, scenario: DemoScenario) -> PublicDemoResult:
        if scenario not in PUBLIC_DEMO_SCENARIOS:
            raise ValueError("unsupported public demo scenario")

        owner_id = f"public-demo:{uuid4()}"
        secret = secrets.token_urlsafe(48)
        verifier = HmacJwtConfirmationAttestationVerifier(
            secret=secret,
            issuer=_DEMO_CONFIRMATION_ISSUER,
            audience=_DEMO_CONFIRMATION_AUDIENCE,
        )
        with TemporaryDirectory(prefix="closeloop-public-demo-") as directory:
            repository = SqlResolutionRepository(
                f"sqlite+pysqlite:///{Path(directory) / 'resolution.db'}"
            )
            service = ResolutionService(
                repository=repository,
                provider_factory=DemoProvider,
                confirmation_verifier=verifier,
            )
            started = service.start_resolution(owner_id, PUBLIC_DEMO_INTENT, scenario)
            attestation = _mint_ephemeral_demo_confirmation(
                started=started,
                owner_id=owner_id,
                secret=secret,
            )
            status = service.confirm_resolution_action(
                owner_id,
                str(started["resolution_id"]),
                True,
                confirmation_attestation=attestation,
            )
            evidence = service.get_resolution_evidence(
                owner_id, str(started["resolution_id"])
            )

        return _presentation_result(scenario, status, evidence)


def _mint_ephemeral_demo_confirmation(
    *,
    started: dict[str, object],
    owner_id: str,
    secret: str,
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": _DEMO_CONFIRMATION_ISSUER,
            "aud": _DEMO_CONFIRMATION_AUDIENCE,
            "confirmation_contract": CONFIRMATION_CONTRACT_VERSION,
            "sub": owner_id,
            "resolution_id": started["resolution_id"],
            "action": started["action"],
            "action_digest": started["action_digest"],
            "confirmed": True,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=30)).timestamp()),
            "jti": str(uuid4()),
        },
        secret,
        algorithm="HS256",
    )


def _transition_time(evidence: dict[str, object], state: str) -> str:
    history = evidence.get("state_history")
    if not isinstance(history, list):
        raise ValueError("public demo lifecycle history is unavailable")
    for transition in history:
        if isinstance(transition, dict) and transition.get("state") == state:
            occurred_at = transition.get("occurred_at")
            if isinstance(occurred_at, str):
                return occurred_at
    raise ValueError("public demo lifecycle history is incomplete")


def _presentation_result(
    scenario: DemoScenario,
    status: dict[str, object],
    evidence: dict[str, object],
) -> PublicDemoResult:
    execution = evidence.get("execution_claim")
    read_back = evidence.get("independent_read_back")
    verification = evidence.get("verification")
    if not all(isinstance(value, dict) for value in (execution, read_back, verification)):
        raise ValueError("public demo terminal evidence is unavailable")
    assert isinstance(execution, dict)
    assert isinstance(read_back, dict)
    assert isinstance(verification, dict)

    completed_state = str(evidence["lifecycle_state"])
    payload = {
        "schema_version": PUBLIC_DEMO_RESULT_SCHEMA,
        "server_generated": True,
        "scenario": scenario,
        "resolution": {
            "resolution_id": evidence["resolution_id"],
            "action": evidence["action"],
            "action_digest": evidence["action_digest"],
            "lifecycle_state": completed_state,
            "requested_at": _transition_time(evidence, "REQUESTED"),
            "confirmed_at": status["confirmed_at"],
            "executing_at": _transition_time(evidence, "EXECUTING"),
            "verifying_at": _transition_time(evidence, "VERIFYING"),
            "completed_at": _transition_time(evidence, completed_state),
        },
        "execution_claim": {
            "source": execution["source"],
            "request_reference": execution["request_id"],
            "provider_reported_success": execution["provider_reported_success"],
            "message": execution["message"],
            "observed_at": execution["observed_at"],
        },
        "independent_read_back": {
            "source": read_back["source"],
            "account_readable": read_back["account_readable"],
            "auto_renew": read_back["auto_renew"],
            "effective_end_date": read_back["effective_end_date"],
            "freshness_seconds": read_back["freshness_seconds"],
            "observed_at": read_back["observed_at"],
        },
        "verification": {
            "verifier": verification["verifier"],
            "verdict": verification["verdict"],
            "consumer_state": verification["consumer_state"],
            "reason": verification["reason"],
            "evaluated_at": verification["evaluated_at"],
        },
        "summary": _PRESENTATION_SUMMARIES[str(verification["verdict"])],
        "recommended_next_step": _PRESENTATION_NEXT_STEPS[
            str(verification["verdict"])
        ],
        "disclosure": {
            "provider": "deterministic simulated subscription provider",
            "confirmation": (
                "isolated public-demo confirmation; not a production trusted attestation"
            ),
            "live_alexa_plus": False,
            "live_aws": False,
            "production_action": False,
        },
    }
    return PublicDemoResult.model_validate(payload)


class _DuplicateJsonKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


async def _read_demo_scenario(request: Request) -> DemoScenario | JSONResponse:
    content_encoding = request.headers.get("content-encoding", "").strip().lower()
    if content_encoding not in {"", "identity"}:
        return _error_response(415, "unsupported_media_type", "Unsupported request encoding.")

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        return _error_response(415, "unsupported_media_type", "Expected application/json.")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > PUBLIC_DEMO_MAX_BODY_BYTES:
            return _error_response(413, "request_too_large", "Demo request is too large.")
    try:
        decoded = bytes(body).decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey):
        return _error_response(400, "invalid_json", "Demo request is not valid JSON.")

    if type(value) is not dict or set(value) != {"scenario"}:
        return _error_response(422, "invalid_demo_request", "Only scenario is accepted.")
    scenario = value["scenario"]
    if type(scenario) is not str or scenario not in PUBLIC_DEMO_SCENARIOS:
        return _error_response(422, "invalid_demo_request", "Unknown demo scenario.")
    return scenario  # type: ignore[return-value]


def _same_origin_if_present(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    request_origin = f"{request.url.scheme}://{request.url.netloc}"
    return origin.rstrip("/") == request_origin.rstrip("/")


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        headers=_RESPONSE_HEADERS,
    )


def _release_after_completion(
    task: asyncio.Task[PublicDemoResult], admission: BoundedSemaphore
) -> None:
    try:
        task.exception()
    except (asyncio.CancelledError, Exception):
        pass
    admission.release()


def install_public_demo_api(
    app: FastAPI,
    *,
    runner: PublicDemoRunnerProtocol | None = None,
    max_concurrency: int = PUBLIC_DEMO_MAX_CONCURRENCY,
    timeout_seconds: float = PUBLIC_DEMO_TIMEOUT_SECONDS,
    to_thread: Callable[..., object] = asyncio.to_thread,
) -> None:
    """Install the isolated public demo route before the static `/demo` mount."""

    if max_concurrency < 1 or timeout_seconds <= 0:
        raise ValueError("public demo admission settings must be positive")
    active_runner = runner or PublicDemoRunner()
    admission = BoundedSemaphore(max_concurrency)

    @app.post("/demo/run", include_in_schema=False)
    async def run_public_demo(request: Request) -> JSONResponse:
        if not _same_origin_if_present(request):
            return _error_response(403, "origin_rejected", "Request origin is not allowed.")
        scenario = await _read_demo_scenario(request)
        if isinstance(scenario, JSONResponse):
            return scenario
        if not admission.acquire(blocking=False):
            return _error_response(429, "demo_busy", "The demo is busy. Try again shortly.")

        task = asyncio.create_task(to_thread(active_runner.run, scenario))  # type: ignore[arg-type]
        try:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout_seconds)
            validated = PublicDemoResult.model_validate(result)
        except asyncio.CancelledError:
            if task.done():
                _release_after_completion(task, admission)
            else:
                task.add_done_callback(
                    lambda completed: _release_after_completion(completed, admission)
                )
            raise
        except TimeoutError:
            task.add_done_callback(
                lambda completed: _release_after_completion(completed, admission)
            )
            return _error_response(503, "demo_unavailable", "Demo proof is unavailable.")
        except Exception:
            admission.release()
            return _error_response(503, "demo_unavailable", "Demo proof is unavailable.")
        admission.release()
        return JSONResponse(
            validated.model_dump(mode="json"),
            status_code=200,
            headers=_RESPONSE_HEADERS,
        )
