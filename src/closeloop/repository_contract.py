from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .confirmation import (
    CONFIRMATION_CONTRACT_VERSION,
    MAX_ATTESTATION_ID_LENGTH,
    MAX_ATTESTATION_LIFETIME_SECONDS,
    MAX_CONFIRMATION_AGE_SECONDS,
    VerifiedConfirmationAttestation,
    confirmation_action_digest,
)
from .lifecycle import (
    TERMINAL_STATES,
    InvalidTransitionError,
    LifecycleState,
    ResolutionRecord,
    ResolutionStorageUnavailableError,
    StateTransition,
    allowed_previous_states,
)
from .models import (
    ActionReceipt,
    CancellationEvidence,
    ConsumerState,
    ResolutionVerdict,
    VerificationResult,
)
from .verifier import verify_cancellation


_VERDICT_STATES = {
    ResolutionVerdict.PASS: (LifecycleState.VERIFIED, ConsumerState.VERIFIED),
    ResolutionVerdict.FAIL: (LifecycleState.NOT_COMPLETED, ConsumerState.NOT_COMPLETED),
    ResolutionVerdict.INCONCLUSIVE: (
        LifecycleState.AWAITING_PROOF,
        ConsumerState.AWAITING_PROOF,
    ),
}


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    normalized = utc(value)
    assert normalized is not None
    return normalized.isoformat().replace("+00:00", "Z")


def validate_new_record(record: ResolutionRecord) -> None:
    if record.state is not LifecycleState.AWAITING_CONFIRMATION or record.version != 0:
        raise InvalidTransitionError(
            "new resolution must begin in AWAITING_CONFIRMATION at version zero"
        )
    if [item.state for item in record.state_history] != [
        LifecycleState.REQUESTED,
        LifecycleState.AWAITING_CONFIRMATION,
    ]:
        raise InvalidTransitionError("new resolution has invalid state history")
    validate_target_record(record)


