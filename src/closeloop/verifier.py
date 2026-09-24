from datetime import date, datetime, timedelta
import re

from .models import (
    ActionReceipt,
    CancellationEvidence,
    ConsumerState,
    ResolutionVerdict,
    VerificationResult,
)
from .outcomes import OutcomeViolation


MAX_EVIDENCE_AGE_SECONDS = 30


def is_valid_action_receipt(receipt: object) -> bool:
    return (
        isinstance(receipt, ActionReceipt)
        and isinstance(receipt.request_id, str)
        and bool(receipt.request_id.strip())
        and type(receipt.provider_reported_success) is bool
        and isinstance(receipt.message, str)
        and (
            receipt.target_digest is None
            or (
                isinstance(receipt.target_digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", receipt.target_digest) is not None
            )
        )
    )


def is_valid_cancellation_evidence(evidence: object) -> bool:
    if not isinstance(evidence, CancellationEvidence):
        return False
    if type(evidence.account_readable) is not bool:
        return False
    if evidence.auto_renew is not None and type(evidence.auto_renew) is not bool:
        return False
    freshness = evidence.freshness_seconds
    if freshness is not None and (type(freshness) is not int or freshness < 0):
        return False
    if evidence.target_digest is not None and (
        not isinstance(evidence.target_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", evidence.target_digest) is None
    ):
        return False
    if evidence.attempt_id is not None and (
        not isinstance(evidence.attempt_id, str) or not evidence.attempt_id.strip()
    ):
        return False
    effective_end_date = evidence.effective_end_date
    if effective_end_date is not None:
        if not isinstance(effective_end_date, str) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", effective_end_date
        ) is None:
            return False
        try:
            date.fromisoformat(effective_end_date)
        except ValueError:
            return False
    return True


def verify_cancellation(
    receipt: ActionReceipt,
    evidence: CancellationEvidence,
    *,
    terminal_failure: bool = False,
    expected_target_digest: str | None = None,
    expected_attempt_id: str | None = None,
    outcome_violation: OutcomeViolation | None = None,
    expected_owner_id: str | None = None,
    expected_resolution_id: str | None = None,
    outcome_deadline_at: datetime | None = None,
    verification_time: datetime | None = None,
) -> VerificationResult:
    """Deterministically verify whether subscription cancellation is proven.

    Important: provider-reported success is never sufficient for PASS.
    """

    if outcome_violation is not None:
        valid_violation = (
            outcome_violation.event_type == "renewal_charge"
            and outcome_violation.amount_cents > 0
            and outcome_violation.currency in {"USD", "CAD", "GBP", "EUR"}
            and outcome_violation.source in {"demo_billing_readback", "independent_billing_readback"}
            and bool(outcome_violation.evidence_id)
            and expected_owner_id is not None
            and outcome_violation.owner_id == expected_owner_id
            and expected_resolution_id is not None
            and outcome_violation.resolution_id == expected_resolution_id
            and expected_target_digest is not None
            and outcome_violation.target_digest == expected_target_digest
            and outcome_deadline_at is not None
            and outcome_violation.observed_at >= outcome_deadline_at
            and verification_time is not None
            and outcome_violation.observed_at <= verification_time
            and verification_time - outcome_violation.observed_at <= timedelta(days=7)
        )
        if valid_violation:
            return VerificationResult(
                verdict=ResolutionVerdict.FAIL,
                consumer_state=ConsumerState.NOT_COMPLETED,
                reason="A renewal charge was independently observed after the requested cancellation deadline.",
                action_receipt=receipt,
                evidence=evidence,
            )
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Outcome-violation evidence did not correlate to this owner, resolution, target, or deadline.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if not is_valid_cancellation_evidence(evidence):
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Independent evidence is malformed or unsafe to evaluate.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if evidence.account_readable is not True:
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Independent account state is unavailable.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if evidence.freshness_seconds is None or evidence.freshness_seconds > MAX_EVIDENCE_AGE_SECONDS:
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Independent evidence is missing or stale.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if not is_valid_action_receipt(receipt) or receipt.provider_reported_success is not True:
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Execution did not return a reliable successful action receipt.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if expected_target_digest is not None and (
        receipt.target_digest != expected_target_digest
        or evidence.target_digest != expected_target_digest
        or evidence.attempt_id != expected_attempt_id
    ):
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Independent evidence does not correlate to this action target and verification attempt.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if evidence.auto_renew is True:
        if terminal_failure:
            return VerificationResult(
                verdict=ResolutionVerdict.FAIL,
                consumer_state=ConsumerState.NOT_COMPLETED,
                reason="The bounded verification window ended and fresh account evidence still shows auto-renew enabled.",
                action_receipt=receipt,
                evidence=evidence,
            )
        return VerificationResult(
            verdict=ResolutionVerdict.INCONCLUSIVE,
            consumer_state=ConsumerState.AWAITING_PROOF,
            reason="Cancellation was accepted but auto-renew is still enabled; the outcome remains open.",
            action_receipt=receipt,
            evidence=evidence,
        )

    if evidence.auto_renew is False and evidence.effective_end_date:
        return VerificationResult(
            verdict=ResolutionVerdict.PASS,
            consumer_state=ConsumerState.VERIFIED,
            reason="Auto-renew is disabled and an effective end date is independently observable.",
            action_receipt=receipt,
            evidence=evidence,
        )

    return VerificationResult(
        verdict=ResolutionVerdict.INCONCLUSIVE,
        consumer_state=ConsumerState.AWAITING_PROOF,
        reason="Observed state does not contain enough evidence for completion.",
        action_receipt=receipt,
        evidence=evidence,
    )
