from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock

import boto3
import jwt
import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.auth.settings import AuthSettings
from moto import mock_aws

from closeloop.auth import HmacJwtTokenVerifier, REQUIRED_SCOPE, principal_key
from closeloop.dynamodb_repository import DynamoDbResolutionRepository
from closeloop.http_app import create_app
from closeloop.lifecycle import (
    ConcurrentResolutionUpdateError,
    InvalidTransitionError,
    ResolutionError,
    ResolutionStorageUnavailableError,
    ResolutionService,
    TerminalOutcomeImmutableError,
)
from closeloop.mcp_server import create_mcp_server
from closeloop.models import (
    ActionReceipt,
    CancellationEvidence,
    ConsumerState,
    ResolutionVerdict,
)
from closeloop.repository import SqlResolutionRepository, UnavailableResolutionRepository
from closeloop.verifier import verify_cancellation
from tests.confirmation_support import trusted_confirmation


OWNER = "owner-a"
INTENT = "Cancel my subscription and make sure I will not be charged again."
ISSUER = "https://issuer.security.test"
AUDIENCE = "https://closeloop.security.test/mcp"
SECRET = "security-test-secret-that-is-more-than-thirty-two-bytes"
TABLE_NAME = "closeloop-security-test"


class CountingProvider:
    def __init__(
        self,
        *,
        receipt: ActionReceipt | object | None = None,
        evidence: CancellationEvidence | object | None = None,
        execution_error: Exception | None = None,
        evidence_error: Exception | None = None,
    ) -> None:
        self.receipt = receipt or ActionReceipt("action-1", True, "Cancellation accepted")
        self.evidence = evidence or CancellationEvidence(True, False, "2026-09-30", 0)
        self.execution_error = execution_error
        self.evidence_error = evidence_error
        self.execution_count = 0
        self.read_count = 0
        self._lock = Lock()

    def cancel_subscription(self):
        with self._lock:
            self.execution_count += 1
        if self.execution_error:
            raise self.execution_error
        return self.receipt

    def read_cancellation_evidence(self):
        with self._lock:
            self.read_count += 1
        if self.evidence_error:
            raise self.evidence_error
        return self.evidence


def make_service(tmp_path, provider: CountingProvider | None = None, name="security.db"):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / name}")
    if provider is None:
        return ResolutionService(repository)
    return ResolutionService(repository, lambda _: provider)


def make_auth():
    settings = AuthSettings(
        issuer_url=ISSUER,
        resource_server_url=AUDIENCE,
        required_scopes=[REQUIRED_SCOPE],
    )
    return settings, HmacJwtTokenVerifier(SECRET, ISSUER, AUDIENCE)


def token_for(subject="principal-a", **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": subject,
        "iat": now,
        "exp": now + 300,
        "scope": REQUIRED_SCOPE,
    }
    claims.update(overrides)
    secret = claims.pop("_secret", SECRET)
    return jwt.encode(claims, secret, algorithm="HS256")


def protocol_headers(token=None, version="2025-11-25"):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": version,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def tool_request(name, arguments, request_id=1):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


@pytest.mark.parametrize("bad_confirmation", ["true", "yes", 1, 0, None, [], {}])
def test_non_boolean_mcp_confirmation_never_executes(tmp_path, bad_confirmation):
    async def attack():
        provider = CountingProvider()
        service = make_service(tmp_path, provider)
        server = create_mcp_server(service, principal_resolver=lambda: OWNER)
        async with Client(server, raise_exceptions=False) as client:
            started = await client.call_tool("start_resolution", {"intent": INTENT})
            resolution_id = started.structured_content["resolution_id"]
            rejected = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": bad_confirmation,
                    "confirmation_attestation": trusted_confirmation(
                        started.structured_content, OWNER
                    ),
                },
            )
            return provider, service, resolution_id, rejected

    provider, service, resolution_id, rejected = asyncio.run(attack())
    assert rejected.is_error is True
    assert provider.execution_count == 0
    assert service.get_resolution_status(OWNER, resolution_id)["lifecycle_state"] == (
        "AWAITING_CONFIRMATION"
    )


