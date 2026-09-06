from datetime import date
import re

from .models import (
    ActionReceipt,
    CancellationEvidence,
    ConsumerState,
    ResolutionVerdict,
    VerificationResult,
)


MAX_EVIDENCE_AGE_SECONDS = 30


def is_valid_action_receipt(receipt: object) -> bool:
    return (
        isinstance(receipt, ActionReceipt)
        and isinstance(receipt.request_id, str)
        and bool(receipt.request_id.strip())
        and type(receipt.provider_reported_success) is bool
        and isinstance(receipt.message, str)
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
) -> VerificationResult:
    """Deterministically verify whether subscription cancellation is proven.

    Important: provider-reported success is never sufficient for PASS.
    """

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

    if evidence.auto_renew is True:
        return VerificationResult(
            verdict=ResolutionVerdict.FAIL,
            consumer_state=ConsumerState.NOT_COMPLETED,
            reason="Account is readable and auto-renew is still enabled.",
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
