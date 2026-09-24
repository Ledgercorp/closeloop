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
from .models import ActionReceipt, CancellationEvidence, ResourceIdentity
from .outcomes import OutcomeViolation, RecoveryAction
from .repository import SqlResolutionRepository


PUBLIC_DEMO_RESULT_SCHEMA = "closeloop.public-demo-result/v2"
PUBLIC_DEMO_SCENARIOS = frozenset(
    {"healthy", "false_success", "evidence_outage", "persistent_resolution", "terminal_failure", "recovery_loop", "outcome_violation"}
)
PUBLIC_DEMO_INTENT = "Cancel StreamBox before next Friday and make sure I don't get charged again."
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
        "In this isolated simulation, independent evidence confirms auto-renew is off "
        "and the effective billing end date is visible."
    ),
    "FAIL": (
        "Fresh account evidence still shows auto-renew enabled after the bounded "
        "verification window. CloseLoop reports cancellation was not completed."
    ),
    "INCONCLUSIVE": "The request was sent, but CloseLoop cannot verify the result yet.",
}
_PRESENTATION_NEXT_STEPS = {
    "PASS": "The isolated demo requires no further action.",
    "FAIL": "In this simulation, the resolution needs attention; CloseLoop did not mark it complete.",
    "INCONCLUSIVE": "In this simulation, the resolution stays open for a later explicit recheck.",
}

DemoScenario = Literal["healthy", "false_success", "evidence_outage", "persistent_resolution", "terminal_failure", "recovery_loop", "outcome_violation"]
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
    is_terminal: bool
    next_check_at: str | None
    last_checked_at: str | None
    check_count: int
    max_checks: int
    resolved_at: str | None
    requested_at: str = Field(min_length=1, max_length=64)
    confirmed_at: str = Field(min_length=1, max_length=64)
    executing_at: str = Field(min_length=1, max_length=64)
    verifying_at: str = Field(min_length=1, max_length=64)
    completed_at: str | None
    resolution_receipt: dict[str, object] | None = None


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
    schema_version: Literal["closeloop.public-demo-result/v2"]
    server_generated: Literal[True]
    scenario: DemoScenario
    resolution: PublicDemoResolution
    execution_claim: PublicDemoExecutionClaim
    independent_read_back: PublicDemoReadBack
    verification: PublicDemoVerification
    summary: str = Field(min_length=1, max_length=500)
    recommended_next_step: str = Field(min_length=1, max_length=500)
    disclosure: PublicDemoDisclosure
    lifecycle_story: list[dict[str, object]] = Field(default_factory=list)
    verification_history: list[dict[str, object]] = Field(default_factory=list)

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
        if scenario == "persistent_resolution":
            return _run_persistent_resolution_demo()
        if scenario in {"recovery_loop", "outcome_violation"}:
            return _run_recovery_demo(scenario)

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
            if scenario == "terminal_failure":
                while status["lifecycle_state"] == "AWAITING_PROOF":
                    due = datetime.fromisoformat(
                        str(status["next_check_at"]).replace("Z", "+00:00")
                    )
                    status = service.recheck_resolution(
                        owner_id,
                        str(started["resolution_id"]),
                        scheduled_for=due,
                        now=due,
                    )
            evidence = service.get_resolution_evidence(
                owner_id, str(started["resolution_id"])
            )

        return _presentation_result(scenario, status, evidence)


class _PersistentJourneyProvider:
    def __init__(self) -> None:
        self.reads = 0

    def cancel_subscription(self, target: ResourceIdentity) -> ActionReceipt:
        return ActionReceipt("demo-request-1", True, "Cancellation accepted", target.target_digest)

    def read_cancellation_evidence(
        self, target: ResourceIdentity, attempt_id: str
    ) -> CancellationEvidence:
        self.reads += 1
        if self.reads == 1:
            return CancellationEvidence(
                True, True, None, 0, target.target_digest, attempt_id
            )
        return CancellationEvidence(
            True, False, "2026-10-03", 0, target.target_digest, attempt_id
        )


