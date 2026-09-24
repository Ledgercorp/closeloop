from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from closeloop.lifecycle import (
    InvalidTransitionError,
    ResolutionNotFoundError,
    ResolutionService,
    ResolutionStorageUnavailableError,
)
from closeloop.demo_provider import DemoProvider
from closeloop.models import ActionReceipt, CancellationEvidence
from closeloop.repository import SqlResolutionRepository
from closeloop.repository_contract import record_from_mapping, record_to_mapping
from tests.confirmation_support import trusted_confirmation


OWNER = "persistent-owner"
INTENT = "Cancel StreamBox before renewal and confirm the outcome."


class MutableProvider:
    def __init__(self) -> None:
        self.cancel_count = 0
        self.read_count = 0
        self.evidence = CancellationEvidence(False, None, None, 900)

    def cancel_subscription(self, target) -> ActionReceipt:
        self.cancel_count += 1
        return ActionReceipt("request-1", True, "Cancellation accepted", target.target_digest)

    def read_cancellation_evidence(self, target, attempt_id) -> CancellationEvidence:
        self.read_count += 1
        evidence = self.evidence
        return CancellationEvidence(
            evidence.account_readable,
            evidence.auto_renew,
            evidence.effective_end_date,
            evidence.freshness_seconds,
            target.target_digest,
            attempt_id,
        )


class CrashOnceProvider(MutableProvider):
    def read_cancellation_evidence(self, target, attempt_id) -> CancellationEvidence:
        self.read_count += 1
        if self.read_count == 1:
            raise SystemExit("simulated process stop after execution claim")
        return CancellationEvidence(True, False, "2026-10-03", 0, target.target_digest, attempt_id)


def make_service(database, provider):
    return ResolutionService(
        SqlResolutionRepository(f"sqlite+pysqlite:///{database}"),
        lambda _: provider,
    )


def test_awaiting_proof_survives_restart_then_resolves_same_record(tmp_path):
    database = tmp_path / "persistent.db"
    provider = MutableProvider()
    day_one = make_service(database, provider)
    started = day_one.start_resolution(OWNER, INTENT, provider_mode="evidence_outage")
    awaiting = day_one.confirm_resolution_action(
        OWNER,
        started["resolution_id"],
        True,
        trusted_confirmation(started, OWNER),
    )

    assert awaiting["lifecycle_state"] == "AWAITING_PROOF"
    assert awaiting["is_terminal"] is False
    assert awaiting["check_count"] == 1
    assert awaiting["next_check_at"]
    assert len(day_one.get_resolution_evidence(OWNER, started["resolution_id"])["verification_history"]) == 1
    assert [x["resolution_id"] for x in day_one.list_open_resolutions(OWNER)] == [started["resolution_id"]]

    # A new service instance represents a later session; only independent evidence changes.
    provider.evidence = CancellationEvidence(True, False, "2026-10-03", 0)
    day_two = make_service(database, provider)
    due = datetime.fromisoformat(awaiting["next_check_at"].replace("Z", "+00:00"))
    resolved = day_two.recheck_resolution(
        OWNER, started["resolution_id"], scheduled_for=due, now=due
    )

    assert resolved["resolution_id"] == started["resolution_id"]
    assert resolved["lifecycle_state"] == "VERIFIED"
    assert resolved["is_terminal"] is True
    assert resolved["resolved_at"]
    assert resolved["check_count"] == 2
    assert provider.cancel_count == 1
    assert provider.read_count == 2
    assert len(day_two.get_resolution_evidence(OWNER, started["resolution_id"])["verification_history"]) == 2
    assert [x["resolution_id"] for x in day_two.list_recent_resolutions(OWNER)] == [started["resolution_id"]]
    with pytest.raises(ResolutionNotFoundError):
        day_two.get_resolution_status("another-owner", started["resolution_id"])
    with pytest.raises(InvalidTransitionError):
        day_two.recheck_resolution(OWNER, started["resolution_id"], scheduled_for=due, now=due)
    assert provider.cancel_count == 1


