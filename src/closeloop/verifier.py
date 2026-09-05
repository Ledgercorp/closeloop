from .models import (
    ActionReceipt,
    CancellationEvidence,
    ConsumerState,
    ResolutionVerdict,
    VerificationResult,
)


MAX_EVIDENCE_AGE_SECONDS = 30


def verify_cancellation(
    receipt: ActionReceipt,
    evidence: CancellationEvidence,
) -> VerificationResult:
    """Deterministically verify whether subscription cancellation is proven.

    Important: provider-reported success is never sufficient for PASS.
    """

    if not evidence.account_readable:
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
