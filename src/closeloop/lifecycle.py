from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Protocol
from uuid import uuid4

from .demo_provider import DemoProvider
from .models import ActionReceipt, CancellationEvidence, ResolutionVerdict, VerificationResult
from .verifier import verify_cancellation


class LifecycleState(str, Enum):
    REQUESTED = "REQUESTED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    NOT_COMPLETED = "NOT_COMPLETED"
    AWAITING_PROOF = "AWAITING_PROOF"


TERMINAL_STATES = frozenset(
    {
        LifecycleState.VERIFIED,
        LifecycleState.NOT_COMPLETED,
        LifecycleState.AWAITING_PROOF,
    }
)

_ALLOWED_TRANSITIONS = {
    LifecycleState.REQUESTED: frozenset({LifecycleState.AWAITING_CONFIRMATION}),
    LifecycleState.AWAITING_CONFIRMATION: frozenset({LifecycleState.EXECUTING}),
    LifecycleState.EXECUTING: frozenset({LifecycleState.VERIFYING}),
    LifecycleState.VERIFYING: TERMINAL_STATES,
}


def allowed_previous_states(next_state: LifecycleState) -> frozenset[LifecycleState]:
    return frozenset(
        state for state, allowed in _ALLOWED_TRANSITIONS.items() if next_state in allowed
    )


class ResolutionError(ValueError):
    """Base error for a rejected resolution operation."""


class ResolutionNotFoundError(ResolutionError):
    """Raised for missing and unauthorized resolutions without revealing which."""


class InvalidTransitionError(ResolutionError):
    """Raised when a lifecycle transition is not explicitly allowed."""


class ConcurrentResolutionUpdateError(ResolutionError):
    """Raised when another instance changed a resolution first."""


class TerminalOutcomeImmutableError(ResolutionError):
    """Raised when an update attempts to change an existing terminal outcome."""


class ResolutionStorageUnavailableError(RuntimeError):
    """Raised when durable storage is not configured or reachable."""


class CancellationProvider(Protocol):
    def cancel_subscription(self) -> ActionReceipt: ...

    def read_cancellation_evidence(self) -> CancellationEvidence: ...


ProviderFactory = Callable[[str], CancellationProvider]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class StateTransition:
    state: LifecycleState
    occurred_at: datetime


@dataclass
class ResolutionRecord:
    resolution_id: str
    owner_id: str
    intent: str
    provider_mode: str
    state: LifecycleState = LifecycleState.REQUESTED
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    confirmed_at: datetime | None = None
    execution_claim: ActionReceipt | None = None
    execution_claim_observed_at: datetime | None = None
    independent_evidence: CancellationEvidence | None = None
    independent_evidence_observed_at: datetime | None = None
    verification: VerificationResult | None = None
    verified_at: datetime | None = None
    state_history: list[StateTransition] = field(default_factory=list)
    version: int = 0


class ResolutionRepository(Protocol):
    def create(self, record: ResolutionRecord) -> None: ...

    def get_owned(self, resolution_id: str, owner_id: str) -> ResolutionRecord: ...

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None: ...

    def list_open_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]: ...


