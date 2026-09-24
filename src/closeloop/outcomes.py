from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Mapping
from uuid import uuid4


class UnsupportedOutcomeRequest(ValueError):
    """The request is outside the bounded executable workflow set."""


class AttentionLevel(StrEnum):
    SILENT = "SILENT"
    INFORMATIONAL = "INFORMATIONAL"
    ACTION_NEEDED = "ACTION_NEEDED"
    URGENT = "URGENT"


class RecoveryState(StrEnum):
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    DECLINED = "DECLINED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


def _time(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


@dataclass(frozen=True)
class OutcomeContract:
    version: str
    resolution_type: str
    target_digest: str
    desired_state: str
    deadline_at: datetime | None
    verification_requirement: str
    prohibited_outcome: str | None
    recovery_policy: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "version": self.version,
            "resolution_type": self.resolution_type,
            "target_digest": self.target_digest,
            "desired_state": self.desired_state,
            "deadline_at": _iso(self.deadline_at),
            "verification_requirement": self.verification_requirement,
            "prohibited_outcome": self.prohibited_outcome,
            "recovery_policy": self.recovery_policy,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> OutcomeContract:
        deadline = _time(value.get("deadline_at"))
        fields = ("version", "resolution_type", "target_digest", "desired_state", "verification_requirement", "recovery_policy")
        if any(not isinstance(value.get(key), str) or not value[key] for key in fields):
            raise ValueError("outcome contract is malformed")
        prohibited = value.get("prohibited_outcome")
        if prohibited is not None and not isinstance(prohibited, str):
            raise ValueError("outcome contract prohibited outcome is malformed")
        return cls(*(str(value[key]) for key in fields[:4]), deadline,
                   str(value["verification_requirement"]), prohibited,
                   str(value["recovery_policy"]))


def interpret_cancellation_request(
    intent: str, *, target_digest: str, requested_at: datetime
) -> OutcomeContract:
    """Support only explicit subscription-cancellation language and a small deadline vocabulary."""
    normalized = " ".join(intent.lower().split())
    if not re.search(r"\bcancel(?:l?ation|ling)?\b", normalized) or not re.search(
        r"\b(subscription|streambox)\b", normalized
    ):
        raise UnsupportedOutcomeRequest("I can currently keep an eye on subscription cancellations. Please clarify that request.")

    deadline: datetime | None = None
    friday = re.search(r"\b(before|by)\s+(this|next)?\s*friday\b", normalized)
    if friday:
        local = requested_at.astimezone(timezone.utc)
        days = (4 - local.weekday()) % 7 or 7
        if friday.group(2) == "next":
            days += 7
        deadline = datetime.combine((local + timedelta(days=days)).date(), time.min, timezone.utc)
    elif re.search(r"\b(before|by)\s+tomorrow\b", normalized):
        local = requested_at.astimezone(timezone.utc)
        deadline = datetime.combine((local + timedelta(days=1)).date(), time.min, timezone.utc)

    return OutcomeContract(
        version="closeloop.outcome-contract/v1",
        resolution_type="CANCELLATION",
        target_digest=target_digest,
        desired_state="subscription.auto_renew == false",
        deadline_at=deadline,
        verification_requirement="fresh_independent_account_readback",
        prohibited_outcome=("renewal_charge_after_deadline" if "charg" in normalized or "renew" in normalized else None),
        recovery_policy="user_confirmation_required",
    )


@dataclass(frozen=True)
class AttentionEvent:
    event_id: str
    owner_id: str
    resolution_id: str
    target_digest: str
    severity: AttentionLevel
    reason: str
    message: str
    dedupe_key: str
    created_at: datetime

    def to_mapping(self) -> dict[str, object]:
        return {"event_id": self.event_id, "owner_id": self.owner_id, "resolution_id": self.resolution_id,
                "target_digest": self.target_digest, "severity": self.severity.value, "reason": self.reason,
                "message": self.message, "dedupe_key": self.dedupe_key, "created_at": _iso(self.created_at)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> AttentionEvent:
        try:
            return cls(str(value["event_id"]), str(value["owner_id"]), str(value["resolution_id"]),
                       str(value["target_digest"]), AttentionLevel(str(value["severity"])), str(value["reason"]),
                       str(value["message"]), str(value["dedupe_key"]), _time(value["created_at"]))  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("attention event is malformed") from exc


def attention_candidate(
    *, owner_id: str, resolution_id: str, target_digest: str, contract: OutcomeContract,
    lifecycle_state: str, evidence: Mapping[str, object] | None,
    has_violation: bool, now: datetime,
) -> AttentionEvent | None:
    """Produce deterministic attention only from material state or fresh independent evidence."""
    if has_violation:
        level, reason, message = AttentionLevel.URGENT, "outcome_violation", "A renewal charge appeared after the cancellation deadline."
    elif lifecycle_state == "VERIFIED":
        level, reason, message = AttentionLevel.INFORMATIONAL, "verified", "The cancellation is verified complete."
    elif lifecycle_state == "NOT_COMPLETED":
        level, reason, message = AttentionLevel.ACTION_NEEDED, "not_completed", "The cancellation was not completed."
    elif contract.deadline_at is not None and now >= contract.deadline_at:
        level, reason, message = AttentionLevel.URGENT, "deadline_passed", "The cancellation deadline passed and the result is still open."
    elif (
        contract.deadline_at is not None
        and contract.deadline_at - now <= timedelta(hours=6)
        and evidence is not None
        and evidence.get("account_readable") is True
        and evidence.get("auto_renew") is True
        and isinstance(evidence.get("freshness_seconds"), int)
        and int(evidence["freshness_seconds"]) <= 300
    ):
        level, reason, message = AttentionLevel.ACTION_NEEDED, "deadline_approaching", "The subscription still renews soon."
    else:
        return None
    key = f"{level.value}:{reason}"
    return AttentionEvent(str(uuid4()), owner_id, resolution_id, target_digest, level, reason, message, key, now)


@dataclass
class RecoveryAction:
    recovery_id: str
    owner_id: str
    resolution_id: str
    target_digest: str
    action_type: str
    action_digest: str
    reason: str
    state: RecoveryState
    created_at: datetime
    expires_at: datetime
    evidence_attempt_id: str | None = None
    confirmation_attestation_id: str | None = None
    execution_receipt: dict[str, object] | None = None
    state_history: list[dict[str, str]] = field(default_factory=list)

    def to_mapping(self) -> dict[str, object]:
        return {"recovery_id": self.recovery_id, "owner_id": self.owner_id, "resolution_id": self.resolution_id,
                "target_digest": self.target_digest, "action_type": self.action_type, "action_digest": self.action_digest,
                "reason": self.reason, "state": self.state.value, "created_at": _iso(self.created_at),
                "expires_at": _iso(self.expires_at), "evidence_attempt_id": self.evidence_attempt_id,
                "confirmation_attestation_id": self.confirmation_attestation_id,
                "execution_receipt": self.execution_receipt, "state_history": self.state_history}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RecoveryAction:
        try:
            history = value["state_history"]
            if not isinstance(history, list) or any(not isinstance(x, dict) for x in history):
                raise ValueError
            receipt = value.get("execution_receipt")
            if receipt is not None and not isinstance(receipt, dict):
                raise ValueError
            return cls(str(value["recovery_id"]), str(value["owner_id"]), str(value["resolution_id"]),
                       str(value["target_digest"]), str(value["action_type"]), str(value["action_digest"]),
                       str(value["reason"]), RecoveryState(str(value["state"])), _time(value["created_at"]),
                       _time(value["expires_at"]), value.get("evidence_attempt_id"),
                       value.get("confirmation_attestation_id"), receipt, history)  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("recovery action is malformed") from exc


def recovery_action_digest(*, recovery_id: str, owner_id: str, resolution_id: str,
                           target_digest: str, action_type: str, reason: str,
                           expires_at: datetime) -> str:
    body = {"version": "closeloop.recovery-action/v1", "recovery_id": recovery_id, "owner_id": owner_id,
            "resolution_id": resolution_id, "target_digest": target_digest, "action_type": action_type,
            "reason": reason, "expires_at": _iso(expires_at)}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class OutcomeViolation:
    violation_id: str
    owner_id: str
    resolution_id: str
    target_digest: str
    event_type: str
    amount_cents: int
    currency: str
    source: str
    evidence_id: str
    observed_at: datetime

    def to_mapping(self) -> dict[str, object]:
        return {"violation_id": self.violation_id, "owner_id": self.owner_id, "resolution_id": self.resolution_id,
                "target_digest": self.target_digest, "event_type": self.event_type, "amount_cents": self.amount_cents,
                "currency": self.currency, "source": self.source, "evidence_id": self.evidence_id,
                "observed_at": _iso(self.observed_at)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> OutcomeViolation:
        try:
            result = cls(str(value["violation_id"]), str(value["owner_id"]), str(value["resolution_id"]),
                         str(value["target_digest"]), str(value["event_type"]), int(value["amount_cents"]),
                         str(value["currency"]), str(value["source"]), str(value["evidence_id"]),
                         _time(value["observed_at"]))  # type: ignore[arg-type]
            if result.event_type != "renewal_charge" or result.amount_cents <= 0 or len(result.currency) != 3:
                raise ValueError
            return result
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("outcome violation is malformed") from exc
