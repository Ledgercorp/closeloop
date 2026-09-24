from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol
from uuid import uuid4

from .confirmation import (
    CONFIRMATION_ACTION,
    CONFIRMATION_CONTRACT_VERSION,
    ConfirmationAttestationError,
    ConfirmationAttestationVerifier,
    ExpectedConfirmation,
    VerifiedConfirmationAttestation,
    confirmation_action_digest,
    confirmation_attestation_verifier_from_environment,
)
from .demo_provider import DemoProvider
from .models import (
    ActionReceipt,
    CancellationEvidence,
    ResourceIdentity,
    ResolutionVerdict,
    VerificationResult,
    demo_resource_identity,
)
from .verifier import (
    is_valid_action_receipt,
    is_valid_cancellation_evidence,
    verify_cancellation,
)


MAX_INTENT_LENGTH = 2000
MAX_RESOLUTION_ID_LENGTH = 64
MAX_VERIFICATION_CHECKS = 4


class LifecycleState(str, Enum):
    REQUESTED = "REQUESTED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    NOT_COMPLETED = "NOT_COMPLETED"
    AWAITING_PROOF = "AWAITING_PROOF"


class ResolutionType(str, Enum):
    CANCELLATION = "CANCELLATION"
    REFUND = "REFUND"
    RETURN = "RETURN"
    WARRANTY_CLAIM = "WARRANTY_CLAIM"
    SERVICE_REQUEST = "SERVICE_REQUEST"
    APPOINTMENT = "APPOINTMENT"


TERMINAL_STATES = frozenset(
    {
        LifecycleState.VERIFIED,
        LifecycleState.NOT_COMPLETED,
    }
)

_ALLOWED_TRANSITIONS = {
    LifecycleState.REQUESTED: frozenset({LifecycleState.AWAITING_CONFIRMATION}),
    LifecycleState.AWAITING_CONFIRMATION: frozenset({LifecycleState.EXECUTING}),
    LifecycleState.EXECUTING: frozenset({LifecycleState.VERIFYING}),
    LifecycleState.VERIFYING: frozenset(
        {*TERMINAL_STATES, LifecycleState.AWAITING_PROOF, LifecycleState.VERIFYING}
    ),
    LifecycleState.AWAITING_PROOF: frozenset({LifecycleState.VERIFYING}),
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
    def cancel_subscription(self, target: ResourceIdentity) -> ActionReceipt: ...

    def read_cancellation_evidence(
        self, target: ResourceIdentity, attempt_id: str
    ) -> CancellationEvidence: ...


ProviderFactory = Callable[[str], CancellationProvider]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
    confirmation_contract_version: str | None = None
    confirmation_attestation: VerifiedConfirmationAttestation | None = None


@dataclass(slots=True)
class VerificationAttempt:
    checked_at: datetime
    evidence: CancellationEvidence
    result: VerificationResult
    attempt_id: str = ""
    check_count: int = 0
    terminal_failure_eligible: bool = False


@dataclass
class ResolutionRecord:
    resolution_id: str
    owner_id: str
    intent: str
    provider_mode: str
    target: ResourceIdentity | None = None
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
    resolution_type: ResolutionType = ResolutionType.CANCELLATION
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    check_count: int = 0
    max_checks: int = MAX_VERIFICATION_CHECKS
    verification_history: list[VerificationAttempt] = field(default_factory=list)
    resolved_at: datetime | None = None
    resolution_reason: str | None = None


class ResolutionRepository(Protocol):
    def create(self, record: ResolutionRecord) -> None: ...

    def get_owned(self, resolution_id: str, owner_id: str) -> ResolutionRecord: ...

    def save_owned(self, record: ResolutionRecord, expected_version: int) -> None: ...

    def list_open_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]: ...
    def list_recent_owned(self, owner_id: str, limit: int) -> list[ResolutionRecord]: ...


