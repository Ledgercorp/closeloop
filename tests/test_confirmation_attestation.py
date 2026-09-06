from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from mcp import Client

from closeloop.confirmation import (
    CONFIRMATION_ACTION,
    CONFIRMATION_CONTRACT_VERSION,
    DenyAllConfirmationAttestationVerifier,
    confirmation_attestation_verifier_from_environment,
)
from closeloop.lifecycle import (
    InvalidTransitionError,
    LifecycleState,
    ResolutionError,
    ResolutionService,
    ResolutionStorageUnavailableError,
)
from closeloop.mcp_server import create_mcp_server
from closeloop.repository import SqlResolutionRepository
from closeloop.repository_contract import record_from_mapping, record_to_mapping
from tests.confirmation_support import (
    TEST_CONFIRMATION_ISSUER,
    TEST_CONFIRMATION_SECRET,
    trusted_confirmation,
)


OWNER = "confirmation-owner"
INTENT = "Cancel my subscription and make sure I will not be charged again."


class CountingProvider:
    def __init__(self) -> None:
        self.execution_count = 0

    def cancel_subscription(self):
        from closeloop.models import ActionReceipt

        self.execution_count += 1
        return ActionReceipt("confirmed-action", True, "Cancellation accepted")

    def read_cancellation_evidence(self):
        from closeloop.models import CancellationEvidence

        return CancellationEvidence(True, False, "2026-09-30", 0)


def make_service(tmp_path, provider=None, name="confirmation.db"):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / name}")
    factory = (lambda _: provider) if provider else None
    return (
        ResolutionService(repository, factory)
        if factory
        else ResolutionService(repository)
    )


def assert_rejected_without_execution(service, started, attestation, provider):
    with pytest.raises(ResolutionError, match="trusted confirmation"):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=attestation,
        )
    assert provider.execution_count == 0
    assert service.get_resolution_status(OWNER, started["resolution_id"])[
        "lifecycle_state"
    ] == "AWAITING_CONFIRMATION"


def test_valid_trusted_attestation_is_consumed_before_execution_and_persisted(tmp_path):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)
    token = trusted_confirmation(started, OWNER)

    completed = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=token,
    )
    record = SqlResolutionRepository(
        f"sqlite+pysqlite:///{tmp_path / 'confirmation.db'}"
    ).get_owned(started["resolution_id"], OWNER)
    execution_transition = next(
        item for item in record.state_history if item.state is LifecycleState.EXECUTING
    )
    provenance = execution_transition.confirmation_attestation

    assert completed["verdict"] == "PASS"
    assert provider.execution_count == 1
    assert record.state_history[0].confirmation_contract_version == (
        CONFIRMATION_CONTRACT_VERSION
    )
    assert provenance is not None
    assert provenance.issuer == TEST_CONFIRMATION_ISSUER
    assert provenance.action_digest == started["action_digest"]
    assert provenance.token_sha256 not in token
    assert token not in str(record_to_mapping(record))


@pytest.mark.parametrize(
    "overrides",
    [
        {"sub": "another-principal"},
        {"resolution_id": "another-resolution"},
        {"action": "delete_account"},
        {"action_digest": "0" * 64},
        {"confirmed": False},
        {"iss": "https://unknown-issuer.invalid"},
        {"confirmation_contract": "closeloop.confirmation/v0"},
        {"iat": "1"},
        {"exp": 1.5},
        {"jti": ""},
        {"jti": "x" * 129},
    ],
)
def test_modified_or_mismatched_claims_fail_closed(tmp_path, overrides):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)
    token = trusted_confirmation(started, OWNER, overrides=overrides)

    assert_rejected_without_execution(service, started, token, provider)


@pytest.mark.parametrize(
    "offset_seconds,lifetime_seconds",
    [
        (-121, 300),
        (-61, 60),
        (1, 60),
        (0, 301),
        (0, 0),
    ],
)
def test_expired_future_or_overlong_attestations_fail_closed(
    tmp_path, offset_seconds, lifetime_seconds
):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)
    issued = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    token = trusted_confirmation(
        started,
        OWNER,
        now=issued,
        lifetime_seconds=lifetime_seconds,
    )

    assert_rejected_without_execution(service, started, token, provider)


@pytest.mark.parametrize("kind", ["tampered", "wrong-secret", "unsigned"])
def test_agent_generated_or_tampered_attestation_fails_closed(tmp_path, kind):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)
    if kind == "tampered":
        token = trusted_confirmation(started, OWNER)
        header, payload, signature = token.split(".")
        replacement = "A" if signature[0] != "A" else "B"
        token = ".".join((header, payload, replacement + signature[1:]))
    elif kind == "wrong-secret":
        token = trusted_confirmation(
            started,
            OWNER,
            secret="agent-generated-secret-that-is-more-than-thirty-two-bytes",
        )
    else:
        now = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode(
            {
                "iss": TEST_CONFIRMATION_ISSUER,
                "aud": "https://closeloop.test/confirmation",
                "confirmation_contract": CONFIRMATION_CONTRACT_VERSION,
                "sub": OWNER,
                "resolution_id": started["resolution_id"],
                "action": CONFIRMATION_ACTION,
                "action_digest": started["action_digest"],
                "confirmed": True,
                "iat": now,
                "exp": now + 60,
                "jti": "agent-fake",
            },
            key="",
            algorithm="none",
        )

    assert_rejected_without_execution(service, started, token, provider)


