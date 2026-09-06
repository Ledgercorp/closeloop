from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import NoReturn

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from .lifecycle import (
    TERMINAL_STATES,
    ConcurrentResolutionUpdateError,
    InvalidTransitionError,
    LifecycleState,
    ResolutionError,
    ResolutionNotFoundError,
    ResolutionRecord,
    ResolutionRepository,
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


_metadata = MetaData()
_resolutions = Table(
    "closeloop_resolutions",
    _metadata,
    Column("resolution_id", String(36), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("intent", Text, nullable=False),
    Column("provider_mode", String(32), nullable=False),
    Column("state", String(32), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True)),
    Column("execution_claim", JSON),
    Column("execution_claim_observed_at", DateTime(timezone=True)),
    Column("independent_evidence", JSON),
    Column("independent_evidence_observed_at", DateTime(timezone=True)),
    Column("verification", JSON),
    Column("verified_at", DateTime(timezone=True)),
    Column("state_history", JSON, nullable=False),
    Column("version", Integer, nullable=False),
)


class SqlResolutionRepository:
    """Durable owner-scoped repository for SQLite or PostgreSQL.

    Conditional updates provide optimistic serialization across instances.
    Updates whose stored state is already terminal never match, making terminal
    outcomes immutable through this repository.
    """

    def __init__(self, database_url: str) -> None:
        normalized_url = self._normalize_url(database_url)
        connect_args = {"check_same_thread": False} if normalized_url.startswith("sqlite") else {}
        self._engine: Engine = create_engine(
            normalized_url,
            poolclass=NullPool,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._schema_lock = Lock()
        self._schema_ready = False

    @staticmethod
    def _normalize_url(database_url: str) -> str:
        if database_url.startswith("postgres://"):
            return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
        if database_url.startswith("postgresql://"):
            return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
        return database_url

    def create(self, record: ResolutionRecord) -> None:
        self._ensure_schema()
        validate_new_record(record)
        try:
            with self._engine.begin() as connection:
                connection.execute(insert(_resolutions).values(**record_to_mapping(record)))
        except IntegrityError as exc:
            raise ResolutionError(f"resolution already exists: {record.resolution_id}") from exc
        except SQLAlchemyError as exc:
            raise ResolutionStorageUnavailableError("durable resolution storage failed") from exc

    def get_owned(self, resolution_id: str, owner_id: str) -> ResolutionRecord:
        self._ensure_schema()
        try:
            with self._engine.connect() as connection:
                row = connection.execute(
                    select(_resolutions).where(
                        _resolutions.c.resolution_id == resolution_id,
                        _resolutions.c.owner_id == owner_id,
                    )
                ).mappings().one_or_none()
        except SQLAlchemyError as exc:
            raise ResolutionStorageUnavailableError("durable resolution storage failed") from exc
        if row is None:
            raise ResolutionNotFoundError(f"unknown resolution: {resolution_id}")
        return record_from_mapping(row)

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None:
        self._ensure_schema()
        if record.version != expected_version:
            raise ConcurrentResolutionUpdateError(
                f"resolution version does not match expected version: {record.resolution_id}"
            )
        expected_history = expected_previous_history(record)
        next_version = expected_version + 1
        values = record_to_mapping(record)
        values["version"] = next_version
        try:
            with self._engine.begin() as connection:
                current = connection.execute(
                    select(
                        _resolutions.c.state,
                        _resolutions.c.version,
                        _resolutions.c.state_history,
                    ).where(
                        _resolutions.c.resolution_id == record.resolution_id,
                        _resolutions.c.owner_id == record.owner_id,
                    )
                ).mappings().one_or_none()
                if current is None:
                    raise ResolutionNotFoundError(
                        f"unknown resolution: {record.resolution_id}"
                    )
                if LifecycleState(current["state"]) in TERMINAL_STATES:
                    raise TerminalOutcomeImmutableError(
                        f"terminal outcome is immutable for resolution: {record.resolution_id}"
                    )
                if current["version"] != expected_version:
                    raise ConcurrentResolutionUpdateError(
                        f"resolution changed on another instance: {record.resolution_id}"
                    )
                if LifecycleState(current["state"]) not in allowed_previous_states(record.state):
                    raise InvalidTransitionError(
                        f"transition {current['state']} -> {record.state.value} is not allowed"
                    )
                if current["state_history"] != expected_history:
                    raise ConcurrentResolutionUpdateError(
                        f"resolution history changed: {record.resolution_id}"
                    )
                validate_target_record(record)
                result = connection.execute(
                    _owned_transition_update(
                        resolution_id=record.resolution_id,
                        owner_id=record.owner_id,
                        expected_version=expected_version,
                        next_state=record.state,
                    ).values(**values)
                )
                if result.rowcount == 1:
                    record.version = next_version
                    return
                raise ConcurrentResolutionUpdateError(
                    f"resolution changed on another instance: {record.resolution_id}"
                )
        except ResolutionError:
            raise
        except SQLAlchemyError as exc:
            raise ResolutionStorageUnavailableError("durable resolution storage failed") from exc

    def list_open_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]:
        self._ensure_schema()
        try:
            with self._engine.connect() as connection:
                rows = connection.execute(
                    select(_resolutions)
                    .where(
                        _resolutions.c.owner_id == owner_id,
                        _resolutions.c.state.not_in([state.value for state in TERMINAL_STATES]),
                    )
                    .order_by(_resolutions.c.created_at)
                    .limit(limit)
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise ResolutionStorageUnavailableError("durable resolution storage failed") from exc
        return [record_from_mapping(row) for row in rows]

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            try:
                _metadata.create_all(self._engine)
            except SQLAlchemyError as exc:
                raise ResolutionStorageUnavailableError(
                    "durable resolution storage is unavailable"
                ) from exc
            self._schema_ready = True


def _owned_transition_update(
    *,
    resolution_id: str,
    owner_id: str,
    expected_version: int,
    next_state: LifecycleState,
):
    """Build the cross-dialect atomic transition predicate.

    Exact prior history is compared after the owner-scoped read. Version and state provide the
    atomic write guard; the JSON column is deliberately absent because PostgreSQL `json` has no
    equality operator.
    """

    return update(_resolutions).where(
        _resolutions.c.resolution_id == resolution_id,
        _resolutions.c.owner_id == owner_id,
        _resolutions.c.version == expected_version,
        _resolutions.c.state.not_in([state.value for state in TERMINAL_STATES]),
        _resolutions.c.state.in_(
            [state.value for state in allowed_previous_states(next_state)]
        ),
    )


class UnavailableResolutionRepository:
    def __init__(
        self,
        message: str = (
            "CLOSELOOP_DYNAMODB_TABLE, CLOSELOOP_DATABASE_URL, or DATABASE_URL "
            "is required in serverless environments"
        ),
    ) -> None:
        self._message = message

    def _fail(self) -> NoReturn:
        raise ResolutionStorageUnavailableError(self._message)

    def create(self, record: ResolutionRecord) -> None:
        self._fail()

    def get_owned(self, resolution_id: str, owner_id: str) -> ResolutionRecord:
        self._fail()

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None:
        self._fail()

    def list_open_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]:
        self._fail()


def create_repository_from_environment() -> ResolutionRepository:
    dynamodb_table = os.getenv("CLOSELOOP_DYNAMODB_TABLE")
    if dynamodb_table is not None:
        if not dynamodb_table.strip():
            return UnavailableResolutionRepository(
                "CLOSELOOP_DYNAMODB_TABLE must be a non-empty table name"
            )
        from .dynamodb_repository import DynamoDbResolutionRepository

        return DynamoDbResolutionRepository(
            dynamodb_table,
            region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
            endpoint_url=os.getenv("CLOSELOOP_DYNAMODB_ENDPOINT_URL"),
        )
    database_url = (
        os.getenv("CLOSELOOP_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
    )
    if database_url:
        return SqlResolutionRepository(database_url)
    if os.getenv("VERCEL"):
        return UnavailableResolutionRepository()

    database_path = Path(
        os.getenv("CLOSELOOP_SQLITE_PATH", str(Path.cwd() / ".closeloop" / "resolutions.db"))
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return SqlResolutionRepository(f"sqlite+pysqlite:///{database_path}")