def validate_target_record(record: ResolutionRecord) -> None:
    if not record.resolution_id.strip() or not record.owner_id.strip():
        raise InvalidTransitionError("resolution requires an authenticated owner and identifier")
    if not record.intent.strip() or not record.provider_mode.strip():
        raise InvalidTransitionError("resolution intent and provider mode are required")
    if record.version < 0:
        raise InvalidTransitionError("resolution version cannot be negative")
    if not record.state_history or record.state_history[-1].state is not record.state:
        raise InvalidTransitionError("state history does not match current state")
    if record.state_history[0].state is not LifecycleState.REQUESTED:
        raise InvalidTransitionError("state history must begin with REQUESTED")
    if (
        record.state_history[0].confirmation_contract_version
        != CONFIRMATION_CONTRACT_VERSION
    ):
        raise InvalidTransitionError("resolution confirmation contract is unavailable")
    if any(
        item.confirmation_contract_version is not None
        for item in record.state_history[1:]
    ):
        raise InvalidTransitionError("confirmation contract version is misplaced")
    for previous, current in zip(record.state_history, record.state_history[1:]):
        if previous.state not in allowed_previous_states(current.state):
            raise InvalidTransitionError("state history contains an invalid transition")
        if utc(previous.occurred_at) > utc(current.occurred_at):
            raise InvalidTransitionError("state history timestamps must be monotonic")
    created_at = utc(record.created_at)
    updated_at = utc(record.updated_at)
    first_transition_at = utc(record.state_history[0].occurred_at)
    last_transition_at = utc(record.state_history[-1].occurred_at)
    if not (created_at <= first_transition_at <= last_transition_at <= updated_at):
        raise InvalidTransitionError("record timestamps do not match state history")

    if record.state is LifecycleState.AWAITING_CONFIRMATION:
        if any(item.confirmation_attestation for item in record.state_history):
            raise InvalidTransitionError(
                "unconfirmed resolution cannot contain confirmation attestation"
            )
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
    transition_times = {
        transition.state: utc(transition.occurred_at)
        for transition in record.state_history
    }
    confirmed_at = utc(record.confirmed_at)
    if not (
        transition_times[LifecycleState.AWAITING_CONFIRMATION]
        <= confirmed_at
        <= transition_times[LifecycleState.EXECUTING]
    ):
        raise InvalidTransitionError("confirmation timestamp is out of lifecycle order")
    attestation_transitions = [
        transition
        for transition in record.state_history
        if transition.confirmation_attestation is not None
    ]
    if (
        len(attestation_transitions) != 1
        or attestation_transitions[0].state is not LifecycleState.EXECUTING
    ):
        raise InvalidTransitionError(
            "execution requires one canonical confirmation attestation"
        )
    attestation = attestation_transitions[0].confirmation_attestation
    assert attestation is not None
    if (
        attestation.contract_version != CONFIRMATION_CONTRACT_VERSION
        or not attestation.issuer.strip()
        or len(attestation.issuer) > 512
        or not attestation.attestation_id.strip()
        or len(attestation.attestation_id) > MAX_ATTESTATION_ID_LENGTH
        or len(attestation.action_digest) != 64
        or len(attestation.token_sha256) != 64
        or any(character not in "0123456789abcdef" for character in attestation.action_digest)
        or any(character not in "0123456789abcdef" for character in attestation.token_sha256)
    ):
        raise InvalidTransitionError("confirmation attestation metadata is invalid")
    expected_digest = confirmation_action_digest(
        principal_id=record.owner_id,
        resolution_id=record.resolution_id,
        intent=record.intent,
        provider_mode=record.provider_mode,
    )
    if attestation.action_digest != expected_digest:
        raise InvalidTransitionError("confirmation action digest does not match resolution")
    issued_at = utc(attestation.issued_at)
    expires_at = utc(attestation.expires_at)
    if not (issued_at <= confirmed_at < expires_at):
        raise InvalidTransitionError("confirmation attestation timing is invalid")
    if (
        (expires_at - issued_at).total_seconds()
        > MAX_ATTESTATION_LIFETIME_SECONDS
        or (confirmed_at - issued_at).total_seconds() > MAX_CONFIRMATION_AGE_SECONDS
    ):
        raise InvalidTransitionError("confirmation attestation freshness is invalid")
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
    execution_observed_at = utc(record.execution_claim_observed_at)
    if not (
        transition_times[LifecycleState.EXECUTING]
        <= execution_observed_at
        <= transition_times[LifecycleState.VERIFYING]
    ):
        raise InvalidTransitionError("execution timestamp is out of lifecycle order")
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
        evidence_observed_at = utc(record.independent_evidence_observed_at)
        verified_at = utc(record.verified_at)
        if not (
            transition_times[LifecycleState.VERIFYING]
            <= evidence_observed_at
            <= verified_at
            <= last_transition_at
        ):
            raise InvalidTransitionError("verification timestamps are out of lifecycle order")
        expected_state, expected_consumer_state = _VERDICT_STATES[record.verification.verdict]
        if record.state is not expected_state:
            raise InvalidTransitionError("terminal state does not match verifier evidence")
        if record.verification.consumer_state is not expected_consumer_state:
            raise InvalidTransitionError("consumer state does not match verifier verdict")
        if (
            record.execution_claim != record.verification.action_receipt
            or record.independent_evidence != record.verification.evidence
        ):
            raise InvalidTransitionError("terminal verifier inputs do not match stored evidence")
        computed = verify_cancellation(record.execution_claim, record.independent_evidence)
        if record.verification != computed:
            raise InvalidTransitionError(
                "stored verifier result does not match deterministic evaluation"
            )
        return
    raise InvalidTransitionError(f"unsupported persisted state: {record.state.value}")