def test_missing_attestation_and_boolean_only_mcp_call_are_rejected(tmp_path):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)
    assert_rejected_without_execution(service, started, None, provider)

    async def attack():
        server = create_mcp_server(service, principal_resolver=lambda: OWNER)
        async with Client(server, raise_exceptions=False) as client:
            return await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": started["resolution_id"], "confirmed": True},
            )

    result = asyncio.run(attack())
    assert result.is_error is True
    assert provider.execution_count == 0


def test_attestation_for_one_resolution_cannot_confirm_another(tmp_path):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    first = service.start_resolution(OWNER, "Cancel subscription A")
    second = service.start_resolution(OWNER, "Cancel subscription B")

    assert_rejected_without_execution(
        service,
        second,
        trusted_confirmation(first, OWNER),
        provider,
    )


def test_attestation_replay_fails_across_repository_reinstantiation(tmp_path):
    database = tmp_path / "restart.db"
    first_service = ResolutionService(
        SqlResolutionRepository(f"sqlite+pysqlite:///{database}")
    )
    started = first_service.start_resolution(OWNER, INTENT)
    token = trusted_confirmation(started, OWNER)
    first_service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=token,
    )

    restarted = ResolutionService(SqlResolutionRepository(f"sqlite+pysqlite:///{database}"))
    with pytest.raises(InvalidTransitionError):
        restarted.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=token,
        )


def test_missing_or_partial_production_configuration_is_deny_all(monkeypatch):
    for name in (
        "CLOSELOOP_CONFIRMATION_SECRET",
        "CLOSELOOP_CONFIRMATION_ISSUER",
        "CLOSELOOP_CONFIRMATION_AUDIENCE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(
        confirmation_attestation_verifier_from_environment(),
        DenyAllConfirmationAttestationVerifier,
    )
    monkeypatch.setenv("CLOSELOOP_CONFIRMATION_SECRET", TEST_CONFIRMATION_SECRET)
    assert isinstance(
        confirmation_attestation_verifier_from_environment(),
        DenyAllConfirmationAttestationVerifier,
    )


@pytest.mark.parametrize(
    "removed",
    ["version", "attestation", "digest", "token_hash", "extended_expiry"],
)
def test_removing_or_modifying_persisted_confirmation_provenance_fails_closed(
    tmp_path, removed
):
    service = make_service(tmp_path)
    started = service.start_resolution(OWNER, INTENT)
    service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )
    repository = SqlResolutionRepository(
        f"sqlite+pysqlite:///{tmp_path / 'confirmation.db'}"
    )
    mapping = record_to_mapping(
        repository.get_owned(started["resolution_id"], OWNER),
        serialize_datetimes=True,
    )
    if removed == "version":
        del mapping["state_history"][0]["confirmation_contract_version"]
    elif removed == "attestation":
        del mapping["state_history"][2]["confirmation_attestation"]
    else:
        persisted = mapping["state_history"][2]["confirmation_attestation"]
        if removed == "digest":
            persisted["action_digest"] = "0" * 64
        elif removed == "token_hash":
            persisted["token_sha256"] = "not-a-digest"
        else:
            persisted["expires_at"] = "2030-01-01T00:00:00Z"

    with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
        record_from_mapping(mapping)


class UncertainFirstSaveRepository:
    def __init__(self, delegate, *, persist_before_failure: bool) -> None:
        self.delegate = delegate
        self.persist_before_failure = persist_before_failure
        self.failed = False

    def create(self, record):
        return self.delegate.create(record)

    def get_owned(self, resolution_id, owner_id):
        return self.delegate.get_owned(resolution_id, owner_id)

    def save_owned(self, record, expected_version):
        if not self.failed:
            self.failed = True
            if self.persist_before_failure:
                self.delegate.save_owned(record, expected_version)
            raise ResolutionStorageUnavailableError("uncertain confirmation persistence")
        return self.delegate.save_owned(record, expected_version)

    def list_open_owned(self, owner_id, limit):
        return self.delegate.list_open_owned(owner_id, limit)


@pytest.mark.parametrize("persist_before_failure", [False, True])
def test_storage_failure_around_atomic_consumption_never_executes_provider(
    tmp_path, persist_before_failure
):
    base = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'uncertain.db'}")
    provider = CountingProvider()
    repository = UncertainFirstSaveRepository(
        base, persist_before_failure=persist_before_failure
    )
    service = ResolutionService(repository, lambda _: provider)
    started = service.start_resolution(OWNER, INTENT)

    with pytest.raises(ResolutionStorageUnavailableError):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(started, OWNER),
        )
    assert provider.execution_count == 0
    state = base.get_owned(started["resolution_id"], OWNER).state
    assert state is (
        LifecycleState.EXECUTING
        if persist_before_failure
        else LifecycleState.AWAITING_CONFIRMATION
    )
