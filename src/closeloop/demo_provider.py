from dataclasses import dataclass
from uuid import uuid4

from .models import ActionReceipt, CancellationEvidence, ResourceIdentity


@dataclass
class DemoSubscription:
    active: bool = True
    auto_renew: bool = True
    paid_through: str = "2026-09-30"


class DemoProvider:
    """First-party sandbox provider with explicit fault injection.

    Modes:
    - healthy: cancellation mutates account state and reports success.
    - false_success: reports success but leaves auto-renew on.
    - terminal_failure: leaves auto-renew on until the bounded verification window ends.
    - evidence_outage: action succeeds, but independent read-back is unavailable.
    """

    def __init__(self, mode: str = "healthy") -> None:
        if mode not in {"healthy", "false_success", "evidence_outage", "terminal_failure"}:
            raise ValueError(f"unsupported mode: {mode}")
        self.mode = mode
        self.subscription = DemoSubscription()

    def cancel_subscription(self, target: ResourceIdentity) -> ActionReceipt:
        request_id = str(uuid4())
        if self.mode == "healthy":
            self.subscription.auto_renew = False
            return ActionReceipt(request_id, True, "Cancellation accepted", target.target_digest)

        if self.mode in {"false_success", "terminal_failure"}:
            return ActionReceipt(request_id, True, "Cancellation accepted", target.target_digest)

        # evidence_outage: the mutation succeeds, but proof cannot be read later.
        self.subscription.auto_renew = False
        return ActionReceipt(request_id, True, "Cancellation accepted", target.target_digest)

    def read_cancellation_evidence(
        self, target: ResourceIdentity, attempt_id: str
    ) -> CancellationEvidence:
        if self.mode == "evidence_outage":
            return CancellationEvidence(
                account_readable=False,
                auto_renew=None,
                effective_end_date=None,
                freshness_seconds=None,
                target_digest=target.target_digest,
                attempt_id=attempt_id,
            )

        return CancellationEvidence(
            account_readable=True,
            auto_renew=self.subscription.auto_renew,
            effective_end_date=self.subscription.paid_through,
            freshness_seconds=0,
            target_digest=target.target_digest,
            attempt_id=attempt_id,
        )
