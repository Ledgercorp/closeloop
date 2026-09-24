from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import jwt
import pytest

from closeloop.confirmation import (
    CONFIRMATION_CONTRACT_VERSION,
    HmacJwtConfirmationAttestationVerifier,
)
from closeloop.lifecycle import (
    InvalidTransitionError,
    ResolutionError,
    ResolutionNotFoundError,
    ResolutionService,
)
from closeloop.models import ActionReceipt, CancellationEvidence, ResolutionVerdict
from closeloop.outcomes import OutcomeViolation, UnsupportedOutcomeRequest
from closeloop.repository import SqlResolutionRepository
from closeloop.verifier import verify_cancellation
from tests.confirmation_support import trusted_confirmation

OWNER = "outcome-management-owner"
ISSUER = "https://confirmation-authority.test"
AUDIENCE = "https://closeloop.test/confirmation"
SECRET = "outcome-management-test-secret-that-is-at-least-thirty-two-bytes"


class RecoveryProvider:
    def __init__(self) -> None:
        self.cancellations = 0
        self.recoveries = 0
        self.auto_renew = True
        self.readable = True
        self.recovery_changes_state = True

    def cancel_subscription(self, target):
        self.cancellations += 1
        return ActionReceipt("cancel-1", True, "accepted", target.target_digest)

    def read_cancellation_evidence(self, target, attempt_id):
        return CancellationEvidence(
            self.readable, self.auto_renew if self.readable else None,
            None if self.auto_renew or not self.readable else "2026-10-03", 0,
            target.target_digest, attempt_id,
        )

    def execute_recovery(self, action):
        self.recoveries += 1
        if self.recovery_changes_state:
            self.auto_renew = False
        return {
            "source": "demo_provider.simulated_recovery",
            "request_id": f"recovery-{action.recovery_id}",
            "action_digest": action.action_digest,
            "target_digest": action.target_digest,
            "claimed_success": True,
            "summary": "follow-up prepared",
        }


def _service(tmp_path, provider):
    confirmation_verifier = HmacJwtConfirmationAttestationVerifier(
        secret=SECRET, issuer=ISSUER, audience=AUDIENCE,
    )
    return ResolutionService(
        repository=SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'outcomes.db'}"),
        provider_factory=lambda _: provider,
        confirmation_verifier=confirmation_verifier,
        recovery_provider=provider,
    )


def _recovery_confirmation(proposal, resolution_id: str, now: datetime) -> str:
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "confirmation_contract": CONFIRMATION_CONTRACT_VERSION,
            "sub": OWNER,
            "resolution_id": resolution_id,
            "action": proposal["action_type"],
            "action_digest": proposal["provenance"]["action_digest"],
            "confirmed": True,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=30)).timestamp()),
            "jti": str(uuid4()),
        },
        SECRET,
        algorithm="HS256",
    )


def test_supported_intent_creates_persisted_contract_and_rejects_unsupported(tmp_path):
    service = _service(tmp_path, RecoveryProvider())
    with pytest.raises(UnsupportedOutcomeRequest):
        service.start_resolution(OWNER, "Please email the retailer and get my refund")

    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    assert started["outcome_contract"]["resolution_type"] == "CANCELLATION"
    assert started["outcome_contract"]["desired_state"] == "subscription.auto_renew == false"
    assert started["outcome_contract"]["recovery_policy"] == "user_confirmation_required"


@pytest.mark.parametrize("age", [-1, 8 * 24 * 60 * 60])
def test_future_or_stale_outcome_violation_cannot_establish_failure(age):
    deadline = datetime(2026, 9, 25, tzinfo=timezone.utc)
    observed_at = deadline + timedelta(minutes=1)
    verification_time = observed_at + timedelta(seconds=age)
    violation = OutcomeViolation(
        violation_id=str(uuid4()), owner_id=OWNER, resolution_id="resolution-1",
        target_digest="a" * 64, event_type="renewal_charge", amount_cents=1999,
        currency="USD", source="demo_billing_readback", evidence_id="charge-1",
        observed_at=observed_at,
    )
    result = verify_cancellation(
        ActionReceipt("request-1", True, "accepted", "a" * 64),
        CancellationEvidence(False, None, None, None, "a" * 64, "attempt-1"),
        expected_target_digest="a" * 64,
        expected_attempt_id="attempt-1",
        outcome_violation=violation,
        expected_owner_id=OWNER,
        expected_resolution_id="resolution-1",
        outcome_deadline_at=deadline,
        verification_time=verification_time,
    )
    assert result.verdict is ResolutionVerdict.INCONCLUSIVE