def _run_persistent_resolution_demo() -> PublicDemoResult:
    owner_id = f"public-demo:{uuid4()}"
    secret = secrets.token_urlsafe(48)
    verifier = HmacJwtConfirmationAttestationVerifier(
        secret=secret,
        issuer=_DEMO_CONFIRMATION_ISSUER,
        audience=_DEMO_CONFIRMATION_AUDIENCE,
    )
    provider = _PersistentJourneyProvider()
    story: list[dict[str, object]] = [
        {
            "scene": "DELEGATION",
            "session": "Day 1",
            "lifecycle_state": "AWAITING_CONFIRMATION",
            "summary": "Alexa+ asks for confirmation before any cancellation action.",
        }
    ]
    with TemporaryDirectory(prefix="closeloop-public-demo-") as directory:
        database = Path(directory) / "resolution.db"
        repository = SqlResolutionRepository(f"sqlite+pysqlite:///{database}")
        factory = lambda _mode: provider
        service = ResolutionService(
            repository=repository,
            provider_factory=factory,
            confirmation_verifier=verifier,
        )
        started = service.start_resolution(owner_id, PUBLIC_DEMO_INTENT, "false_success")
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
        evidence = service.get_resolution_evidence(owner_id, str(started["resolution_id"]))
        story.append(
            {
                "scene": "EXECUTION",
                "session": "Day 1",
                "lifecycle_state": "VERIFYING",
                "provider_reported_success": evidence["execution_claim"]["provider_reported_success"],
                "summary": "StreamBox accepted the request. CloseLoop is checking the account; acceptance is not resolution.",
            }
        )
        story.append(
            {
                "scene": "FALSE_SUCCESS",
                "session": "Day 1",
                "lifecycle_state": status["lifecycle_state"],
                "summary": "StreamBox accepted the cancellation request, but auto-renew is still on. I’m not marking this resolved yet.",
                "auto_renew": evidence["independent_read_back"]["auto_renew"],
            }
        )

        # A separate service instance simulates a later conversational session.
        service = ResolutionService(
            repository=SqlResolutionRepository(f"sqlite+pysqlite:///{database}"),
            provider_factory=factory,
            confirmation_verifier=verifier,
        )
        resumed = service.get_resolution_status(owner_id, str(started["resolution_id"]))
        story.append(
            {
                "scene": "PERSISTENCE",
                "session": "Later session",
                "resolution_id": resumed["resolution_id"],
                "lifecycle_state": resumed["lifecycle_state"],
                "next_check_at": resumed["next_check_at"],
                "summary": "What happened with StreamBox? CloseLoop retrieved the same open resolution.",
            }
        )
        due = datetime.fromisoformat(str(resumed["next_check_at"]).replace("Z", "+00:00"))
        status = service.recheck_resolution(
            owner_id,
            str(started["resolution_id"]),
            scheduled_for=due,
            now=due,
        )
        evidence = service.get_resolution_evidence(owner_id, str(started["resolution_id"]))
        story.extend(
            [
                {
                    "scene": "RECHECK",
                    "session": "Later session",
                    "resolution_id": status["resolution_id"],
                    "lifecycle_state": status["lifecycle_state"],
                    "last_checked_at": status["last_checked_at"],
                    "summary": "Independent read-back now finds auto-renew off and an effective end date.",
                },
                {
                    "scene": "FINAL_ANSWER",
                    "session": "Later session",
                    "lifecycle_state": status["lifecycle_state"],
                    "effective_end_date": evidence["independent_read_back"]["effective_end_date"],
                    "summary": "It’s verified canceled now. Auto-renew is off and your access ends October 3.",
                },
            ]
        )
        return _presentation_result(
            "persistent_resolution", status, evidence, story
        )


class _RecoveryJourneyProvider(_PersistentJourneyProvider):
    def __init__(self) -> None:
        super().__init__()
        self.recovery_completed = False
        self.refund_draft_prepared = False

    def read_cancellation_evidence(self, target: ResourceIdentity, attempt_id: str) -> CancellationEvidence:
        self.reads += 1
        return CancellationEvidence(
            account_readable=True,
            auto_renew=not self.recovery_completed,
            effective_end_date="2026-10-03" if self.recovery_completed else None,
            freshness_seconds=0,
            target_digest=target.target_digest,
            attempt_id=attempt_id,
        )

    def execute_recovery(self, action: RecoveryAction) -> dict[str, object]:
        if action.action_type == "prepare_support_followup":
            self.recovery_completed = True
            summary = "Support follow-up prepared; the simulated provider later updated the account."
        elif action.action_type == "prepare_refund_request":
            self.refund_draft_prepared = True
            summary = "Refund request draft prepared. Nothing was sent."
        else:
            raise ValueError("unsupported simulated recovery action")
        return {
            "source": "demo_provider.simulated_recovery",
            "request_id": f"recovery-{action.recovery_id}",
            "action_digest": action.action_digest,
            "target_digest": action.target_digest,
            "claimed_success": True,
            "summary": summary,
        }