def record_to_mapping(
    record: ResolutionRecord, *, serialize_datetimes: bool = False
) -> dict[str, object]:
    def time_value(value: datetime | None) -> datetime | str | None:
        if value is None:
            return None
        return iso(value) if serialize_datetimes else utc(value)

    return {
        "resolution_id": record.resolution_id,
        "owner_id": record.owner_id,
        "intent": record.intent,
        "provider_mode": record.provider_mode,
        "state": record.state.value,
        "created_at": time_value(record.created_at),
        "updated_at": time_value(record.updated_at),
        "confirmed_at": time_value(record.confirmed_at),
        "execution_claim": (
            {
                "request_id": record.execution_claim.request_id,
                "provider_reported_success": record.execution_claim.provider_reported_success,
                "message": record.execution_claim.message,
            }
            if record.execution_claim
            else None
        ),
        "execution_claim_observed_at": time_value(record.execution_claim_observed_at),
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
        "independent_evidence_observed_at": time_value(
            record.independent_evidence_observed_at
        ),
        "verification": (
            {
                "verdict": record.verification.verdict.value,
                "consumer_state": record.verification.consumer_state.value,
                "reason": record.verification.reason,
            }
            if record.verification
            else None
        ),
        "verified_at": time_value(record.verified_at),
        "state_history": [_transition_to_mapping(item) for item in record.state_history],
        "version": record.version,
    }


def record_from_mapping(mapping: Mapping[str, Any]) -> ResolutionRecord:
    try:
        receipt_data = _optional_mapping(mapping.get("execution_claim"), "execution_claim")
        evidence_data = _optional_mapping(
            mapping.get("independent_evidence"), "independent_evidence"
        )
        verification_data = _optional_mapping(mapping.get("verification"), "verification")

        receipt = None
        if receipt_data is not None:
            receipt = ActionReceipt(
                request_id=_required_str(receipt_data, "request_id"),
                provider_reported_success=_required_bool(
                    receipt_data, "provider_reported_success"
                ),
                message=_required_str(receipt_data, "message", allow_empty=True),
            )
        evidence = None
        if evidence_data is not None:
            evidence = CancellationEvidence(
                account_readable=_required_bool(evidence_data, "account_readable"),
                auto_renew=_optional_bool(evidence_data.get("auto_renew"), "auto_renew"),
                effective_end_date=_optional_str(
                    evidence_data.get("effective_end_date"), "effective_end_date"
                ),
                freshness_seconds=_optional_int(
                    evidence_data.get("freshness_seconds"), "freshness_seconds"
                ),
            )
        verification = None
        if verification_data is not None:
            if receipt is None or evidence is None:
                raise ValueError("stored verifier evidence is incomplete")
            verification = VerificationResult(
                verdict=ResolutionVerdict(_required_str(verification_data, "verdict")),
                consumer_state=ConsumerState(
                    _required_str(verification_data, "consumer_state")
                ),
                reason=_required_str(verification_data, "reason", allow_empty=True),
                action_receipt=receipt,
                evidence=evidence,
            )

        history_data = mapping["state_history"]
        if not isinstance(history_data, list):
            raise TypeError("state_history must be a list")
        history = []
        for item in history_data:
            item_mapping = _required_mapping(item, "state_history item")
            attestation_data = _optional_mapping(
                item_mapping.get("confirmation_attestation"),
                "confirmation_attestation",
            )
            attestation = None
            if attestation_data is not None:
                attestation = VerifiedConfirmationAttestation(
                    contract_version=_required_str(
                        attestation_data, "contract_version"
                    ),
                    issuer=_required_str(attestation_data, "issuer"),
                    attestation_id=_required_str(attestation_data, "attestation_id"),
                    issued_at=_required_time(attestation_data.get("issued_at"), "issued_at"),
                    expires_at=_required_time(
                        attestation_data.get("expires_at"), "expires_at"
                    ),
                    action_digest=_required_str(attestation_data, "action_digest"),
                    token_sha256=_required_str(attestation_data, "token_sha256"),
                )
            history.append(
                StateTransition(
                    LifecycleState(_required_str(item_mapping, "state")),
                    _required_time(item_mapping.get("occurred_at"), "occurred_at"),
                    confirmation_contract_version=_optional_str(
                        item_mapping.get("confirmation_contract_version"),
                        "confirmation_contract_version",
                    ),
                    confirmation_attestation=attestation,
                )
            )

        version = mapping["version"]
        if isinstance(version, bool) or int(version) != version:
            raise TypeError("version must be an integer")
        record = ResolutionRecord(
            resolution_id=_required_str(mapping, "resolution_id"),
            owner_id=_required_str(mapping, "owner_id"),
            intent=_required_str(mapping, "intent"),
            provider_mode=_required_str(mapping, "provider_mode"),
            state=LifecycleState(_required_str(mapping, "state")),
            created_at=_required_time(mapping.get("created_at"), "created_at"),
            updated_at=_required_time(mapping.get("updated_at"), "updated_at"),
            confirmed_at=_optional_time(mapping.get("confirmed_at"), "confirmed_at"),
            execution_claim=receipt,
            execution_claim_observed_at=_optional_time(
                mapping.get("execution_claim_observed_at"),
                "execution_claim_observed_at",
            ),
            independent_evidence=evidence,
            independent_evidence_observed_at=_optional_time(
                mapping.get("independent_evidence_observed_at"),
                "independent_evidence_observed_at",
            ),
            verification=verification,
            verified_at=_optional_time(mapping.get("verified_at"), "verified_at"),
            state_history=history,
            version=int(version),
        )
        validate_target_record(record)
        return record
    except ResolutionStorageUnavailableError:
        raise
    except Exception as exc:
        raise ResolutionStorageUnavailableError(
            "stored resolution record is invalid"
        ) from exc


