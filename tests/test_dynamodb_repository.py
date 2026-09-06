from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

from closeloop.dynamodb_repository import DynamoDbResolutionRepository
from closeloop.confirmation import CONFIRMATION_CONTRACT_VERSION
from closeloop.lifecycle import (
    ConcurrentResolutionUpdateError,
    InvalidTransitionError,
    LifecycleState,
    ResolutionNotFoundError,
    ResolutionRecord,
    ResolutionError,
    ResolutionService,
    ResolutionStorageUnavailableError,
    StateTransition,
    TerminalOutcomeImmutableError,
)
from closeloop.repository import (
    SqlResolutionRepository,
    UnavailableResolutionRepository,
    create_repository_from_environment,
)
from closeloop.repository_contract import record_from_mapping, record_to_mapping
from tests.confirmation_support import trusted_confirmation, verified_test_confirmation


OWNER_A = "owner-a"
OWNER_B = "owner-b"
INTENT = "Cancel my subscription and make sure I will not be charged again."
TABLE_NAME = "closeloop-resolutions-test"


def create_resource():
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


@pytest.fixture
def aws_resource():
    with mock_aws():
        yield create_resource()


def repository_for(resource):
    return DynamoDbResolutionRepository(TABLE_NAME, dynamodb_resource=resource)


@pytest.mark.parametrize(
    ("provider_mode", "verdict", "consumer_state"),
    [
        ("healthy", "PASS", "Verified"),
        ("false_success", "FAIL", "Not completed"),
        ("evidence_outage", "INCONCLUSIVE", "Awaiting proof"),
    ],
)
def test_lifecycle_and_evidence_survive_repository_reinstantiation(
    aws_resource, provider_mode, verdict, consumer_state
):
    first = ResolutionService(repository_for(aws_resource))
    started = first.start_resolution(OWNER_A, INTENT, provider_mode)

    second = ResolutionService(repository_for(aws_resource))
    assert second.get_resolution_status(OWNER_A, started["resolution_id"]) == started
    terminal = second.confirm_resolution_action(
        OWNER_A,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER_A),
    )

    restarted = ResolutionService(repository_for(aws_resource))
    status = restarted.get_resolution_status(OWNER_A, started["resolution_id"])
    evidence = restarted.get_resolution_evidence(OWNER_A, started["resolution_id"])
    assert status == terminal
    assert status["verdict"] == verdict
    assert status["consumer_state"] == consumer_state
    assert evidence["verification"]["verdict"] == verdict
    assert evidence["execution_claim"]["provider_reported_success"] is True
    assert evidence["independent_read_back"] is not None


def test_owner_isolation_confirmation_and_open_list(aws_resource):
    service = ResolutionService(repository_for(aws_resource))
    started = service.start_resolution(OWNER_A, INTENT)

    with pytest.raises(ResolutionNotFoundError, match="unknown resolution"):
        service.get_resolution_status(OWNER_B, started["resolution_id"])
    with pytest.raises(ResolutionNotFoundError, match="unknown resolution"):
        service.confirm_resolution_action(OWNER_B, started["resolution_id"], confirmed=True)
    with pytest.raises(ResolutionError, match="explicit confirmation"):
        service.confirm_resolution_action(OWNER_A, started["resolution_id"], confirmed=False)
    assert service.list_open_resolutions(OWNER_B) == []
    assert service.list_open_resolutions(OWNER_A)[0]["resolution_id"] == started["resolution_id"]


def test_stale_writer_and_terminal_overwrite_fail_atomically(aws_resource):
    repository_a = repository_for(aws_resource)
    repository_b = repository_for(aws_resource)
    service = ResolutionService(repository_a)
    started = service.start_resolution(OWNER_A, INTENT)
    record_a = repository_a.get_owned(started["resolution_id"], OWNER_A)
    record_b = repository_b.get_owned(started["resolution_id"], OWNER_A)

    record_a.confirmed_at = record_a.updated_at
    record_a.state = LifecycleState.EXECUTING
    record_a.state_history.append(
        StateTransition(
            LifecycleState.EXECUTING,
            record_a.updated_at,
            confirmation_attestation=verified_test_confirmation(
                started, OWNER_A, now=record_a.updated_at
            ),
        )
    )
    repository_a.save_owned(record_a, expected_version=record_a.version)

    record_b.confirmed_at = record_b.updated_at
    record_b.state = LifecycleState.EXECUTING
    record_b.state_history.append(
        StateTransition(
            LifecycleState.EXECUTING,
            record_b.updated_at,
            confirmation_attestation=verified_test_confirmation(
                started, OWNER_A, now=record_b.updated_at
            ),
        )
    )
    with pytest.raises(ConcurrentResolutionUpdateError, match="another instance"):
        repository_b.save_owned(record_b, expected_version=record_b.version)

    terminal_started = service.start_resolution(OWNER_A, "terminal record")
    service.confirm_resolution_action(
        OWNER_A,
        terminal_started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(terminal_started, OWNER_A),
    )
    terminal = repository_a.get_owned(terminal_started["resolution_id"], OWNER_A)
    version = terminal.version
    template_started = service.start_resolution(OWNER_A, "replacement attempt")
    replacement = repository_a.get_owned(template_started["resolution_id"], OWNER_A)
    replacement.resolution_id = terminal.resolution_id
    replacement.version = version
    with pytest.raises(TerminalOutcomeImmutableError, match="immutable"):
        repository_a.save_owned(replacement, expected_version=version)
    assert (
        repository_a.get_owned(terminal_started["resolution_id"], OWNER_A).version
        == version
    )