def test_rechecks_are_bounded_and_stale_scheduled_checks_are_rejected(tmp_path):
    database = tmp_path / "bounded.db"
    provider = MutableProvider()
    service = make_service(database, provider)
    started = service.start_resolution(OWNER, INTENT, provider_mode="evidence_outage")
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
    )
    stale_schedule = datetime.fromisoformat(status["next_check_at"].replace("Z", "+00:00"))
    status = service.recheck_resolution(
        OWNER, started["resolution_id"], scheduled_for=stale_schedule, now=stale_schedule
    )
    with pytest.raises(InvalidTransitionError, match="stale"):
        service.recheck_resolution(
            OWNER,
            started["resolution_id"],
            scheduled_for=stale_schedule,
            now=stale_schedule + timedelta(minutes=5),
        )
    for _ in range(2):
        due = datetime.fromisoformat(status["next_check_at"].replace("Z", "+00:00"))
        status = service.recheck_resolution(
            OWNER, started["resolution_id"], scheduled_for=due, now=due
        )
    assert status["lifecycle_state"] == "AWAITING_PROOF"
    assert status["check_count"] == status["max_checks"] == 4
    assert status["next_check_at"] is None
    assert len(service.get_resolution_evidence(OWNER, started["resolution_id"])["verification_history"]) == 4
    with pytest.raises(InvalidTransitionError, match="attempt limit"):
        service.recheck_resolution(OWNER, started["resolution_id"], force=True)
    assert provider.cancel_count == 1
    assert provider.read_count == 4


def test_fresh_enabled_state_at_bounded_deadline_is_not_completed(tmp_path):
    database = tmp_path / "terminal-failure.db"
    provider = MutableProvider()
    provider.evidence = CancellationEvidence(True, True, None, 0)
    service = make_service(database, provider)
    started = service.start_resolution(OWNER, INTENT)
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
    )

    while status["check_count"] < status["max_checks"]:
        due = datetime.fromisoformat(status["next_check_at"].replace("Z", "+00:00"))
        status = service.recheck_resolution(
            OWNER,
            started["resolution_id"],
            scheduled_for=due,
            now=due,
        )

    assert status["lifecycle_state"] == "NOT_COMPLETED"
    assert status["verdict"] == "FAIL"
    assert status["is_terminal"] is True
    assert status["next_check_at"] is None
    assert provider.cancel_count == 1
    assert provider.read_count == 4


def test_early_manual_rechecks_cannot_shorten_failure_window(tmp_path):
    database = tmp_path / "early-failure-checks.db"
    provider = MutableProvider()
    provider.evidence = CancellationEvidence(True, True, None, 0)
    service = make_service(database, provider)
    started = service.start_resolution(OWNER, INTENT)
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
    )
    early = datetime.fromisoformat(status["updated_at"].replace("Z", "+00:00")) + timedelta(minutes=1)
    due = datetime.fromisoformat(status["next_check_at"].replace("Z", "+00:00"))
    with pytest.raises(InvalidTransitionError, match="premature"):
        service.recheck_resolution(
            OWNER,
            started["resolution_id"],
            scheduled_for=due,
            now=early,
        )

    while status["check_count"] < status["max_checks"]:
        status = service.recheck_resolution(
            OWNER,
            started["resolution_id"],
            force=True,
            now=early,
        )

    assert status["lifecycle_state"] == "AWAITING_PROOF"
    assert status["verdict"] == "INCONCLUSIVE"
    assert status["is_terminal"] is False
    assert provider.cancel_count == 1


def test_provider_rejection_never_becomes_not_completed(tmp_path):
    database = tmp_path / "rejected-action.db"

    class RejectedProvider(MutableProvider):
        def cancel_subscription(self, target) -> ActionReceipt:
            self.cancel_count += 1
            return ActionReceipt("request-1", False, "Rejected", target.target_digest)

    provider = RejectedProvider()
    provider.evidence = CancellationEvidence(True, True, None, 0)
    service = make_service(database, provider)
    started = service.start_resolution(OWNER, INTENT)
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
    )
    assert status["lifecycle_state"] == "AWAITING_PROOF"
    assert status["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("mismatch", ["resource", "prior_attempt"])
def test_unrelated_or_transplanted_readback_cannot_resolve(mismatch, tmp_path):
    class MismatchedEvidenceProvider(MutableProvider):
        def read_cancellation_evidence(self, target, attempt_id):
            evidence = super().read_cancellation_evidence(target, attempt_id)
            if mismatch == "resource":
                return CancellationEvidence(True, False, "2026-10-03", 0, "f" * 64, attempt_id)
            return CancellationEvidence(
                True, False, "2026-10-03", 0, target.target_digest, "prior-attempt"
            )

    provider = MismatchedEvidenceProvider()
    provider.evidence = CancellationEvidence(True, False, "2026-10-03", 0)
    service = make_service(tmp_path / f"{mismatch}.db", provider)
    started = service.start_resolution(OWNER, INTENT)
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
    )
    assert status["lifecycle_state"] == "AWAITING_PROOF"
    assert status["verdict"] == "INCONCLUSIVE"