@pytest.mark.parametrize(
    "evidence",
    [
        CancellationEvidence(True, False, "2026-09-30", -1),
        CancellationEvidence("yes", False, "2026-09-30", 0),
        CancellationEvidence(True, False, "   ", 0),
        CancellationEvidence(True, False, "not-a-date", 0),
        CancellationEvidence(True, False, "2026-09-30", "0"),
        CancellationEvidence(True, 0, "2026-09-30", 0),
    ],
)
def test_malformed_independent_evidence_never_passes_or_raises(evidence):
    receipt = ActionReceipt("action-1", True, "Cancellation accepted")

    result = verify_cancellation(receipt, evidence)

    assert result.verdict is ResolutionVerdict.INCONCLUSIVE
    assert result.consumer_state is ConsumerState.AWAITING_PROOF


@pytest.mark.parametrize(
    "receipt",
    [
        ActionReceipt("action-1", False, "Provider unavailable"),
        ActionReceipt("", True, "Cancellation accepted"),
        ActionReceipt("action-1", 1, "Cancellation accepted"),
        ActionReceipt("action-1", True, 7),
    ],
)
def test_failed_or_malformed_execution_receipt_cannot_support_pass(receipt):
    evidence = CancellationEvidence(True, False, "2026-09-30", 0)

    result = verify_cancellation(receipt, evidence)

    assert result.verdict is ResolutionVerdict.INCONCLUSIVE
    assert result.consumer_state is ConsumerState.AWAITING_PROOF


@pytest.mark.parametrize(
    ("freshness", "expected"),
    [
        (0, ResolutionVerdict.PASS),
        (30, ResolutionVerdict.PASS),
        (31, ResolutionVerdict.INCONCLUSIVE),
    ],
)
def test_evidence_freshness_boundary_is_deterministic(freshness, expected):
    receipt = ActionReceipt("action-1", True, "Cancellation accepted")
    evidence = CancellationEvidence(True, False, "2026-09-30", freshness)

    assert verify_cancellation(receipt, evidence).verdict is expected


def test_provider_execution_exception_cannot_become_verified(tmp_path):
    provider = CountingProvider(execution_error=RuntimeError("provider-secret"))
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)

    completed = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )

    assert completed["verdict"] == "INCONCLUSIVE"
    assert completed["consumer_state"] == "Awaiting proof"
    assert provider.execution_count == 1


@pytest.mark.parametrize(
    ("receipt", "evidence"),
    [
        ({"provider_reported_success": True}, CancellationEvidence(True, False, "2026-09-30", 0)),
        (ActionReceipt("action-1", True, "ok"), {"account_readable": True}),
    ],
)
def test_malformed_provider_objects_are_normalized_to_awaiting_proof(
    tmp_path, receipt, evidence
):
    provider = CountingProvider(receipt=receipt, evidence=evidence)
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)

    completed = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )

    assert completed["verdict"] == "INCONCLUSIVE"
    assert completed["consumer_state"] == "Awaiting proof"


def test_mcp_intent_and_resolution_identifiers_have_explicit_bounds(tmp_path):
    async def inspect_and_attack():
        provider = CountingProvider()
        service = make_service(tmp_path, provider)
        server = create_mcp_server(service, principal_resolver=lambda: OWNER)
        async with Client(server, raise_exceptions=False) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            intent_schema = tools["start_resolution"].input_schema["properties"]["intent"]
            resolution_schema = tools["get_resolution_status"].input_schema["properties"][
                "resolution_id"
            ]
            oversized = await client.call_tool(
                "start_resolution", {"intent": "x" * 2001}
            )
            return provider, service, intent_schema, resolution_schema, oversized

    provider, service, intent_schema, resolution_schema, oversized = asyncio.run(
        inspect_and_attack()
    )
    assert intent_schema["maxLength"] == 2000
    assert resolution_schema["maxLength"] == 64
    assert oversized.is_error is True
    assert provider.execution_count == 0
    assert service.list_open_resolutions(OWNER) == []


def test_direct_service_input_bounds_fail_before_storage(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError, match="2000"):
        service.start_resolution(OWNER, "x" * 2001)
    with pytest.raises(ValueError, match="64"):
        service.get_resolution_status(OWNER, "x" * 65)
    assert service.list_open_resolutions(OWNER) == []