def test_illegal_jump_and_missing_confirmation_are_rejected(aws_resource):
    repository = repository_for(aws_resource)
    service = ResolutionService(repository)
    started = service.start_resolution(OWNER_A, INTENT)
    record = repository.get_owned(started["resolution_id"], OWNER_A)
    record.state = LifecycleState.VERIFYING
    with pytest.raises(InvalidTransitionError):
        repository.save_owned(record, expected_version=record.version)

    record = repository.get_owned(started["resolution_id"], OWNER_A)
    record.state = LifecycleState.EXECUTING
    record.state_history.append(StateTransition(LifecycleState.EXECUTING, record.updated_at))
    with pytest.raises(InvalidTransitionError, match="explicit confirmation"):
        repository.save_owned(record, expected_version=record.version)


class _PagedTable:
    def __init__(self, table):
        self._table = table
        self.calls: list[dict[str, object]] = []

    def put_item(self, **kwargs):
        self.calls.append({"operation": "put_item", **deepcopy(kwargs)})
        return self._table.put_item(**kwargs)

    def get_item(self, **kwargs):
        self.calls.append({"operation": "get_item", **deepcopy(kwargs)})
        return self._table.get_item(**kwargs)

    def query(self, **kwargs):
        self.calls.append({"operation": "query", **deepcopy(kwargs)})
        return self._table.query(Limit=1, **kwargs)


class _ResourceWrapper:
    def __init__(self, table):
        self.table = table

    def Table(self, name):
        assert name == TABLE_NAME
        return self.table


def test_requests_use_conditions_consistent_reads_and_paginated_created_order(aws_resource):
    spy = _PagedTable(aws_resource.Table(TABLE_NAME))
    repository = repository_for(_ResourceWrapper(spy))
    service = ResolutionService(repository)
    first = service.start_resolution(OWNER_A, "first")
    terminal = service.start_resolution(OWNER_A, "terminal")
    service.confirm_resolution_action(
        OWNER_A,
        terminal["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(terminal, OWNER_A),
    )
    second = service.start_resolution(OWNER_A, "second")
    third = service.start_resolution(OWNER_A, "third")

    open_records = service.list_open_resolutions(OWNER_A, limit=2)
    assert [item["resolution_id"] for item in open_records] == [
        first["resolution_id"],
        second["resolution_id"],
    ]
    assert len([call for call in spy.calls if call["operation"] == "query"]) > 1
    assert all(
        call["ConsistentRead"] is True
        for call in spy.calls
        if call["operation"] in {"get_item", "query"}
    )

    create_call = next(call for call in spy.calls if call["operation"] == "put_item")
    assert "attribute_not_exists(#owner)" in create_call["ConditionExpression"]
    assert "attribute_not_exists(#resolution)" in create_call["ConditionExpression"]
    save_call = next(
        call
        for call in spy.calls
        if call["operation"] == "put_item" and "#version" in call["ConditionExpression"]
    )
    assert "#state IN" in save_call["ConditionExpression"]
    assert save_call["ExpressionAttributeNames"]["#state"] == "state"
    assert save_call["ExpressionAttributeNames"]["#version"] == "version"
    assert save_call["ExpressionAttributeNames"]["#history"] == "state_history"
    assert third["resolution_id"] not in [item["resolution_id"] for item in open_records]


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("verification", "consumer_state", "Not completed"),
        ("independent_evidence", "auto_renew", True),
        ("independent_evidence", "account_readable", False),
        ("independent_evidence", "effective_end_date", None),
    ],
)
def test_corrupt_terminal_result_or_evidence_fails_closed(
    aws_resource, section, field, value
):
    repository = repository_for(aws_resource)
    service = ResolutionService(repository)
    started = service.start_resolution(OWNER_A, INTENT)
    service.confirm_resolution_action(
        OWNER_A,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER_A),
    )
    table = aws_resource.Table(TABLE_NAME)
    response = table.get_item(
        Key={"owner_id": OWNER_A, "resolution_id": started["resolution_id"]}
    )
    item = response["Item"]
    item[section][field] = value
    table.put_item(Item=item)

    with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
        repository.get_owned(started["resolution_id"], OWNER_A)


