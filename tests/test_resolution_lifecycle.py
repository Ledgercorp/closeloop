from datetime import datetime

import pytest

from closeloop.demo_provider import DemoProvider
from closeloop.lifecycle import InvalidTransitionError, ResolutionError, ResolutionService
from closeloop.models import ActionReceipt, CancellationEvidence
from closeloop.repository import SqlResolutionRepository
from tests.confirmation_support import trusted_confirmation


INTENT = "Cancel my subscription and make sure I will not be charged again."
OWNER = "owner-a"


def make_service(tmp_path, provider_factory=DemoProvider):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'resolutions.db'}")
    return ResolutionService(repository, provider_factory)


class CountingProvider:
    def __init__(self) -> None:
        self.execution_count = 0
        self.read_count = 0

    def cancel_subscription(self) -> ActionReceipt:
        self.execution_count += 1
        return ActionReceipt("action-1", True, "Cancellation accepted")

    def read_cancellation_evidence(self) -> CancellationEvidence:
        self.read_count += 1
        return CancellationEvidence(True, False, "2026-09-30", 0)


def test_start_requires_confirmation_before_any_mutation(tmp_path):
    provider = CountingProvider()
    service = make_service(tmp_path, lambda _: provider)

    started = service.start_resolution(OWNER, INTENT)

    assert started["lifecycle_state"] == "AWAITING_CONFIRMATION"
    assert started["is_terminal"] is False
    assert started["confirmation_required"] is True
    assert started["verdict"] is None
    assert provider.execution_count == 0
    assert provider.read_count == 0

    with pytest.raises(ResolutionError, match="explicit confirmation"):
        service.confirm_resolution_action(OWNER, started["resolution_id"], confirmed=False)

    assert provider.execution_count == 0
    assert service.get_resolution_status(OWNER, started["resolution_id"]) == started


@pytest.mark.parametrize(
    ("provider_mode", "verdict", "consumer_state", "lifecycle_state"),
    [
        ("healthy", "PASS", "Verified", "VERIFIED"),
        ("false_success", "FAIL", "Not completed", "NOT_COMPLETED"),
        ("evidence_outage", "INCONCLUSIVE", "Awaiting proof", "AWAITING_PROOF"),
    ],
)
def test_confirmed_action_uses_independent_verification(
    tmp_path, provider_mode, verdict, consumer_state, lifecycle_state
):
    service = make_service(tmp_path)
    started = service.start_resolution(OWNER, INTENT, provider_mode)

    completed = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )
    evidence = service.get_resolution_evidence(OWNER, started["resolution_id"])

    assert completed["lifecycle_state"] == lifecycle_state
    assert completed["verdict"] == verdict
    assert completed["consumer_state"] == consumer_state
    assert completed["is_terminal"] is True
    assert evidence["execution_claim"]["provider_reported_success"] is True
    assert evidence["execution_claim"]["evidence_type"] == "execution_claim"
    assert evidence["independent_read_back"]["evidence_type"] == "independent_read_back"
    assert evidence["verification"]["verdict"] == verdict
    assert evidence["verification"]["consumer_state"] == consumer_state


def test_provider_success_claim_cannot_create_verified_result(tmp_path):
    service = make_service(tmp_path)
    started = service.start_resolution(OWNER, INTENT, "false_success")

    completed = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )
    evidence = service.get_resolution_evidence(OWNER, started["resolution_id"])

    assert evidence["execution_claim"]["provider_reported_success"] is True
    assert evidence["independent_read_back"]["auto_renew"] is True
    assert completed["verdict"] == "FAIL"
    assert completed["consumer_state"] == "Not completed"
    assert completed["lifecycle_state"] == "NOT_COMPLETED"


def test_status_and_evidence_reads_do_not_mutate_outcome(tmp_path):
    service = make_service(tmp_path)
    started = service.start_resolution(OWNER, INTENT, "healthy")
    terminal = service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )

    first_status = service.get_resolution_status(OWNER, started["resolution_id"])
    first_evidence = service.get_resolution_evidence(OWNER, started["resolution_id"])
    second_status = service.get_resolution_status(OWNER, started["resolution_id"])
    second_evidence = service.get_resolution_evidence(OWNER, started["resolution_id"])

    assert first_status == second_status == terminal
    assert first_evidence == second_evidence
    assert [item["state"] for item in first_evidence["state_history"]] == [
        "REQUESTED",
        "AWAITING_CONFIRMATION",
        "EXECUTING",
        "VERIFYING",
        "VERIFIED",
    ]


def test_repeated_confirmation_rejects_invalid_terminal_transition(tmp_path):
    provider = CountingProvider()
    service = make_service(tmp_path, lambda _: provider)
    started = service.start_resolution(OWNER, INTENT)
    attestation = trusted_confirmation(started, OWNER)
    service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=attestation,
    )

    with pytest.raises(InvalidTransitionError, match="cannot confirm"):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            confirmation_attestation=attestation,
        )

    assert provider.execution_count == 1


def test_list_open_resolutions_only_returns_non_terminal_records(tmp_path):
    service = make_service(tmp_path)
    open_resolution = service.start_resolution(OWNER, "Cancel subscription A")
    completed_resolution = service.start_resolution(OWNER, "Cancel subscription B")
    service.confirm_resolution_action(
        OWNER,
        completed_resolution["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(completed_resolution, OWNER),
    )

    listed = service.list_open_resolutions(OWNER)

    assert [item["resolution_id"] for item in listed] == [open_resolution["resolution_id"]]
    assert listed[0]["is_terminal"] is False


def test_evidence_has_stable_provenance_timestamps_and_identifiers(tmp_path):
    service = make_service(tmp_path)
    started = service.start_resolution(OWNER, INTENT)
    service.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER),
    )

    evidence = service.get_resolution_evidence(OWNER, started["resolution_id"])

    assert evidence["resolution_id"] == started["resolution_id"]
    assert evidence["action_digest"] == started["action_digest"]
    assert evidence["execution_claim"]["request_id"]
    assert evidence["execution_claim"]["source"] == "demo_provider.cancel_subscription"
    assert (
        evidence["independent_read_back"]["source"]
        == "demo_provider.read_cancellation_evidence"
    )
    assert evidence["verification"]["verifier"] == "closeloop.verify_cancellation/v1"
    for timestamp in (
        evidence["execution_claim"]["observed_at"],
        evidence["independent_read_back"]["observed_at"],
        evidence["verification"]["evaluated_at"],
    ):
        assert datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is not None


def test_callers_have_no_direct_verdict_override_parameter(tmp_path):
    service = make_service(tmp_path)
    started = service.start_resolution(OWNER, INTENT, "false_success")

    with pytest.raises(TypeError):
        service.confirm_resolution_action(
            OWNER,
            started["resolution_id"],
            confirmed=True,
            verdict="PASS",
        )

    assert service.get_resolution_status(OWNER, started["resolution_id"])["verdict"] is None