def test_target_identity_is_owner_scoped_and_action_confirmation_bound(tmp_path):
    service = make_service(tmp_path / "target-identity.db", MutableProvider())
    first = service.start_resolution("owner-one", INTENT)
    second = service.start_resolution("owner-two", INTENT)
    first_record = service._repository.get_owned(first["resolution_id"], "owner-one")
    second_record = service._repository.get_owned(second["resolution_id"], "owner-two")
    assert first_record.target.target_digest != second_record.target.target_digest
    assert first_record.target.resource_id == "streambox-subscription"


def test_malformed_persisted_recheck_budget_fails_closed(tmp_path):
    service = make_service(tmp_path / "bad-budget.db", MutableProvider())
    started = service.start_resolution(OWNER, INTENT)
    record = service._repository.get_owned(started["resolution_id"], OWNER)
    mapping = record_to_mapping(record, serialize_datetimes=True)
    mapping["max_checks"] = 5000
    with pytest.raises(ResolutionStorageUnavailableError, match="invalid"):
        record_from_mapping(mapping)


def test_concurrent_recheck_claim_allows_one_evidence_read(tmp_path):
    database = tmp_path / "concurrent.db"
    provider = MutableProvider()
    service = make_service(database, provider)
    started = service.start_resolution(OWNER, INTENT, provider_mode="evidence_outage")
    status = service.confirm_resolution_action(
        OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
    )
    due = datetime.fromisoformat(status["next_check_at"].replace("Z", "+00:00"))
    other_service = make_service(database, provider)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            service.recheck_resolution,
            OWNER,
            started["resolution_id"],
            scheduled_for=due,
            now=due,
        )
        second = pool.submit(
            other_service.recheck_resolution,
            OWNER,
            started["resolution_id"],
            scheduled_for=due,
            now=due,
        )
        outcomes = []
        for future in (first, second):
            try:
                outcomes.append(future.result())
            except InvalidTransitionError:
                outcomes.append(None)
    assert sum(outcome is not None for outcome in outcomes) == 1
    assert provider.cancel_count == 1
    assert provider.read_count == 2


def test_restart_after_action_resumes_readback_without_repeating_action(tmp_path):
    database = tmp_path / "restart-mid-verification.db"
    provider = CrashOnceProvider()
    day_one = make_service(database, provider)
    started = day_one.start_resolution(OWNER, INTENT)
    with pytest.raises(SystemExit, match="simulated process stop"):
        day_one.confirm_resolution_action(
            OWNER, started["resolution_id"], True, trusted_confirmation(started, OWNER)
        )
    verifying = make_service(database, provider).get_resolution_status(
        OWNER, started["resolution_id"]
    )
    assert verifying["lifecycle_state"] == "VERIFYING"
    assert verifying["check_count"] == 1

    restarted = make_service(database, provider)
    recovery_time = datetime.fromisoformat(verifying["updated_at"].replace("Z", "+00:00"))
    recovered = restarted.recheck_resolution(
        OWNER,
        started["resolution_id"],
        now=recovery_time + timedelta(minutes=5),
    )
    assert recovered["lifecycle_state"] == "VERIFIED"
    assert recovered["is_terminal"] is True
    assert provider.cancel_count == 1


def test_evidence_history_from_another_resolution_cannot_be_stored(tmp_path):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'wrong-evidence.db'}")
    service = ResolutionService(repository, lambda mode: DemoProvider(mode))
    first = service.start_resolution(OWNER, INTENT, provider_mode="false_success")
    second = service.start_resolution(OWNER, INTENT, provider_mode="evidence_outage")
    service.confirm_resolution_action(
        OWNER, first["resolution_id"], True, trusted_confirmation(first, OWNER)
    )
    service.confirm_resolution_action(
        OWNER, second["resolution_id"], True, trusted_confirmation(second, OWNER)
    )
    source = repository.get_owned(first["resolution_id"], OWNER)
    target = repository.get_owned(second["resolution_id"], OWNER)
    target.independent_evidence = source.independent_evidence
    target.independent_evidence_observed_at = source.independent_evidence_observed_at
    target.verification = source.verification
    target.verified_at = source.verified_at
    target.verification_history = source.verification_history

    with pytest.raises(InvalidTransitionError, match="transition"):
        repository.save_owned(target, expected_version=target.version)
    assert repository.get_owned(second["resolution_id"], OWNER).independent_evidence.account_readable is False