@pytest.mark.parametrize(
    "override",
    [
        {"verdict": "PASS"},
        {"Verdict": "PASS"},
        {"status": "VERIFIED"},
        {"success": True},
        {"verification": {"verdict": "PASS"}},
        {"result": {"status": "VERIFIED"}},
        {"verdict": "pass"},
        {"verdict": "P%41SS"},
    ],
)
def test_mcp_override_variants_are_rejected_before_execution(tmp_path, override):
    async def attack():
        provider = CountingProvider(
            evidence=CancellationEvidence(True, True, None, 0)
        )
        service = make_service(tmp_path, provider)
        server = create_mcp_server(service, principal_resolver=lambda: OWNER)
        async with Client(server, raise_exceptions=False) as client:
            started = await client.call_tool("start_resolution", {"intent": INTENT})
            resolution_id = started.structured_content["resolution_id"]
            result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": trusted_confirmation(
                        started.structured_content, OWNER
                    ),
                    **override,
                },
            )
            return provider, service, resolution_id, result

    provider, service, resolution_id, result = asyncio.run(attack())
    assert result.is_error is True
    assert provider.execution_count == 0
    assert service.get_resolution_status(OWNER, resolution_id)["verdict"] is None


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"intent": 7},
        {"intent": {"value": INTENT}},
        {"intent": INTENT, "provider_mode": "HEALTHY"},
        {"intent": INTENT, "provider_mode": "healthy\u0000"},
        {"intent": INTENT, "principal_id": "attacker"},
        {"intent": INTENT, "status": "VERIFIED"},
    ],
)
def test_malformed_start_arguments_create_no_resolution(tmp_path, arguments):
    async def attack():
        service = make_service(tmp_path)
        server = create_mcp_server(service, principal_resolver=lambda: OWNER)
        async with Client(server, raise_exceptions=False) as client:
            rejected = await client.call_tool("start_resolution", arguments)
            listed = await client.call_tool("list_open_resolutions", {})
            return rejected, listed

    rejected, listed = asyncio.run(attack())
    assert rejected.is_error is True
    assert listed.structured_content["resolutions"] == []


@pytest.mark.parametrize(
    "tool_name", ["set_verdict", "mark_success", "force_pass", "SET_VERDICT"]
)
def test_forbidden_or_unknown_tool_names_cannot_mutate_state(tmp_path, tool_name):
    async def attack():
        service = make_service(tmp_path)
        server = create_mcp_server(service, principal_resolver=lambda: OWNER)
        async with Client(server, raise_exceptions=False) as client:
            rejected = await client.call_tool(tool_name, {"verdict": "PASS"})
            listed = await client.call_tool("list_open_resolutions", {})
            return rejected, listed

    rejected, listed = asyncio.run(attack())
    assert rejected.is_error is True
    assert listed.structured_content["resolutions"] == []


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": 1},
        {"iss": "https://attacker.invalid"},
        {"aud": "https://attacker.invalid/mcp"},
        {"sub": ""},
        {"sub": None},
        {"_secret": "wrong-secret-that-is-still-long-enough-for-hmac"},
    ],
)
def test_invalid_authentication_claims_fail_closed(tmp_path, claims):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    with TestClient(app) as client:
        response = client.post(
            "/mcp", headers=protocol_headers(token_for(**claims)), json=request
        )

    assert response.status_code == 401
    assert "traceback" not in response.text.lower()
    assert SECRET not in response.text


def test_payload_cannot_spoof_authenticated_principal(tmp_path):
    settings, verifier = make_auth()
    owner = principal_key(ISSUER, "principal-a")
    service = make_service(tmp_path)
    app = create_app(service, settings, verifier)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers=protocol_headers(token_for()),
            json=tool_request(
                "start_resolution",
                {"intent": INTENT, "principal_id": "principal-b", "owner_id": "owner-b"},
            ),
        )

    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True
    assert service.list_open_resolutions(owner) == []


@pytest.mark.parametrize(
    "candidate_transform",
    [
        lambda value: value,
        lambda value: value.upper(),
        lambda value: f"%7B{value}%7D",
        lambda value: f"{value} ",
        lambda value: "00000000-0000-0000-0000-000000000000",
    ],
)
def test_cross_principal_identifier_variants_are_indistinguishable(
    tmp_path, candidate_transform
):
    async def attack():
        current_owner = {"value": "owner-a"}
        service = make_service(tmp_path)
        server = create_mcp_server(
            service, principal_resolver=lambda: current_owner["value"]
        )
        async with Client(server, raise_exceptions=False) as client:
            started = await client.call_tool("start_resolution", {"intent": INTENT})
            resolution_id = started.structured_content["resolution_id"]
            current_owner["value"] = "owner-b"
            candidate = candidate_transform(resolution_id)
            rejected = await client.call_tool(
                "get_resolution_evidence", {"resolution_id": candidate}
            )
            missing = await client.call_tool(
                "get_resolution_evidence", {"resolution_id": "missing"}
            )
            return resolution_id, rejected, missing

    resolution_id, rejected, missing = asyncio.run(attack())
    rejected_text = rejected.content[0].text
    assert rejected.is_error is True
    assert rejected_text == missing.content[0].text
    assert resolution_id not in rejected_text
    assert INTENT not in rejected_text