def _run_recovery_demo(scenario: Literal["recovery_loop", "outcome_violation"]) -> PublicDemoResult:
    owner_id = f"public-demo:{uuid4()}"
    secret = secrets.token_urlsafe(48)
    verifier = HmacJwtConfirmationAttestationVerifier(
        secret=secret, issuer=_DEMO_CONFIRMATION_ISSUER, audience=_DEMO_CONFIRMATION_AUDIENCE
    )
    provider = _RecoveryJourneyProvider()
    story: list[dict[str, object]] = []
    with TemporaryDirectory(prefix="closeloop-recovery-demo-") as directory:
        database = Path(directory) / "resolution.db"
        repository = SqlResolutionRepository(f"sqlite+pysqlite:///{database}")
        service = ResolutionService(
            repository=repository,
            provider_factory=lambda _mode: provider,
            confirmation_verifier=verifier,
            recovery_provider=provider,
        )
        started = service.start_resolution(owner_id, PUBLIC_DEMO_INTENT, "false_success")
        resolution_id = str(started["resolution_id"])
        service.confirm_resolution_action(
            owner_id,
            resolution_id,
            True,
            _mint_ephemeral_demo_confirmation(started=started, owner_id=owner_id, secret=secret),
        )
        status = service.get_resolution_status(owner_id, resolution_id)
        record = repository.get_owned(resolution_id, owner_id)
        contract = record.outcome_contract
        if contract is None or contract.deadline_at is None or record.target is None:
            raise ValueError("demo request did not produce a bounded outcome contract")
        story.extend(
            [
                {"scene": "NORMAL_REQUEST", "utterance": PUBLIC_DEMO_INTENT, "lifecycle_state": "AWAITING_CONFIRMATION"},
                {"scene": "ORIGINAL_ACTION", "summary": "The cancellation request was sent once and the provider accepted it."},
                {"scene": "FALSE_SUCCESS", "lifecycle_state": status["lifecycle_state"], "summary": status["open_loop_summary"]},
            ]
        )

        if scenario == "recovery_loop":
            attention_time = max(
                datetime.now(timezone.utc) + timedelta(minutes=10),
                contract.deadline_at - timedelta(hours=5),
            )
            status = service.recheck_resolution(owner_id, resolution_id, now=attention_time, force=True)
            proposal = status.get("recovery_proposal")
            if not isinstance(proposal, dict) or status["attention"].get("level") not in {"ACTION_NEEDED", "URGENT"}:
                raise ValueError("fresh evidence and deadline policy did not justify recovery")
            story.extend(
                [
                    {"scene": "TIME_PASSES", "simulation": True, "summary": "Simulated time advances toward renewal."},
                    {"scene": "ACTION_NEEDED", "attention": status["attention"], "recovery_proposal": proposal},
                    {"scene": "RECOVERY_CONFIRMATION", "utterance": "Handle it.", "summary": "A new signed confirmation is bound to this exact follow-up."},
                ]
            )
            recovery_time = attention_time + timedelta(seconds=30)
            recovery_attestation = _mint_ephemeral_action_confirmation(
                owner_id=owner_id, resolution_id=resolution_id, action=str(proposal["action_type"]),
                action_digest=str(proposal["provenance"]["action_digest"]), secret=secret, now=recovery_time,
            )
            status = service.confirm_recovery_action(
                owner_id, resolution_id, str(proposal["recovery_id"]), confirmed=True,
                confirmation_attestation=recovery_attestation, now=recovery_time,
            )
            story.append({"scene": "RECOVERY_EXECUTED", "recovery_actions": status["recovery_actions"]})
            due = datetime.fromisoformat(str(status["next_check_at"]).replace("Z", "+00:00"))
            status = service.recheck_resolution(
                owner_id, resolution_id, scheduled_for=due,
                now=max(due, recovery_time),
            )
            story.extend(
                [
                    {"scene": "REVERIFY", "lifecycle_state": status["lifecycle_state"], "summary": status["open_loop_summary"]},
                    {"scene": "RESOLUTION_RECEIPT", "receipt": status["resolution_receipt"]},
                ]
            )
        else:
            observed_at = contract.deadline_at + timedelta(minutes=1)
            violation_now = observed_at + timedelta(minutes=1)
            violation = OutcomeViolation(
                violation_id=str(uuid4()), owner_id=owner_id, resolution_id=resolution_id,
                target_digest=record.target.target_digest, event_type="renewal_charge",
                amount_cents=1999, currency="USD", source="demo_billing_readback",
                evidence_id=f"demo-billing-{uuid4()}", observed_at=observed_at,
            )
            status = service.record_outcome_violation(owner_id, resolution_id, violation, now=violation_now)
            proposal = status.get("recovery_proposal")
            if not isinstance(proposal, dict) or status["attention"].get("level") != "URGENT":
                raise ValueError("outcome violation did not create urgent attention and a recovery proposal")
            story.extend(
                [
                    {"scene": "OUTCOME_VIOLATION", "evidence": violation.to_mapping(), "summary": status["open_loop_summary"]},
                    {"scene": "URGENT_ATTENTION", "attention": status["attention"], "recovery_proposal": proposal},
                    {"scene": "RECOVERY_CONFIRMATION", "utterance": "Prepare the refund request.", "summary": "Separate confirmation required; this only prepares a draft."},
                ]
            )
            recovery_time = violation_now + timedelta(minutes=1)
            recovery_attestation = _mint_ephemeral_action_confirmation(
                owner_id=owner_id, resolution_id=resolution_id, action=str(proposal["action_type"]),
                action_digest=str(proposal["provenance"]["action_digest"]), secret=secret, now=recovery_time,
            )
            service.confirm_recovery_action(
                owner_id, resolution_id, str(proposal["recovery_id"]), confirmed=True,
                confirmation_attestation=recovery_attestation, now=recovery_time,
            )
            due = datetime.fromisoformat(str(status["next_check_at"]).replace("Z", "+00:00"))
            status = service.recheck_resolution(
                owner_id, resolution_id, scheduled_for=due,
                now=max(due, recovery_time),
            )
            story.extend(
                [
                    {"scene": "REFUND_DRAFT_PREPARED", "recovery_actions": status["recovery_actions"]},
                    {"scene": "OUTCOME_EVALUATED", "lifecycle_state": status["lifecycle_state"], "summary": status["open_loop_summary"]},
                ]
            )

        evidence = service.get_resolution_evidence(owner_id, resolution_id)
        return _presentation_result(scenario, status, evidence, lifecycle_story=story)