class ResolutionService:
    """Runs the lifecycle using durable, owner-scoped optimistic updates.

    The repository is the cross-instance serialization boundary. Only the
    deterministic verifier may produce a terminal verdict.
    """

    def __init__(
        self,
        repository: ResolutionRepository | None = None,
        provider_factory: ProviderFactory = DemoProvider,
    ) -> None:
        if repository is None:
            from .repository import create_repository_from_environment

            repository = create_repository_from_environment()
        self._repository = repository
        self._provider_factory = provider_factory

    def start_resolution(
        self,
        owner_id: str,
        intent: str,
        provider_mode: str = "healthy",
    ) -> dict[str, object]:
        self._validate_owner(owner_id)
        normalized_intent = intent.strip()
        if not normalized_intent:
            raise ResolutionError("intent must not be empty")

        now = _utc_now()
        record = ResolutionRecord(
            resolution_id=str(uuid4()),
            owner_id=owner_id,
            intent=normalized_intent,
            provider_mode=provider_mode,
            created_at=now,
            updated_at=now,
            state_history=[StateTransition(LifecycleState.REQUESTED, now)],
        )
        self._transition(record, LifecycleState.AWAITING_CONFIRMATION)
        self._repository.create(record)
        return self._status_view(record)

    def confirm_resolution_action(
        self,
        owner_id: str,
        resolution_id: str,
        confirmed: bool,
    ) -> dict[str, object]:
        self._validate_owner(owner_id)
        if confirmed is not True:
            raise ResolutionError("explicit confirmation is required before execution")

        record = self._repository.get_owned(resolution_id, owner_id)
        if record.state is not LifecycleState.AWAITING_CONFIRMATION:
            raise InvalidTransitionError(
                f"cannot confirm resolution while state is {record.state.value}"
            )
        record.confirmed_at = _utc_now()
        self._transition(record, LifecycleState.EXECUTING)
        self._repository.save_owned(record, expected_version=record.version)

        provider = self._provider_factory(record.provider_mode)
        receipt = self._execute(provider)
        record.execution_claim = receipt
        record.execution_claim_observed_at = _utc_now()
        self._transition(record, LifecycleState.VERIFYING)
        self._repository.save_owned(record, expected_version=record.version)

        evidence = self._collect_independent_evidence(provider)
        result = verify_cancellation(receipt, evidence)
        record.independent_evidence = evidence
        record.independent_evidence_observed_at = _utc_now()
        record.verification = result
        record.verified_at = _utc_now()
        self._transition(record, self._terminal_state_for(result))
        self._repository.save_owned(record, expected_version=record.version)
        return self._status_view(record)

    def get_resolution_status(self, owner_id: str, resolution_id: str) -> dict[str, object]:
        self._validate_owner(owner_id)
        return self._status_view(self._repository.get_owned(resolution_id, owner_id))

    def get_resolution_evidence(self, owner_id: str, resolution_id: str) -> dict[str, object]:
        self._validate_owner(owner_id)
        return self._evidence_view(self._repository.get_owned(resolution_id, owner_id))

    def list_open_resolutions(self, owner_id: str, limit: int = 50) -> list[dict[str, object]]:
        self._validate_owner(owner_id)
        if limit < 1 or limit > 100:
            raise ResolutionError("limit must be between 1 and 100")
        return [
            self._status_view(record)
            for record in self._repository.list_open_owned(owner_id, limit)
        ]

    @staticmethod
    def _validate_owner(owner_id: str) -> None:
        if not owner_id or not owner_id.strip():
            raise ResolutionError("an authenticated principal is required")

    @staticmethod
    def _execute(provider: CancellationProvider) -> ActionReceipt:
        try:
            return provider.cancel_subscription()
        except Exception:
            return ActionReceipt(
                request_id=str(uuid4()),
                provider_reported_success=False,
                message="Execution provider did not return a receipt.",
            )

    @staticmethod
    def _collect_independent_evidence(provider: CancellationProvider) -> CancellationEvidence:
        try:
            return provider.read_cancellation_evidence()
        except Exception:
            return CancellationEvidence(
                account_readable=False,
                auto_renew=None,
                effective_end_date=None,
                freshness_seconds=None,
            )

    @staticmethod
    def _terminal_state_for(result: VerificationResult) -> LifecycleState:
        return {
            ResolutionVerdict.PASS: LifecycleState.VERIFIED,
            ResolutionVerdict.FAIL: LifecycleState.NOT_COMPLETED,
            ResolutionVerdict.INCONCLUSIVE: LifecycleState.AWAITING_PROOF,
        }[result.verdict]

    @staticmethod
    def _transition(record: ResolutionRecord, next_state: LifecycleState) -> None:
        if record.state not in allowed_previous_states(next_state):
            raise InvalidTransitionError(
                f"transition {record.state.value} -> {next_state.value} is not allowed"
            )
        now = _utc_now()
        record.state = next_state
        record.updated_at = now
        record.state_history.append(StateTransition(next_state, now))

    @staticmethod
    def _status_view(record: ResolutionRecord) -> dict[str, object]:
        verification = record.verification
        if verification:
            explanation = verification.reason
            consumer_state = verification.consumer_state.value
            verdict = verification.verdict.value
        else:
            explanation = (
                "Waiting for explicit confirmation before any consequential action."
                if record.state is LifecycleState.AWAITING_CONFIRMATION
                else "Resolution is in progress."
            )
            consumer_state = None
            verdict = None

        return {
            "resolution_id": record.resolution_id,
            "action": "cancel_subscription",
            "intent": record.intent,
            "execution_environment": "demo_simulation",
            "provider_mode": record.provider_mode,
            "lifecycle_state": record.state.value,
            "is_terminal": record.state in TERMINAL_STATES,
            "confirmation_required": record.state is LifecycleState.AWAITING_CONFIRMATION,
            "consumer_state": consumer_state,
            "verdict": verdict,
            "explanation": explanation,
            "created_at": _isoformat(record.created_at),
            "updated_at": _isoformat(record.updated_at),
            "confirmed_at": _isoformat(record.confirmed_at),
        }

    @staticmethod
    def _evidence_view(record: ResolutionRecord) -> dict[str, object]:
        receipt = record.execution_claim
        evidence = record.independent_evidence
        verification = record.verification
        return {
            "resolution_id": record.resolution_id,
            "action": "cancel_subscription",
            "execution_environment": "demo_simulation",
            "provider_mode": record.provider_mode,
            "lifecycle_state": record.state.value,
            "execution_claim": (
                {
                    "evidence_type": "execution_claim",
                    "source": "demo_provider.cancel_subscription",
                    "request_id": receipt.request_id,
                    "provider_reported_success": receipt.provider_reported_success,
                    "message": receipt.message,
                    "observed_at": _isoformat(record.execution_claim_observed_at),
                }
                if receipt
                else None
            ),
            "independent_read_back": (
                {
                    "evidence_type": "independent_read_back",
                    "source": "demo_provider.read_cancellation_evidence",
                    "account_readable": evidence.account_readable,
                    "auto_renew": evidence.auto_renew,
                    "effective_end_date": evidence.effective_end_date,
                    "freshness_seconds": evidence.freshness_seconds,
                    "observed_at": _isoformat(record.independent_evidence_observed_at),
                }
                if evidence
                else None
            ),
            "verification": (
                {
                    "verifier": "closeloop.verify_cancellation/v1",
                    "verdict": verification.verdict.value,
                    "consumer_state": verification.consumer_state.value,
                    "reason": verification.reason,
                    "evaluated_at": _isoformat(record.verified_at),
                }
                if verification
                else None
            ),
            "state_history": [
                {
                    "state": transition.state.value,
                    "occurred_at": _isoformat(transition.occurred_at),
                }
                for transition in record.state_history
            ],
        }