def test_malformed_jsonrpc_and_unsupported_protocol_do_not_mutate(tmp_path):
    settings, verifier = make_auth()
    owner = principal_key(ISSUER, "principal-a")
    service = make_service(tmp_path)
    app = create_app(service, settings, verifier)
    with TestClient(app) as client:
        malformed_json = client.post(
            "/mcp",
            headers=protocol_headers(token_for()),
            content=b'{"jsonrpc":"2.0",',
        )
        malformed_rpc = client.post(
            "/mcp",
            headers=protocol_headers(token_for()),
            json={"jsonrpc": "1.0", "id": 2, "method": "tools/call", "params": {}},
        )
        unsupported = client.post(
            "/mcp",
            headers=protocol_headers(token_for(), version="1900-01-01"),
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
        )

    assert malformed_json.status_code in {400, 422}
    assert malformed_rpc.status_code == 400
    assert unsupported.status_code == 400
    assert service.list_open_resolutions(owner) == []


def test_readback_and_provider_factory_failures_are_never_verified(tmp_path):
    readback_failure = CountingProvider(
        evidence_error=TimeoutError("readback-secret")
    )
    service = make_service(tmp_path, readback_failure, name="readback.db")
    started = service.start_resolution(OWNER, INTENT)
    completed = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )
    assert completed["verdict"] == "INCONCLUSIVE"

    repository = SqlResolutionRepository(
        f"sqlite+pysqlite:///{tmp_path / 'factory.db'}"
    )

    def unavailable_factory(_):
        raise RuntimeError("factory-secret")

    unavailable = ResolutionService(repository, unavailable_factory)
    started = unavailable.start_resolution(OWNER, INTENT)
    completed = unavailable.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )
    assert completed["verdict"] == "INCONCLUSIVE"


class FailOnSaveRepository:
    def __init__(self, delegate, fail_on: int) -> None:
        self.delegate = delegate
        self.fail_on = fail_on
        self.save_count = 0

    def create(self, record):
        return self.delegate.create(record)

    def get_owned(self, resolution_id, owner_id):
        return self.delegate.get_owned(resolution_id, owner_id)

    def save_owned(self, record, expected_version):
        self.save_count += 1
        if self.save_count == self.fail_on:
            raise ResolutionStorageUnavailableError("database-secret")
        return self.delegate.save_owned(record, expected_version)

    def list_open_owned(self, owner_id, limit):
        return self.delegate.list_open_owned(owner_id, limit)


def test_partial_terminal_write_leaves_truthful_verifying_state(tmp_path):
    base = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'partial.db'}")
    failing = FailOnSaveRepository(base, fail_on=3)
    service = ResolutionService(failing)
    started = service.start_resolution(OWNER, INTENT)

    with pytest.raises(ResolutionStorageUnavailableError, match="database-secret"):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(started, OWNER),
        )

    persisted = ResolutionService(base).get_resolution_status(OWNER, started["resolution_id"])
    assert persisted["lifecycle_state"] == "VERIFYING"
    assert persisted["verdict"] is None


def test_unexpected_verifier_error_is_sanitized_and_never_verified(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    server = create_mcp_server(service, principal_resolver=lambda: OWNER)

    def broken_verifier(*_):
        raise RuntimeError("verifier-secret")

    monkeypatch.setattr("closeloop.lifecycle.verify_cancellation", broken_verifier)

    async def attack():
        async with Client(server, raise_exceptions=False) as client:
            started = await client.call_tool("start_resolution", {"intent": INTENT})
            resolution_id = started.structured_content["resolution_id"]
            result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": trusted_confirmation(
                        started.structured_content, OWNER
                    ),
                },
            )
            return resolution_id, result

    resolution_id, result = asyncio.run(attack())
    text = result.content[0].text
    assert result.is_error is True
    assert "verifier-secret" not in text
    assert "traceback" not in text.lower()
    status = service.get_resolution_status(OWNER, resolution_id)
    assert status["lifecycle_state"] == "VERIFYING"
    assert status["verdict"] is None


def test_storage_failure_error_does_not_leak_repository_details():
    service = ResolutionService(
        UnavailableResolutionRepository("dynamodb-table-secret us-east-1")
    )
    server = create_mcp_server(service, principal_resolver=lambda: OWNER)

    async def attack():
        async with Client(server, raise_exceptions=False) as client:
            return await client.call_tool("list_open_resolutions", {})

    result = asyncio.run(attack())
    text = result.content[0].text
    assert result.is_error is True
    assert "dynamodb-table-secret" not in text
    assert "us-east-1" not in text
    assert "traceback" not in text.lower()
    assert "temporarily unavailable" in text