def test_shared_codec_preserves_sql_and_dynamodb_record_contract(tmp_path):
    sql = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'codec.db'}")
    service = ResolutionService(sql)
    started = service.start_resolution(OWNER_A, INTENT)
    record = sql.get_owned(started["resolution_id"], OWNER_A)

    restored = record_from_mapping(record_to_mapping(record, serialize_datetimes=True))
    assert record_to_mapping(restored) == record_to_mapping(record)


def test_shared_codec_rejects_evidence_that_no_longer_supports_stored_pass(tmp_path):
    sql = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'corrupt.db'}")
    service = ResolutionService(sql)
    started = service.start_resolution(OWNER_A, INTENT)
    service.confirm_resolution_action(
        OWNER_A,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER_A),
    )
    record = sql.get_owned(started["resolution_id"], OWNER_A)
    mapping = record_to_mapping(record, serialize_datetimes=True)
    mapping["independent_evidence"]["auto_renew"] = True

    with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
        record_from_mapping(mapping)


def test_item_size_guard_fails_before_aws_write(aws_resource):
    repository = repository_for(aws_resource)
    now = datetime.now(timezone.utc)
    oversized_record = ResolutionRecord(
        resolution_id="oversized-record",
        owner_id=OWNER_A,
        intent="x" * (351 * 1024),
        provider_mode="healthy",
        state=LifecycleState.AWAITING_CONFIRMATION,
        created_at=now,
        updated_at=now,
        state_history=[
            StateTransition(
                LifecycleState.REQUESTED,
                now,
                confirmation_contract_version=CONFIRMATION_CONTRACT_VERSION,
            ),
            StateTransition(LifecycleState.AWAITING_CONFIRMATION, now),
        ],
    )
    with pytest.raises(ResolutionStorageUnavailableError, match="item-size"):
        repository.create(oversized_record)
    assert aws_resource.Table(TABLE_NAME).scan()["Count"] == 0


class _FailingTable:
    def __init__(self, failure):
        self.failure = failure

    def get_item(self, **kwargs):
        raise self.failure

    def query(self, **kwargs):
        raise self.failure

    def put_item(self, **kwargs):
        raise self.failure


@pytest.mark.parametrize(
    "failure",
    [
        ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "missing"}},
            "GetItem",
        ),
        ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "GetItem",
        ),
        ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow"}},
            "GetItem",
        ),
        ClientError(
            {"Error": {"Code": "ValidationException", "Message": "invalid"}},
            "GetItem",
        ),
        EndpointConnectionError(endpoint_url="http://127.0.0.1:9"),
    ],
)
def test_aws_service_failures_map_to_storage_unavailable(failure):
    repository = DynamoDbResolutionRepository(
        TABLE_NAME, dynamodb_resource=_ResourceWrapper(_FailingTable(failure))
    )
    with pytest.raises(ResolutionStorageUnavailableError, match="storage failed"):
        repository.get_owned("resolution", OWNER_A)
    with pytest.raises(ResolutionStorageUnavailableError, match="storage failed"):
        repository.list_open_owned(OWNER_A, 50)
    with pytest.raises(ResolutionStorageUnavailableError, match="storage failed"):
        ResolutionService(repository).start_resolution(OWNER_A, INTENT)


def test_environment_selects_explicit_dynamodb_before_sql(aws_resource, monkeypatch):
    monkeypatch.setenv("CLOSELOOP_DYNAMODB_TABLE", TABLE_NAME)
    monkeypatch.setenv("CLOSELOOP_DATABASE_URL", "sqlite+pysqlite:///should-not-be-used.db")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    repository = create_repository_from_environment()
    assert isinstance(repository, DynamoDbResolutionRepository)


def test_blank_explicit_dynamodb_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("CLOSELOOP_DYNAMODB_TABLE", "   ")
    monkeypatch.setenv("CLOSELOOP_DATABASE_URL", "sqlite+pysqlite:///should-not-be-used.db")
    repository = create_repository_from_environment()
    assert isinstance(repository, UnavailableResolutionRepository)
    with pytest.raises(ResolutionStorageUnavailableError, match="non-empty"):
        repository.list_open_owned(OWNER_A, 50)
