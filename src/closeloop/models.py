from dataclasses import dataclass
from enum import Enum
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
class ActionReceipt:
    request_id: str
    provider_reported_success: bool
    message: str


@dataclass(frozen=True)
class CancellationEvidence:
    account_readable: bool
    auto_renew: Optional[bool]
    effective_end_date: Optional[str]
    freshness_seconds: Optional[int] = 0


@dataclass(frozen=True)
class VerificationResult:
    verdict: ResolutionVerdict
    consumer_state: ConsumerState
    reason: str
    action_receipt: ActionReceipt
    evidence: CancellationEvidence