def test_replayed_confirmation_cannot_execute_or_terminalize_twice(tmp_path):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    started = service.start_resolution(OWNER, INTENT)
    first = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )

    with pytest.raises(InvalidTransitionError):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(started, OWNER),
        )

    assert provider.execution_count == 1
    assert service.get_resolution_status(OWNER, started["resolution_id"]) == first


def test_same_owner_confirmation_binding_is_a_documented_residual(tmp_path):
    """A trusted confirmation for A cannot authorize same-owner B."""

    service = make_service(tmp_path)
    first = service.start_resolution(OWNER, "Cancel subscription A")
    second = service.start_resolution(OWNER, "Cancel subscription B")

    with pytest.raises(ResolutionError):
        service.confirm_resolution_action(
            OWNER,
            second["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(first, OWNER),
        )
    assert service.get_resolution_status(OWNER, first["resolution_id"])["verdict"] is None
    assert service.get_resolution_status(OWNER, second["resolution_id"])["verdict"] is None


def test_stale_confirmation_cannot_execute(tmp_path, monkeypatch):
    provider = CountingProvider()
    service = make_service(tmp_path, provider)
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    monkeypatch.setattr("closeloop.lifecycle._utc_now", lambda: now)
    started = service.start_resolution(OWNER, INTENT)
    attestation = trusted_confirmation(started, OWNER, now=now)
    monkeypatch.setattr("closeloop.lifecycle._utc_now", lambda: now + timedelta(days=1))

    with pytest.raises(ResolutionError):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=attestation,
        )
    assert provider.execution_count == 0


class BarrierRepository(SqlResolutionRepository):
    def __init__(self, database_url: str, barrier: Barrier) -> None:
        super().__init__(database_url)
        self.barrier = barrier
        self.synchronize_reads = False

    def get_owned(self, resolution_id: str, owner_id: str):
        record = super().get_owned(resolution_id, owner_id)
        if self.synchronize_reads:
            self.barrier.wait(timeout=5)
        return record


def test_concurrent_sql_confirmations_execute_provider_exactly_once(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'concurrent.db'}"
    barrier = Barrier(2)
    repository_a = BarrierRepository(database_url, barrier)
    repository_b = BarrierRepository(database_url, barrier)
    provider = CountingProvider()
    service_a = ResolutionService(repository_a, lambda _: provider)
    service_b = ResolutionService(repository_b, lambda _: provider)
    started = service_a.start_resolution(OWNER, INTENT)
    attestation = trusted_confirmation(started, OWNER)
    repository_a.synchronize_reads = True
    repository_b.synchronize_reads = True

    def confirm(service):
        try:
            return service.confirm_resolution_action(
                OWNER,
                started["resolution_id"],
                confirmed=True,
                confirmation_attestation=attestation,
            )
        except (ConcurrentResolutionUpdateError, InvalidTransitionError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, (service_a, service_b)))

    assert provider.execution_count == 1
    assert len([result for result in results if isinstance(result, dict)]) == 1
    terminal = ResolutionService(SqlResolutionRepository(database_url)).get_resolution_status(
        OWNER, started["resolution_id"]
    )
    assert terminal["verdict"] == "PASS"


def create_dynamodb_resource():
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    resource.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "owner_id", "AttributeType": "S"},
            {"AttributeName": "resolution_id", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "owner_id", "KeyType": "HASH"},
            {"AttributeName": "resolution_id", "KeyType": "RANGE"},
        ],
    )
    return resource


class BarrierDynamoRepository(DynamoDbResolutionRepository):
    def __init__(self, resource, barrier: Barrier) -> None:
        super().__init__(TABLE_NAME, dynamodb_resource=resource)
        self.barrier = barrier
        self.synchronize_reads = False

    def get_owned(self, resolution_id: str, owner_id: str):
        record = super().get_owned(resolution_id, owner_id)
        if self.synchronize_reads:
            self.barrier.wait(timeout=5)
        return record