def test_recovery_uses_separate_bound_confirmation_and_is_reverified(tmp_path):
    provider = RecoveryProvider()
    service = _service(tmp_path, provider)
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    accepted = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(
        accepted["outcome_contract"]["deadline_at"].replace("Z", "+00:00")
    )
    attention_time = deadline - timedelta(hours=5)
    accepted = service.recheck_resolution(
        OWNER, started["resolution_id"], force=True, now=attention_time,
    )
    proposal = accepted["recovery_proposal"]
    assert accepted["lifecycle_state"] == "AWAITING_PROOF"
    assert accepted["attention"]["level"] == "ACTION_NEEDED"
    assert proposal["requires_confirmation"] is True
    assert provider.cancellations == 1
    now = attention_time + timedelta(seconds=30)

    with pytest.raises(ResolutionError):
        service.confirm_recovery_action(
            OWNER, started["resolution_id"], proposal["recovery_id"], confirmed=True,
            confirmation_attestation=trusted_confirmation(
                started, OWNER, secret=SECRET, issuer=ISSUER,
            ),
            now=now,
        )

    action_id = proposal["recovery_id"]
    attestation = _recovery_confirmation(proposal, started["resolution_id"], now)
    with pytest.raises(ResolutionNotFoundError):
        service.confirm_recovery_action(
            "another-owner", started["resolution_id"], action_id, confirmed=True,
            confirmation_attestation=attestation, now=now,
        )
    with pytest.raises(ResolutionError):
        service.confirm_recovery_action(
            OWNER, started["resolution_id"], action_id, confirmed=True,
            confirmation_attestation=_recovery_confirmation(
                {**proposal, "action_type": "another_action"}, started["resolution_id"], now,
            ),
            now=now,
        )
    assert provider.recoveries == 0
    def confirm_recovery():
        try:
            return service.confirm_recovery_action(
                OWNER, started["resolution_id"], action_id, confirmed=True,
                confirmation_attestation=attestation, now=now,
            )
        except ResolutionError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(confirm_recovery) for _ in range(2)]
        executed_results = [result.result() for result in results]
    successful = [result for result in executed_results if result is not None]
    assert len(successful) == 1
    executed = successful[0]
    assert executed["lifecycle_state"] == "AWAITING_PROOF"
    assert executed["recovery_actions"][0]["state"] == "VERIFYING"
    assert executed["recovery_actions"][0]["execution_receipt"]["claimed_success"] is True

    due = datetime.fromisoformat(executed["next_check_at"].replace("Z", "+00:00"))
    resolved = service.recheck_resolution(
        OWNER, started["resolution_id"], scheduled_for=due, now=due,
    )
    assert resolved["lifecycle_state"] == "VERIFIED"
    assert resolved["recovery_actions"][0]["state"] == "COMPLETED"
    assert provider.cancellations == 1
    assert provider.recoveries == 1
    with pytest.raises(InvalidTransitionError):
        service.confirm_recovery_action(
            OWNER, started["resolution_id"], action_id, confirmed=True,
            confirmation_attestation=attestation, now=now,
        )
    assert provider.cancellations == 1
    assert provider.recoveries == 1


def test_attention_and_recovery_proposals_are_not_duplicated_for_same_condition(tmp_path):
    provider = RecoveryProvider()
    service = _service(tmp_path, provider)
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(status["outcome_contract"]["deadline_at"].replace("Z", "+00:00"))
    attention_time = deadline - timedelta(hours=5)
    service.recheck_resolution(OWNER, started["resolution_id"], force=True, now=attention_time)
    service.recheck_resolution(
        OWNER, started["resolution_id"], force=True,
        now=attention_time + timedelta(minutes=6),
    )
    record = service._repository.get_owned(started["resolution_id"], OWNER)
    assert len(record.attention_events) == 1
    assert len(record.recovery_actions) == 1
    assert provider.cancellations == 1
    assert provider.recoveries == 0


def test_no_actionable_recovery_is_offered_without_configured_provider(tmp_path):
    provider = RecoveryProvider()
    service = ResolutionService(
        repository=SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'no-recovery.db'}"),
        provider_factory=lambda _: provider,
        confirmation_verifier=HmacJwtConfirmationAttestationVerifier(
            secret=SECRET, issuer=ISSUER, audience=AUDIENCE,
        ),
    )
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(status["outcome_contract"]["deadline_at"].replace("Z", "+00:00"))
    status = service.recheck_resolution(
        OWNER, started["resolution_id"], force=True,
        now=deadline - timedelta(hours=5),
    )
    assert status["attention"]["level"] == "ACTION_NEEDED"
    assert status["recovery_proposal"] is None
    assert provider.recoveries == 0


def test_expired_recovery_proposal_cannot_execute(tmp_path):
    provider = RecoveryProvider()
    service = _service(tmp_path, provider)
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(status["outcome_contract"]["deadline_at"].replace("Z", "+00:00"))
    attention_time = deadline - timedelta(hours=5)
    status = service.recheck_resolution(
        OWNER, started["resolution_id"], force=True, now=attention_time,
    )
    proposal = status["recovery_proposal"]
    expires_at = datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00"))

    with pytest.raises(InvalidTransitionError, match="expired"):
        service.confirm_recovery_action(
            OWNER, started["resolution_id"], proposal["recovery_id"], confirmed=True,
            confirmation_attestation="not-a-confirmation", now=expires_at + timedelta(seconds=1),
        )

    stored = service._repository.get_owned(started["resolution_id"], OWNER)
    assert stored.recovery_actions[0].state.value == "EXPIRED"
    assert provider.recoveries == 0