def _transition_to_mapping(item: StateTransition) -> dict[str, object]:
    result: dict[str, object] = {
        "state": item.state.value,
        "occurred_at": iso(item.occurred_at),
    }
    if item.confirmation_contract_version is not None:
        result["confirmation_contract_version"] = item.confirmation_contract_version
    if item.confirmation_attestation is not None:
        attestation = item.confirmation_attestation
        result["confirmation_attestation"] = {
            "contract_version": attestation.contract_version,
            "issuer": attestation.issuer,
            "attestation_id": attestation.attestation_id,
            "issued_at": iso(attestation.issued_at),
            "expires_at": iso(attestation.expires_at),
            "action_digest": attestation.action_digest,
            "token_sha256": attestation.token_sha256,
        }
    return result


def expected_previous_history(record: ResolutionRecord) -> list[dict[str, object]]:
    """Return the exact persisted history required before this transition."""

    if len(record.state_history) < 2:
        raise InvalidTransitionError("resolution has no predecessor history")
    return [_transition_to_mapping(item) for item in record.state_history[:-1]]


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    return value


def _optional_mapping(value: object, field: str) -> Mapping[str, Any] | None:
    return None if value is None else _required_mapping(value, field)


def _required_str(
    mapping: Mapping[str, Any], field: str, *, allow_empty: bool = False
) -> str:
    value = mapping[field]
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise TypeError(f"{field} must be a non-empty string")
    return value


def _optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string or null")
    return value


def _required_bool(mapping: Mapping[str, Any], field: str) -> bool:
    value = mapping[field]
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a boolean")
    return value


def _optional_bool(value: object, field: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{field} must be a boolean or null")
    return value


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or int(value) != value:
        raise TypeError(f"{field} must be an integer or null")
    return int(value)


def _required_time(value: object, field: str) -> datetime:
    parsed = _optional_time(value, field)
    if parsed is None:
        raise TypeError(f"{field} must be a timestamp")
    return parsed


def _optional_time(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return utc(value)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    raise TypeError(f"{field} must be a timestamp or null")