def test_concurrent_dynamodb_confirmations_have_one_conditional_winner():
    with mock_aws():
        resource = create_dynamodb_resource()
        barrier = Barrier(2)
        repository_a = BarrierDynamoRepository(resource, barrier)
        repository_b = BarrierDynamoRepository(resource, barrier)
        provider = CountingProvider()
        service_a = ResolutionService(repository_a, lambda _: provider)
        service_b = ResolutionService(repository_b, lambda _: provider)
        started = service_a.start_resolution(OWNER, INTENT)
        attestation = trusted_confirmation(started, OWNER)
        repository_a.synchronize_reads = True
        repository_b.synchronize_reads = True

        def confirm(service):
            try:
                return service.confirm_resolution_action(
                    OWNER,
                    started["resolution_id"],
                    confirmed=True,
                    confirmation_attestation=attestation,
                )
            except (
                ConcurrentResolutionUpdateError,
                InvalidTransitionError,
                TerminalOutcomeImmutableError,
            ) as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(confirm, (service_a, service_b)))

        repository_a.synchronize_reads = False
        assert provider.execution_count == 1
        assert len([result for result in results if isinstance(result, dict)]) == 1
        terminal = repository_a.get_owned(started["resolution_id"], OWNER)
        assert terminal.verification.verdict is ResolutionVerdict.PASS
        execution_transition = next(
            item for item in terminal.state_history if item.state.value == "EXECUTING"
        )
        assert execution_transition.confirmation_attestation is not None
        restarted = ResolutionService(
            DynamoDbResolutionRepository(TABLE_NAME, dynamodb_resource=resource)
        )
        with pytest.raises(InvalidTransitionError):
            restarted.confirm_resolution_action(
                OWNER,
                started["resolution_id"],
                confirmed=True,
                confirmation_attestation=attestation,
            )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("independent_evidence", "freshness_seconds", -1),
        ("independent_evidence", "freshness_seconds", "0"),
        ("independent_evidence", "effective_end_date", "not-a-date"),
        ("independent_evidence", "effective_end_date", "20260930"),
        ("independent_evidence", "effective_end_date", "2026-W40-3"),
        ("execution_claim", "provider_reported_success", False),
    ],
)
def test_corrupt_dynamodb_evidence_cannot_preserve_stored_pass(section, field, value):
    with mock_aws():
        resource = create_dynamodb_resource()
        repository = DynamoDbResolutionRepository(TABLE_NAME, dynamodb_resource=resource)
        service = ResolutionService(repository)
        started = service.start_resolution(OWNER, INTENT)
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(started, OWNER),
        )
        table = resource.Table(TABLE_NAME)
        key = {"owner_id": OWNER, "resolution_id": started["resolution_id"]}
        item = table.get_item(Key=key, ConsistentRead=True)["Item"]
        item[section][field] = value
        table.put_item(Item=item)

        with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
            repository.get_owned(started["resolution_id"], OWNER)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confirmed_at", "2026-01-01T00:00:00Z"),
        ("execution_claim_observed_at", "2026-01-01T00:00:00Z"),
        ("independent_evidence_observed_at", "2026-01-01T00:00:00Z"),
        ("verified_at", "2030-01-01T00:00:00Z"),
        ("updated_at", "2026-01-01T00:00:00Z"),
    ],
)
def test_corrupt_dynamodb_provenance_timestamps_fail_closed(field, value):
    with mock_aws():
        resource = create_dynamodb_resource()
        repository = DynamoDbResolutionRepository(TABLE_NAME, dynamodb_resource=resource)
        service = ResolutionService(repository)
        started = service.start_resolution(OWNER, INTENT)
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(started, OWNER),
        )
        table = resource.Table(TABLE_NAME)
        key = {"owner_id": OWNER, "resolution_id": started["resolution_id"]}
        item = table.get_item(Key=key, ConsistentRead=True)["Item"]
        item[field] = value
        table.put_item(Item=item)

        with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
            repository.get_owned(started["resolution_id"], OWNER)


def test_corrupt_dynamodb_reordered_history_timestamps_fail_closed():
    with mock_aws():
        resource = create_dynamodb_resource()
        repository = DynamoDbResolutionRepository(TABLE_NAME, dynamodb_resource=resource)
        service = ResolutionService(repository)
        started = service.start_resolution(OWNER, INTENT)
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=trusted_confirmation(started, OWNER),
        )
        table = resource.Table(TABLE_NAME)
        key = {"owner_id": OWNER, "resolution_id": started["resolution_id"]}
        item = table.get_item(Key=key, ConsistentRead=True)["Item"]
        item["state_history"][2]["occurred_at"] = "2030-01-01T00:00:00Z"
        table.put_item(Item=item)

        with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
            repository.get_owned(started["resolution_id"], OWNER)