def _mint_ephemeral_action_confirmation(
    *, owner_id: str, resolution_id: str, action: str, action_digest: str, secret: str, now: datetime
) -> str:
    return jwt.encode(
        {
            "iss": _DEMO_CONFIRMATION_ISSUER, "aud": _DEMO_CONFIRMATION_AUDIENCE,
            "confirmation_contract": CONFIRMATION_CONTRACT_VERSION, "sub": owner_id,
            "resolution_id": resolution_id, "action": action, "action_digest": action_digest,
            "confirmed": True, "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=30)).timestamp()), "jti": str(uuid4()),
        },
        secret,
        algorithm="HS256",
    )


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
    lifecycle_story: list[dict[str, object]] | None = None,
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
            "is_terminal": status["is_terminal"],
            "next_check_at": status["next_check_at"],
            "last_checked_at": status["last_checked_at"],
            "check_count": status["check_count"],
            "max_checks": status["max_checks"],
            "resolved_at": status["resolved_at"],
            "requested_at": _transition_time(evidence, "REQUESTED"),
            "confirmed_at": status["confirmed_at"],
            "executing_at": _transition_time(evidence, "EXECUTING"),
            "verifying_at": _transition_time(evidence, "VERIFYING"),
            "completed_at": status["resolved_at"],
            "resolution_receipt": status.get("resolution_receipt"),
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
        "summary": (
            str(status["open_loop_summary"])
            if status.get("outcome_violations")
            else (
            "The cancellation request was accepted, but auto-renew is still on. "
            "CloseLoop is not marking this resolved yet."
            if verification["verdict"] == "INCONCLUSIVE"
            and read_back["account_readable"] is True
            and read_back["auto_renew"] is True
            else _PRESENTATION_SUMMARIES[str(verification["verdict"])]
            )
        ),
        "recommended_next_step": (
            "Review the refund request draft; nothing has been sent."
            if status.get("outcome_violations")
            else _PRESENTATION_NEXT_STEPS[str(verification["verdict"])]
        ),
        "disclosure": {
            "provider": "deterministic simulated subscription provider",
            "confirmation": (
                "isolated public-demo confirmation; not a production trusted attestation"
            ),
            "live_alexa_plus": False,
            "live_aws": False,
            "production_action": False,
        },
        "lifecycle_story": lifecycle_story or [],
        "verification_history": evidence["verification_history"],
    }
    if lifecycle_story is None and scenario == "evidence_outage":
        lifecycle_story = [
            {
                "scene": "UNCERTAINTY",
                "session": "Simulated check",
                "lifecycle_state": status["lifecycle_state"],
                "next_check_at": status["next_check_at"],
                "summary": "The request was sent, but independent account evidence is unavailable. The resolution remains open as Awaiting proof.",
            }
        ]
        payload["lifecycle_story"] = lifecycle_story
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
