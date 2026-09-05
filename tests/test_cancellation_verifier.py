import pytest

from closeloop.demo_provider import DemoProvider
from closeloop.models import ConsumerState, ResolutionVerdict
from closeloop.verifier import verify_cancellation


@pytest.mark.parametrize(
    ("mode", "expected_verdict", "expected_consumer_state"),
    [
        ("healthy", ResolutionVerdict.PASS, ConsumerState.VERIFIED),
        ("false_success", ResolutionVerdict.FAIL, ConsumerState.NOT_COMPLETED),
        ("evidence_outage", ResolutionVerdict.INCONCLUSIVE, ConsumerState.AWAITING_PROOF),
    ],
)
def test_flagship_demo_semantics(mode, expected_verdict, expected_consumer_state):
    provider = DemoProvider(mode=mode)
    receipt = provider.cancel_subscription()
    evidence = provider.read_cancellation_evidence()

    result = verify_cancellation(receipt, evidence)

    assert receipt.provider_reported_success is True
    assert result.verdict is expected_verdict
    assert result.consumer_state is expected_consumer_state


def test_false_success_never_becomes_pass():
    provider = DemoProvider(mode="false_success")
    receipt = provider.cancel_subscription()
    evidence = provider.read_cancellation_evidence()

    result = verify_cancellation(receipt, evidence)

    assert receipt.provider_reported_success is True
    assert evidence.auto_renew is True
    assert result.verdict is ResolutionVerdict.FAIL