def test_recovery_provider_claim_cannot_certify_resolution(tmp_path):
    provider = RecoveryProvider()
    provider.recovery_changes_state = False
    service = _service(tmp_path, provider)
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(status["outcome_contract"]["deadline_at"].replace("Z", "+00:00"))
    now = deadline - timedelta(hours=5)
    status = service.recheck_resolution(OWNER, started["resolution_id"], force=True, now=now)
    proposal = status["recovery_proposal"]
    assert proposal is not None
    confirmation_time = now + timedelta(seconds=30)
    status = service.confirm_recovery_action(
        OWNER, started["resolution_id"], proposal["recovery_id"], confirmed=True,
        confirmation_attestation=_recovery_confirmation(
            proposal, started["resolution_id"], confirmation_time,
        ),
        now=confirmation_time,
    )
    assert status["recovery_actions"][0]["execution_receipt"]["claimed_success"] is True
    due = datetime.fromisoformat(status["next_check_at"].replace("Z", "+00:00"))
    checked = service.recheck_resolution(
        OWNER, started["resolution_id"], scheduled_for=due, now=due,
    )
    assert checked["lifecycle_state"] == "AWAITING_PROOF"
    assert checked["verdict"] == "INCONCLUSIVE"
    assert provider.cancellations == 1
    assert provider.recoveries == 1


def test_recovery_confirmation_is_bound_to_resolution_and_target(tmp_path):
    provider = RecoveryProvider()
    service = _service(tmp_path, provider)
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(started["outcome_contract"]["deadline_at"].replace("Z", "+00:00"))
    now = deadline - timedelta(hours=5)
    status = service.recheck_resolution(OWNER, started["resolution_id"], force=True, now=now)
    proposal = status["recovery_proposal"]
    valid = _recovery_confirmation(proposal, started["resolution_id"], now + timedelta(seconds=30))
    claims = jwt.decode(
        valid, SECRET, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
        options={"verify_iat": False},
    )

    for field, value in (("resolution_id", "another-resolution"), ("action_digest", "0" * 64)):
        tampered = jwt.encode({**claims, field: value}, SECRET, algorithm="HS256")
        with pytest.raises(ResolutionError):
            service.confirm_recovery_action(
                OWNER, started["resolution_id"], proposal["recovery_id"],
                confirmed=True, confirmation_attestation=tampered,
                now=now + timedelta(seconds=30),
            )

    assert provider.recoveries == 0
    assert provider.cancellations == 1


def test_recovery_remains_open_when_readback_is_unavailable_then_recovers(tmp_path):
    provider = RecoveryProvider()
    service = _service(tmp_path, provider)
    started = service.start_resolution(
        OWNER, "Cancel StreamBox before next Friday and make sure I don't get charged again."
    )
    service.confirm_resolution_action(
        OWNER, started["resolution_id"], True,
        trusted_confirmation(started, OWNER, secret=SECRET, issuer=ISSUER),
    )
    deadline = datetime.fromisoformat(started["outcome_contract"]["deadline_at"].replace("Z", "+00:00"))
    attention_at = deadline - timedelta(hours=5)
    proposal = service.recheck_resolution(
        OWNER, started["resolution_id"], force=True, now=attention_at
    )["recovery_proposal"]
    recovery_at = attention_at + timedelta(seconds=30)
    executed = service.confirm_recovery_action(
        OWNER, started["resolution_id"], proposal["recovery_id"], confirmed=True,
        confirmation_attestation=_recovery_confirmation(proposal, started["resolution_id"], recovery_at),
        now=recovery_at,
    )

    provider.readable = False
    due = datetime.fromisoformat(executed["next_check_at"].replace("Z", "+00:00"))
    unknown = service.recheck_resolution(
        OWNER, started["resolution_id"], scheduled_for=due, now=due
    )
    assert unknown["lifecycle_state"] == "AWAITING_PROOF"
    assert unknown["verdict"] == "INCONCLUSIVE"
    assert unknown["recovery_actions"][0]["state"] == "VERIFYING"
    assert provider.cancellations == 1
    assert provider.recoveries == 1

    provider.readable = True
    next_due = datetime.fromisoformat(unknown["next_check_at"].replace("Z", "+00:00"))
    verified = service.recheck_resolution(
        OWNER, started["resolution_id"], scheduled_for=next_due, now=next_due
    )
    assert verified["lifecycle_state"] == "VERIFIED"
    assert verified["resolution_id"] == started["resolution_id"]
    assert provider.cancellations == 1
    assert provider.recoveries == 1
