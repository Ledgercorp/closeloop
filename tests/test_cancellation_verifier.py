import pytest

from closeloop.demo_provider import DemoProvider
from closeloop.models import ConsumerState, ResolutionVerdict, demo_resource_identity
from closeloop.verifier import verify_cancellation


@pytest.mark.parametrize(
    ("mode", "expected_verdict", "expected_consumer_state"),
    [
        ("healthy", ResolutionVerdict.PASS, ConsumerState.VERIFIED),
        ("false_success", ResolutionVerdict.INCONCLUSIVE, ConsumerState.AWAITING_PROOF),
        ("evidence_outage", ResolutionVerdict.INCONCLUSIVE, ConsumerState.AWAITING_PROOF),
    ],
)
def test_flagship_demo_semantics(mode, expected_verdict, expected_consumer_state):
    provider = DemoProvider(mode=mode)
    target = demo_resource_identity("verifier-test-owner")
    attempt_id = "verifier-test-attempt"
    receipt = provider.cancel_subscription(target)
    evidence = provider.read_cancellation_evidence(target, attempt_id)
    result = verify_cancellation(
        receipt, evidence, expected_target_digest=target.target_digest,
        expected_attempt_id=attempt_id,
    )

    assert receipt.provider_reported_success is True
    assert result.verdict is expected_verdict
    assert result.consumer_state is expected_consumer_state


def test_false_success_never_becomes_pass():
    provider = DemoProvider(mode="false_success")
    target = demo_resource_identity("verifier-test-owner")
    attempt_id = "verifier-test-attempt"
    receipt = provider.cancel_subscription(target)
    evidence = provider.read_cancellation_evidence(target, attempt_id)
    result = verify_cancellation(
        receipt, evidence, expected_target_digest=target.target_digest,
        expected_attempt_id=attempt_id,
    )

    assert receipt.provider_reported_success is True
    assert evidence.auto_renew is True
    assert result.verdict is ResolutionVerdict.INCONCLUSIVE
