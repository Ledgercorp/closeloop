from __future__ import annotations

import os
from datetime import datetime, timezone
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
from sqlalchemy.engine import Engine, RowMapping
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
    StateTransition,
    TerminalOutcomeImmutableError,
    allowed_previous_states,
)
from .models import (
    ActionReceipt,
    CancellationEvidence,
    ConsumerState,
    ResolutionVerdict,
    VerificationResult,
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


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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
        self._validate_new_record(record)
        try:
            with self._engine.begin() as connection:
                connection.execute(insert(_resolutions).values(**self._record_values(record)))
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
        return self._record_from_row(row)

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None:
        self._ensure_schema()
        terminal_values = [state.value for state in TERMINAL_STATES]
        predecessor_values = [state.value for state in allowed_previous_states(record.state)]
        next_version = expected_version + 1
        values = self._record_values(record)
        values["version"] = next_version
        try:
            with self._engine.begin() as connection:
                current = connection.execute(
                    select(_resolutions.c.state, _resolutions.c.version).where(
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
                self._validate_target_record(record)
                result = connection.execute(
                    update(_resolutions)
                    .where(
                        _resolutions.c.resolution_id == record.resolution_id,
                        _resolutions.c.owner_id == record.owner_id,
                        _resolutions.c.version == expected_version,
                        _resolutions.c.state.not_in(terminal_values),
                        _resolutions.c.state.in_(predecessor_values),
                    )
                    .values(**values)
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
        return [self._record_from_row(row) for row in rows]

    @staticmethod
    def _validate_new_record(record: ResolutionRecord) -> None:
        if not record.owner_id.strip():
            raise InvalidTransitionError("new resolution requires an authenticated owner")
        if record.state is not LifecycleState.AWAITING_CONFIRMATION or record.version != 0:
            raise InvalidTransitionError(
                "new resolution must begin in AWAITING_CONFIRMATION at version zero"
            )
        if [item.state for item in record.state_history] != [
            LifecycleState.REQUESTED,
            LifecycleState.AWAITING_CONFIRMATION,
        ]:
            raise InvalidTransitionError("new resolution has invalid state history")
        SqlResolutionRepository._validate_target_record(record)

    @staticmethod
    def _validate_target_record(record: ResolutionRecord) -> None:
        if not record.state_history or record.state_history[-1].state is not record.state:
            raise InvalidTransitionError("state history does not match current state")
        if record.state is LifecycleState.AWAITING_CONFIRMATION:
            if any(
                value is not None
                for value in (
                    record.confirmed_at,
                    record.execution_claim,
                    record.execution_claim_observed_at,
                    record.independent_evidence,
                    record.independent_evidence_observed_at,
                    record.verification,
                    record.verified_at,
                )
            ):
                raise InvalidTransitionError(
                    "unconfirmed resolution cannot contain execution or verifier evidence"
                )
            return
        if record.confirmed_at is None:
            raise InvalidTransitionError("execution requires persisted explicit confirmation")
        if record.state is LifecycleState.EXECUTING:
            if any(
                value is not None
                for value in (
                    record.execution_claim,
                    record.execution_claim_observed_at,
                    record.independent_evidence,
                    record.independent_evidence_observed_at,
                    record.verification,
                    record.verified_at,
                )
            ):
                raise InvalidTransitionError("executing resolution cannot contain later evidence")
            return
        if record.execution_claim is None or record.execution_claim_observed_at is None:
            raise InvalidTransitionError("verification requires persisted execution evidence")
        if record.state is LifecycleState.VERIFYING:
            if any(
                value is not None
                for value in (
                    record.independent_evidence,
                    record.independent_evidence_observed_at,
                    record.verification,
                    record.verified_at,
                )
            ):
                raise InvalidTransitionError(
                    "verifying resolution cannot contain a terminal verifier result"
                )
            return
        if record.state in TERMINAL_STATES:
            if (
                record.independent_evidence is None
                or record.independent_evidence_observed_at is None
                or record.verification is None
                or record.verified_at is None
            ):
                raise InvalidTransitionError("terminal state requires complete verifier evidence")
            expected_state = {
                ResolutionVerdict.PASS: LifecycleState.VERIFIED,
                ResolutionVerdict.FAIL: LifecycleState.NOT_COMPLETED,
                ResolutionVerdict.INCONCLUSIVE: LifecycleState.AWAITING_PROOF,
            }[record.verification.verdict]
            if record.state is not expected_state:
                raise InvalidTransitionError("terminal state does not match verifier evidence")
            if (
                record.execution_claim != record.verification.action_receipt
                or record.independent_evidence != record.verification.evidence
            ):
                raise InvalidTransitionError("terminal verifier inputs do not match stored evidence")
            return
        raise InvalidTransitionError(f"unsupported persisted state: {record.state.value}")

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

    @staticmethod
    def _record_values(record: ResolutionRecord) -> dict[str, object]:
        return {
            "resolution_id": record.resolution_id,
            "owner_id": record.owner_id,
            "intent": record.intent,
            "provider_mode": record.provider_mode,
            "state": record.state.value,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "confirmed_at": record.confirmed_at,
            "execution_claim": (
                {
                    "request_id": record.execution_claim.request_id,
                    "provider_reported_success": record.execution_claim.provider_reported_success,
                    "message": record.execution_claim.message,
                }
                if record.execution_claim
                else None
            ),
            "execution_claim_observed_at": record.execution_claim_observed_at,
            "independent_evidence": (
                {
                    "account_readable": record.independent_evidence.account_readable,
                    "auto_renew": record.independent_evidence.auto_renew,
                    "effective_end_date": record.independent_evidence.effective_end_date,
                    "freshness_seconds": record.independent_evidence.freshness_seconds,
                }
                if record.independent_evidence
                else None
            ),
            "independent_evidence_observed_at": record.independent_evidence_observed_at,
            "verification": (
                {
                    "verdict": record.verification.verdict.value,
                    "consumer_state": record.verification.consumer_state.value,
                    "reason": record.verification.reason,
                }
                if record.verification
                else None
            ),
            "verified_at": record.verified_at,
            "state_history": [
                {"state": item.state.value, "occurred_at": _iso(item.occurred_at)}
                for item in record.state_history
            ],
            "version": record.version,
        }

    @staticmethod
    def _record_from_row(row: RowMapping) -> ResolutionRecord:
        receipt_data = row["execution_claim"]
        evidence_data = row["independent_evidence"]
        verification_data = row["verification"]
        receipt = ActionReceipt(**receipt_data) if receipt_data else None
        evidence = CancellationEvidence(**evidence_data) if evidence_data else None
        verification = None
        if verification_data:
            if receipt is None or evidence is None:
                raise ResolutionStorageUnavailableError("stored verifier evidence is incomplete")
            verification = VerificationResult(
                verdict=ResolutionVerdict(verification_data["verdict"]),
                consumer_state=ConsumerState(verification_data["consumer_state"]),
                reason=verification_data["reason"],
                action_receipt=receipt,
                evidence=evidence,
            )
        return ResolutionRecord(
            resolution_id=row["resolution_id"],
            owner_id=row["owner_id"],
            intent=row["intent"],
            provider_mode=row["provider_mode"],
            state=LifecycleState(row["state"]),
            created_at=_utc(row["created_at"]),
            updated_at=_utc(row["updated_at"]),
            confirmed_at=_utc(row["confirmed_at"]),
            execution_claim=receipt,
            execution_claim_observed_at=_utc(row["execution_claim_observed_at"]),
            independent_evidence=evidence,
            independent_evidence_observed_at=_utc(row["independent_evidence_observed_at"]),
            verification=verification,
            verified_at=_utc(row["verified_at"]),
            state_history=[
                StateTransition(LifecycleState(item["state"]), _parse_time(item["occurred_at"]))
                for item in row["state_history"]
            ],
            version=row["version"],
        )


class UnavailableResolutionRepository:
    def _fail(self) -> NoReturn:
        raise ResolutionStorageUnavailableError(
            "CLOSELOOP_DATABASE_URL or DATABASE_URL is required in serverless environments"
        )

    def create(self, record: ResolutionRecord) -> None:
        self._fail()

    def get_owned(self, resolution_id: str, owner_id: str) -> ResolutionRecord:
        self._fail()

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None:
        self._fail()

    def list_open_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]:
        self._fail()


def create_repository_from_environment() -> ResolutionRepository:
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