class ResolutionService:
    """Runs the lifecycle using durable, owner-scoped optimistic updates.

    The repository is the cross-instance serialization boundary. Only the
    deterministic verifier may produce a terminal verdict.
    """

    def __init__(
        self,
        repository: ResolutionRepository | None = None,
        provider_factory: ProviderFactory = DemoProvider,
        confirmation_verifier: ConfirmationAttestationVerifier | None = None,
    ) -> None:
        if repository is None:
            from .repository import create_repository_from_environment

            repository = create_repository_from_environment()
        self._repository = repository
        self._provider_factory = provider_factory
        self._confirmation_verifier = (
            confirmation_verifier or confirmation_attestation_verifier_from_environment()
        )

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
        if len(normalized_intent) > MAX_INTENT_LENGTH:
            raise ResolutionError(
                f"intent must not exceed {MAX_INTENT_LENGTH} characters"
            )

        now = _utc_now()
        record = ResolutionRecord(
            resolution_id=str(uuid4()),
            owner_id=owner_id,
            intent=normalized_intent,
            provider_mode=provider_mode,
            target=demo_resource_identity(owner_id),
            created_at=now,
            updated_at=now,
            state_history=[
                StateTransition(
                    LifecycleState.REQUESTED,
                    now,
                    confirmation_contract_version=CONFIRMATION_CONTRACT_VERSION,
                )
            ],
        )
        self._transition(record, LifecycleState.AWAITING_CONFIRMATION)
        self._repository.create(record)
        return self._status_view(record)

    def confirm_resolution_action(
        self,
        owner_id: str,
        resolution_id: str,
        confirmed: bool,
        confirmation_attestation: str | None = None,
    ) -> dict[str, object]:
        self._validate_owner(owner_id)
        if confirmed is not True:
            raise ResolutionError("explicit confirmation is required before execution")
        self._validate_resolution_id(resolution_id)

        record = self._repository.get_owned(resolution_id, owner_id)
        if record.state is not LifecycleState.AWAITING_CONFIRMATION:
            raise InvalidTransitionError(
                f"cannot confirm resolution while state is {record.state.value}"
            )
        now = _utc_now()
        digest = self._action_digest(record)
        try:
            verified_confirmation = self._confirmation_verifier.verify(
                confirmation_attestation or "",
                ExpectedConfirmation(
                    principal_id=record.owner_id,
                    resolution_id=record.resolution_id,
                    action=CONFIRMATION_ACTION,
                    action_digest=digest,
                ),
                now=now,
            )
        except ConfirmationAttestationError as exc:
            raise ResolutionError("trusted confirmation attestation is required") from exc
        record.confirmed_at = now
        self._transition(
            record,
            LifecycleState.EXECUTING,
            confirmation_attestation=verified_confirmation,
        )
        self._repository.save_owned(record, expected_version=record.version)

        try:
            provider = self._provider_factory(record.provider_mode)
        except Exception:
            provider = None
        receipt = self._execute(provider, record.target)
        record.execution_claim = receipt
        record.execution_claim_observed_at = _utc_now()
        record.check_count += 1
        self._transition(record, LifecycleState.VERIFYING)
        self._repository.save_owned(record, expected_version=record.version)

        self._record_verification(record, provider, receipt, increment_count=False)
        self._repository.save_owned(record, expected_version=record.version)
        return self._status_view(record)

    def recheck_resolution(
        self,
        owner_id: str,
        resolution_id: str,
        *,
        scheduled_for: datetime | None = None,
        now: datetime | None = None,
        force: bool = False,
    ) -> dict[str, object]:
        """Recheck only the outcome; never repeat the consequential provider action."""
        self._validate_owner(owner_id)
        self._validate_resolution_id(resolution_id)
        record = self._repository.get_owned(resolution_id, owner_id)
        if record.state not in {LifecycleState.AWAITING_PROOF, LifecycleState.VERIFYING}:
            raise InvalidTransitionError("only an unresolved verification can be rechecked")
        current_time = _utc(now or _utc_now())
        terminal_failure_eligible = (
            record.state is LifecycleState.AWAITING_PROOF
            and record.next_check_at is not None
            and record.check_count + 1 >= record.max_checks
            and current_time >= _utc(record.next_check_at)
        )
        if (
            record.state is LifecycleState.VERIFYING
            and current_time < _utc(record.updated_at) + timedelta(minutes=5)
        ):
            raise InvalidTransitionError("verification attempt is already in progress")
        if record.check_count >= record.max_checks:
            raise InvalidTransitionError("verification attempt limit reached")
        if record.state is LifecycleState.AWAITING_PROOF and scheduled_for is not None:
            if record.next_check_at is None or _utc(scheduled_for) != _utc(record.next_check_at):
                raise InvalidTransitionError("scheduled check is stale or already consumed")
            if current_time < _utc(record.next_check_at):
                raise InvalidTransitionError("scheduled check is premature")
        elif (
            record.state is LifecycleState.AWAITING_PROOF
            and not force
            and record.next_check_at is not None
            and current_time < _utc(record.next_check_at)
        ):
            raise InvalidTransitionError("next verification is not due yet")

        # Claim the attempt with a conditional state/version write before any read-back.
        if record.state is LifecycleState.AWAITING_PROOF:
            record.check_count += 1
            record.next_check_at = None
            record.independent_evidence = None
            record.independent_evidence_observed_at = None
            record.verification = None
            record.verified_at = None
            self._transition(record, LifecycleState.VERIFYING, occurred_at=current_time)
            self._repository.save_owned(record, expected_version=record.version)
        else:
            # Recover a verification interrupted by process loss without repeating
            # the action. The conditional version write claims one bounded retry.
            record.check_count += 1
            self._transition(record, LifecycleState.VERIFYING, occurred_at=current_time)
            self._repository.save_owned(record, expected_version=record.version)
        try:
            provider = self._provider_factory(record.provider_mode)
        except Exception:
            provider = None
        receipt = record.execution_claim or ActionReceipt(
            request_id="", provider_reported_success=False, message="original request unavailable"
        )
        self._record_verification(
            record,
            provider,
            receipt,
            checked_at=current_time,
            increment_count=False,
            terminal_failure_eligible=terminal_failure_eligible,
        )
        self._repository.save_owned(record, expected_version=record.version)
        return self._status_view(record)

    def _record_verification(
        self,
        record: ResolutionRecord,
        provider: CancellationProvider | None,
        receipt: ActionReceipt,
        *,
        checked_at: datetime | None = None,
        increment_count: bool = True,
        terminal_failure_eligible: bool = False,
    ) -> None:
        checked_at = _utc(checked_at or _utc_now())
        attempt_id = str(uuid4())
        evidence = self._collect_independent_evidence(provider, record.target, attempt_id)
        result = verify_cancellation(
            receipt,
            evidence,
            terminal_failure=(
                terminal_failure_eligible and record.check_count >= record.max_checks
            ),
            expected_target_digest=record.target.target_digest if record.target else None,
            expected_attempt_id=attempt_id,
        )
        record.independent_evidence = evidence
        record.independent_evidence_observed_at = checked_at
        record.verification = result
        record.verified_at = checked_at
        record.last_checked_at = checked_at
        if increment_count:
            record.check_count += 1
        record.verification_history.append(
            VerificationAttempt(
                checked_at=checked_at,
                evidence=evidence,
                result=result,
                attempt_id=attempt_id,
                check_count=record.check_count,
                terminal_failure_eligible=terminal_failure_eligible,
            )
        )
        if result.verdict is ResolutionVerdict.INCONCLUSIVE:
            record.next_check_at = (
                checked_at + timedelta(minutes=5 * record.check_count)
                if record.check_count < record.max_checks
                else None
            )
            record.resolved_at = None
            record.resolution_reason = result.reason
            next_state = LifecycleState.AWAITING_PROOF
        else:
            record.next_check_at = None
            record.resolved_at = checked_at
            record.resolution_reason = result.reason
            next_state = self._terminal_state_for(result)
        self._transition(record, next_state, occurred_at=checked_at)

    def get_resolution_status(self, owner_id: str, resolution_id: str) -> dict[str, object]:
        self._validate_owner(owner_id)
        self._validate_resolution_id(resolution_id)
        return self._status_view(self._repository.get_owned(resolution_id, owner_id))

    def get_resolution_evidence(self, owner_id: str, resolution_id: str) -> dict[str, object]:
        self._validate_owner(owner_id)
        self._validate_resolution_id(resolution_id)
        return self._evidence_view(self._repository.get_owned(resolution_id, owner_id))

    def list_open_resolutions(self, owner_id: str, limit: int = 50) -> list[dict[str, object]]:
        self._validate_owner(owner_id)
        if limit < 1 or limit > 100:
            raise ResolutionError("limit must be between 1 and 100")
        return [
            self._status_view(record)
            for record in self._repository.list_open_owned(owner_id, limit)
        ]

    def list_recent_resolutions(self, owner_id: str, limit: int = 20) -> list[dict[str, object]]:
        self._validate_owner(owner_id)
        if limit < 1 or limit > 100:
            raise ResolutionError("limit must be between 1 and 100")
        return [
            self._status_view(record)
            for record in self._repository.list_recent_owned(owner_id, limit)
        ]

    @staticmethod
    def _validate_owner(owner_id: str) -> None:
        if not owner_id or not owner_id.strip():
            raise ResolutionError("an authenticated principal is required")

    @staticmethod
    def _validate_resolution_id(resolution_id: str) -> None:
        if not isinstance(resolution_id, str) or not resolution_id.strip():
            raise ResolutionError("resolution_id must be a non-empty string")
        if len(resolution_id) > MAX_RESOLUTION_ID_LENGTH:
            raise ResolutionError(
                f"resolution_id must not exceed {MAX_RESOLUTION_ID_LENGTH} characters"
            )

    @staticmethod
    def _execute(
        provider: CancellationProvider | None, target: ResourceIdentity | None
    ) -> ActionReceipt:
        try:
            receipt = provider.cancel_subscription(target) if provider and target else None
            if not is_valid_action_receipt(receipt):
                raise TypeError("provider returned an invalid action receipt")
            return receipt
        except Exception:
            return ActionReceipt(
                request_id=str(uuid4()),
                provider_reported_success=False,
                message="Execution provider did not return a valid receipt.",
            )

    @staticmethod
    def _collect_independent_evidence(
        provider: CancellationProvider | None,
        target: ResourceIdentity | None,
        attempt_id: str,
    ) -> CancellationEvidence:
        try:
            evidence = (
                provider.read_cancellation_evidence(target, attempt_id)
                if provider and target
                else None
            )
            if not is_valid_cancellation_evidence(evidence):
                raise TypeError("provider returned invalid independent evidence")
            return evidence
        except Exception:
            return CancellationEvidence(
                account_readable=False,
                auto_renew=None,
                effective_end_date=None,
            freshness_seconds=None,
            target_digest=target.target_digest if target else None,
            attempt_id=attempt_id,
            )

    @staticmethod
    def _terminal_state_for(result: VerificationResult) -> LifecycleState:
        return {
            ResolutionVerdict.PASS: LifecycleState.VERIFIED,
            ResolutionVerdict.FAIL: LifecycleState.NOT_COMPLETED,
            ResolutionVerdict.INCONCLUSIVE: LifecycleState.AWAITING_PROOF,
        }[result.verdict]

    @staticmethod
    def _transition(
        record: ResolutionRecord,
        next_state: LifecycleState,
        *,
        confirmation_attestation: VerifiedConfirmationAttestation | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        if record.state not in allowed_previous_states(next_state):
            raise InvalidTransitionError(
                f"transition {record.state.value} -> {next_state.value} is not allowed"
            )
        now = _utc(occurred_at or _utc_now())
        record.state = next_state
        record.updated_at = now
        record.state_history.append(
            StateTransition(
                next_state,
                now,
                confirmation_attestation=confirmation_attestation,
            )
        )

    @staticmethod
    def _action_digest(record: ResolutionRecord) -> str:
        return confirmation_action_digest(
            principal_id=record.owner_id,
            resolution_id=record.resolution_id,
            intent=record.intent,
            provider_mode=record.provider_mode,
            target_digest=record.target.target_digest if record.target else "",
        )

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

        conversation = ResolutionService._conversation_view(record)
        return {
            "resolution_id": record.resolution_id,
            "task": record.intent,
            "action": "cancel_subscription",
            "action_digest": ResolutionService._action_digest(record),
            "intent": record.intent,
            "execution_environment": "demo_simulation",
            "provider_mode": record.provider_mode,
            "lifecycle_state": record.state.value,
            "resolution_type": record.resolution_type.value,
            "is_terminal": record.state in TERMINAL_STATES,
            "last_checked_at": _isoformat(record.last_checked_at),
            "next_check_at": _isoformat(record.next_check_at),
            "check_count": record.check_count,
            "max_checks": record.max_checks,
            "resolved_at": _isoformat(record.resolved_at),
            "confirmation_required": record.state is LifecycleState.AWAITING_CONFIRMATION,
            "consumer_state": consumer_state,
            "verdict": verdict,
            **conversation,
            "explanation": explanation,
            "created_at": _isoformat(record.created_at),
            "updated_at": _isoformat(record.updated_at),
            "confirmed_at": _isoformat(record.confirmed_at),
            "resolution_reason": record.resolution_reason,
        }

    @staticmethod
    def _evidence_view(record: ResolutionRecord) -> dict[str, object]:
        receipt = record.execution_claim
        evidence = record.independent_evidence
        verification = record.verification
        conversation = ResolutionService._conversation_view(record)
        return {
            "resolution_id": record.resolution_id,
            "task": record.intent,
            "action": "cancel_subscription",
            "action_digest": ResolutionService._action_digest(record),
            "execution_environment": "demo_simulation",
            "provider_mode": record.provider_mode,
            "lifecycle_state": record.state.value,
            **conversation,
            "execution_claim": (
                {
                    "evidence_type": "execution_claim",
                    "source": "demo_provider.cancel_subscription",
                    "request_id": receipt.request_id,
                "provider_reported_success": receipt.provider_reported_success,
                "message": receipt.message,
                "observed_at": _isoformat(record.execution_claim_observed_at),
                "target_digest": receipt.target_digest,
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
                "target_digest": evidence.target_digest,
                "attempt_id": evidence.attempt_id,
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
        "verification_history": [
            {
                "checked_at": _isoformat(attempt.checked_at),
                "attempt_id": attempt.attempt_id,
                "check_count": attempt.check_count,
                "terminal_failure_eligible": attempt.terminal_failure_eligible,
                "evidence": {
                        "account_readable": attempt.evidence.account_readable,
                        "auto_renew": attempt.evidence.auto_renew,
                        "effective_end_date": attempt.evidence.effective_end_date,
                    "freshness_seconds": attempt.evidence.freshness_seconds,
                    "target_digest": attempt.evidence.target_digest,
                    "attempt_id": attempt.evidence.attempt_id,
                    },
                    "verdict": attempt.result.verdict.value,
                    "consumer_state": attempt.result.consumer_state.value,
                "reason": attempt.result.reason,
            }
            for attempt in record.verification_history
        ],
        "target_identity": {
            "provider": record.target.provider,
            "account_subject": record.target.account_subject,
            "resource_id": record.target.resource_id,
            "target_digest": record.target.target_digest,
        },
        }

    @staticmethod
    def _conversation_view(record: ResolutionRecord) -> dict[str, object]:
        if record.state in {
            LifecycleState.REQUESTED,
            LifecycleState.AWAITING_CONFIRMATION,
        }:
            execution_status = "not_started"
        elif record.state is LifecycleState.EXECUTING:
            execution_status = "in_progress"
        else:
            execution_status = "completed"

        if record.verification is not None:
            verification_status = record.verification.verdict.value
            consumer_state = record.verification.consumer_state.value
            evidence_summary = record.verification.reason
            recommended_next_step = {
                ResolutionVerdict.PASS: "No further action is required.",
                ResolutionVerdict.FAIL: (
                    "Report that the task was not completed; start a new resolution only if "
                    "the customer asks to retry."
                ),
                ResolutionVerdict.INCONCLUSIVE: (
                    "Report that proof is unavailable and offer to check status or evidence later."
                ),
            }[record.verification.verdict]
        elif record.state is LifecycleState.VERIFYING:
            verification_status = "in_progress"
            consumer_state = None
            evidence_summary = (
                "Execution evidence is recorded; independent verification is still in progress."
            )
            recommended_next_step = "Use get_resolution_status to check for a terminal result."
        elif record.state is LifecycleState.EXECUTING:
            verification_status = "not_started"
            consumer_state = None
            evidence_summary = "Execution is in progress; no independent verdict exists yet."
            recommended_next_step = "Use get_resolution_status before reporting completion."
        else:
            verification_status = "not_started"
            consumer_state = None
            evidence_summary = (
                "No execution or verification evidence exists because confirmation is pending."
            )
            recommended_next_step = (
                "Obtain explicit customer confirmation before calling confirm_resolution_action."
            )

        return {
            "execution_status": execution_status,
            "verification_status": verification_status,
            "consumer_state": consumer_state,
            "evidence_summary": evidence_summary,
            "recommended_next_step": recommended_next_step,
        }
