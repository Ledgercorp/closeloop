from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from .lifecycle import (
    TERMINAL_STATES,
    ConcurrentResolutionUpdateError,
    InvalidTransitionError,
    ResolutionError,
    ResolutionNotFoundError,
    ResolutionRecord,
    ResolutionStorageUnavailableError,
    TerminalOutcomeImmutableError,
    allowed_previous_states,
)
from .repository_contract import (
    expected_previous_history,
    record_from_mapping,
    record_to_mapping,
    validate_new_record,
    validate_target_record,
)


_SAFE_ITEM_SIZE_BYTES = 350 * 1024
_CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"


class DynamoDbResolutionRepository:
    """Owner-scoped durable repository backed by a pre-provisioned table."""

    def __init__(
        self,
        table_name: str,
        *,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        dynamodb_resource: Any | None = None,
    ) -> None:
        if not table_name or not table_name.strip():
            raise ResolutionStorageUnavailableError(
                "CLOSELOOP_DYNAMODB_TABLE must be a non-empty table name"
            )
        self._table_name = table_name.strip()
        try:
            resource = dynamodb_resource or boto3.resource(
                "dynamodb", region_name=region_name, endpoint_url=endpoint_url
            )
            self._table = resource.Table(self._table_name)
        except (BotoCoreError, ClientError, ValueError) as exc:
            raise ResolutionStorageUnavailableError(
                "durable resolution storage is unavailable"
            ) from exc

    def create(self, record: ResolutionRecord) -> None:
        validate_new_record(record)
        item = record_to_mapping(record, serialize_datetimes=True)
        self._validate_item_size(item)
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=(
                    "attribute_not_exists(#owner) AND attribute_not_exists(#resolution)"
                ),
                ExpressionAttributeNames={
                    "#owner": "owner_id",
                    "#resolution": "resolution_id",
                },
            )
        except ClientError as exc:
            if self._error_code(exc) == _CONDITIONAL_CHECK_FAILED:
                raise ResolutionError(
                    f"resolution already exists: {record.resolution_id}"
                ) from exc
            self._raise_storage_error(exc)
        except BotoCoreError as exc:
            self._raise_storage_error(exc)

    def get_owned(self, resolution_id: str, owner_id: str) -> ResolutionRecord:
        try:
            response = self._table.get_item(
                Key={"owner_id": owner_id, "resolution_id": resolution_id},
                ConsistentRead=True,
            )
        except (BotoCoreError, ClientError) as exc:
            self._raise_storage_error(exc)
        item = response.get("Item")
        if item is None:
            raise ResolutionNotFoundError(f"unknown resolution: {resolution_id}")
        return record_from_mapping(self._mapping(item))

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None:
        if record.version != expected_version:
            raise ConcurrentResolutionUpdateError(
                f"resolution version does not match expected version: {record.resolution_id}"
            )
        validate_target_record(record)
        predecessors = sorted(
            allowed_previous_states(record.state), key=lambda state: state.value
        )
        if not predecessors:
            raise InvalidTransitionError(
                f"no persisted state can transition to {record.state.value}"
            )

        next_version = expected_version + 1
        item = record_to_mapping(record, serialize_datetimes=True)
        item["version"] = next_version
        self._validate_item_size(item)
        values: dict[str, object] = {":expected_version": expected_version}
        values[":expected_history"] = expected_previous_history(record)
        state_tokens = []
        for index, state in enumerate(predecessors):
            token = f":previous_state_{index}"
            state_tokens.append(token)
            values[token] = state.value
        condition = (
            "attribute_exists(#owner) AND attribute_exists(#resolution) "
            "AND #version = :expected_version "
            "AND #history = :expected_history "
            f"AND #state IN ({', '.join(state_tokens)})"
        )
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=condition,
                ExpressionAttributeNames={
                    "#owner": "owner_id",
                    "#resolution": "resolution_id",
                    "#state": "state",
                    "#version": "version",
                    "#history": "state_history",
                },
                ExpressionAttributeValues=values,
            )
        except ClientError as exc:
            if self._error_code(exc) == _CONDITIONAL_CHECK_FAILED:
                self._classify_failed_save(record, expected_version)
            self._raise_storage_error(exc)
        except BotoCoreError as exc:
            self._raise_storage_error(exc)
        record.version = next_version

    def list_open_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]:
        records: list[ResolutionRecord] = []
        exclusive_start_key: Mapping[str, object] | None = None
        try:
            while True:
                request: dict[str, object] = {
                    "KeyConditionExpression": Key("owner_id").eq(owner_id),
                    "ConsistentRead": True,
                }
                if exclusive_start_key is not None:
                    request["ExclusiveStartKey"] = exclusive_start_key
                response = self._table.query(**request)
                for item in response.get("Items", []):
                    record = record_from_mapping(self._mapping(item))
                    if record.state not in TERMINAL_STATES:
                        records.append(record)
                next_key = response.get("LastEvaluatedKey")
                if not next_key:
                    break
                exclusive_start_key = self._mapping(next_key)
        except ResolutionStorageUnavailableError:
            raise
        except (BotoCoreError, ClientError) as exc:
            self._raise_storage_error(exc)
        records.sort(key=lambda record: (record.created_at, record.resolution_id))
        return records[:limit]

    def _classify_failed_save(
        self, record: ResolutionRecord, expected_version: int
    ) -> None:
        try:
            response = self._table.get_item(
                Key={
                    "owner_id": record.owner_id,
                    "resolution_id": record.resolution_id,
                },
                ConsistentRead=True,
            )
        except (BotoCoreError, ClientError) as exc:
            self._raise_storage_error(exc)
        item = response.get("Item")
        if item is None:
            raise ResolutionNotFoundError(f"unknown resolution: {record.resolution_id}")
        stored = record_from_mapping(self._mapping(item))
        if stored.state in TERMINAL_STATES:
            raise TerminalOutcomeImmutableError(
                f"terminal outcome is immutable for resolution: {record.resolution_id}"
            )
        if stored.version != expected_version:
            raise ConcurrentResolutionUpdateError(
                f"resolution changed on another instance: {record.resolution_id}"
            )
        raise InvalidTransitionError(
            f"transition {stored.state.value} -> {record.state.value} is not allowed"
        )

    @staticmethod
    def _mapping(value: object) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ResolutionStorageUnavailableError("stored resolution record is invalid")
        return value

    @staticmethod
    def _validate_item_size(item: Mapping[str, object]) -> None:
        # This conservative JSON bound leaves headroom below DynamoDB's 400 KB limit.
        serialized = json.dumps(item, separators=(",", ":"), ensure_ascii=True)
        if len(serialized.encode("utf-8")) > _SAFE_ITEM_SIZE_BYTES:
            raise ResolutionStorageUnavailableError(
                "resolution record exceeds the safe DynamoDB item-size limit"
            )

    @staticmethod
    def _error_code(exc: ClientError) -> str:
        return str(exc.response.get("Error", {}).get("Code", ""))

    @staticmethod
    def _raise_storage_error(exc: Exception) -> None:
        raise ResolutionStorageUnavailableError(
            "durable resolution storage failed"
        ) from exc
