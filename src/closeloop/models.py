from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Optional


class ResolutionVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ConsumerState(str, Enum):
    VERIFIED = "Verified"
    NOT_COMPLETED = "Not completed"
    AWAITING_PROOF = "Awaiting proof"


@dataclass(frozen=True)
class ResourceIdentity:
    provider: str
    account_subject: str
    resource_id: str
    target_digest: str

    @classmethod
    def create(cls, provider: str, account_subject: str, resource_id: str) -> ResourceIdentity:
        canonical = json.dumps(
            [provider, account_subject, resource_id], separators=(",", ":")
        )
        return cls(provider, account_subject, resource_id, sha256(canonical.encode()).hexdigest())


def demo_resource_identity(owner_id: str) -> ResourceIdentity:
    """Return the deterministic, explicitly simulated StreamBox target."""
    subject = sha256(owner_id.encode()).hexdigest()
    return ResourceIdentity.create("demo_provider", subject, "streambox-subscription")


@dataclass(frozen=True)
class ActionReceipt:
    request_id: str
    provider_reported_success: bool
    message: str
    target_digest: str | None = None


@dataclass(frozen=True)
class CancellationEvidence:
    account_readable: bool
    auto_renew: Optional[bool]
    effective_end_date: Optional[str]
    freshness_seconds: Optional[int] = 0
    target_digest: str | None = None
    attempt_id: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    verdict: ResolutionVerdict
    consumer_state: ConsumerState
    reason: str
    action_receipt: ActionReceipt
    evidence: CancellationEvidence
