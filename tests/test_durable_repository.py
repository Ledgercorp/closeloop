import pytest
from sqlalchemy.dialects import postgresql

from closeloop.lifecycle import (
    ConcurrentResolutionUpdateError,
    InvalidTransitionError,
    LifecycleState,
    ResolutionNotFoundError,
    ResolutionService,
    ResolutionStorageUnavailableError,
    StateTransition,
    TerminalOutcomeImmutableError,
)
from closeloop.repository import (
    SqlResolutionRepository,
    _owned_transition_update,
    create_repository_from_environment,
)
from tests.confirmation_support import trusted_confirmation, verified_test_confirmation


OWNER_A = "owner-a"
OWNER_B = "owner-b"
INTENT = "Cancel my subscription and make sure I will not be charged again."


def repository_for(database_path):
    return SqlResolutionRepository(f"sqlite+pysqlite:///{database_path}")


def test_transition_predicate_compiles_for_postgresql_json_storage():
    statement = _owned_transition_update(
        resolution_id="resolution-1",
        owner_id=OWNER_A,
        expected_version=1,
        next_state=LifecycleState.EXECUTING,
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "state_history =" not in compiled
    assert "version =" in compiled
    assert "state IN" in compiled


def test_resolution_survives_repository_and_service_reinstantiation(tmp_path):
    database_path = tmp_path / "resolutions.db"
    first_instance = ResolutionService(repository_for(database_path))
    started = first_instance.start_resolution(OWNER_A, INTENT, "healthy")

    second_instance = ResolutionService(repository_for(database_path))
    restarted_status = second_instance.get_resolution_status(OWNER_A, started["resolution_id"])
    assert restarted_status == started

    terminal = second_instance.confirm_resolution_action(
        OWNER_A,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER_A),
    )
    third_instance = ResolutionService(repository_for(database_path))
    persisted_status = third_instance.get_resolution_status(OWNER_A, started["resolution_id"])
    persisted_evidence = third_instance.get_resolution_evidence(OWNER_A, started["resolution_id"])

    assert persisted_status == terminal
    assert persisted_status["verdict"] == "PASS"
    assert persisted_status["consumer_state"] == "Verified"
    assert persisted_status["confirmed_at"]
    assert persisted_evidence["execution_claim"]["request_id"]
    assert persisted_evidence["independent_read_back"]["auto_renew"] is False
    assert persisted_evidence["verification"]["verdict"] == "PASS"
    assert [item["state"] for item in persisted_evidence["state_history"]] == [
        "REQUESTED",
        "AWAITING_CONFIRMATION",
        "EXECUTING",
        "VERIFYING",
        "VERIFIED",
    ]


@pytest.mark.parametrize(
    ("provider_mode", "verdict", "consumer_state"),
    [
        ("false_success", "FAIL", "Not completed"),
        ("evidence_outage", "INCONCLUSIVE", "Awaiting proof"),
    ],
)
def test_non_pass_outcomes_and_evidence_survive_restart(
    tmp_path, provider_mode, verdict, consumer_state
):
    database_path = tmp_path / "resolutions.db"
    service = ResolutionService(repository_for(database_path))
    started = service.start_resolution(OWNER_A, INTENT, provider_mode)
    service.confirm_resolution_action(
        OWNER_A,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER_A),
    )

    restarted = ResolutionService(repository_for(database_path))
    status = restarted.get_resolution_status(OWNER_A, started["resolution_id"])
    evidence = restarted.get_resolution_evidence(OWNER_A, started["resolution_id"])

    assert status["verdict"] == verdict
    assert status["consumer_state"] == consumer_state
    assert evidence["verification"]["verdict"] == verdict
    assert evidence["execution_claim"]["provider_reported_success"] is True


def test_cross_principal_read_confirm_evidence_and_list_are_rejected(tmp_path):
    service = ResolutionService(repository_for(tmp_path / "resolutions.db"))
    started = service.start_resolution(OWNER_A, INTENT)
    resolution_id = started["resolution_id"]

    with pytest.raises(ResolutionNotFoundError, match="unknown resolution"):
        service.get_resolution_status(OWNER_B, resolution_id)
    with pytest.raises(ResolutionNotFoundError, match="unknown resolution"):
        service.get_resolution_evidence(OWNER_B, resolution_id)
    with pytest.raises(ResolutionNotFoundError, match="unknown resolution"):
        service.confirm_resolution_action(OWNER_B, resolution_id, confirmed=True)
    assert service.list_open_resolutions(OWNER_B) == []

    assert service.get_resolution_status(OWNER_A, resolution_id) == started
    assert service.list_open_resolutions(OWNER_A)[0]["resolution_id"] == resolution_id


def test_terminal_outcome_is_immutable_at_repository_boundary(tmp_path):
    repository = repository_for(tmp_path / "resolutions.db")
    service = ResolutionService(repository)
    started = service.start_resolution(OWNER_A, INTENT)
    service.confirm_resolution_action(
        OWNER_A,
        started["resolution_id"],
        confirmed=True,
        confirmation_attestation=trusted_confirmation(started, OWNER_A),
    )

    terminal_record = repository.get_owned(started["resolution_id"], OWNER_A)
    original_version = terminal_record.version
    terminal_record.state = LifecycleState.AWAITING_CONFIRMATION

    with pytest.raises(TerminalOutcomeImmutableError, match="terminal outcome is immutable"):
        repository.save_owned(terminal_record, expected_version=original_version)

    persisted = ResolutionService(repository_for(tmp_path / "resolutions.db"))
    assert persisted.get_resolution_status(OWNER_A, started["resolution_id"])["verdict"] == "PASS"


def test_optimistic_version_rejects_stale_cross_instance_update(tmp_path):
    database_path = tmp_path / "resolutions.db"
    repository_a = repository_for(database_path)
    repository_b = repository_for(database_path)
    service = ResolutionService(repository_a)
    started = service.start_resolution(OWNER_A, INTENT)

    record_a = repository_a.get_owned(started["resolution_id"], OWNER_A)
    record_b = repository_b.get_owned(started["resolution_id"], OWNER_A)
    record_a.confirmed_at = record_a.updated_at
    record_a.state = LifecycleState.EXECUTING
    record_a.state_history.append(
        StateTransition(
            LifecycleState.EXECUTING,
            record_a.updated_at,
            confirmation_attestation=verified_test_confirmation(
                started, OWNER_A, now=record_a.updated_at
            ),
        )
    )
    repository_a.save_owned(record_a, expected_version=record_a.version)

    record_b.state = LifecycleState.EXECUTING
    with pytest.raises(ConcurrentResolutionUpdateError, match="another instance"):
        repository_b.save_owned(record_b, expected_version=record_b.version)


def test_repository_rejects_illegal_lifecycle_jump(tmp_path):
    repository = repository_for(tmp_path / "resolutions.db")
    service = ResolutionService(repository)
    started = service.start_resolution(OWNER_A, INTENT)
    record = repository.get_owned(started["resolution_id"], OWNER_A)
    record.state = LifecycleState.VERIFYING

    with pytest.raises(InvalidTransitionError, match="is not allowed"):
        repository.save_owned(record, expected_version=record.version)

    persisted = repository.get_owned(started["resolution_id"], OWNER_A)
    assert persisted.state is LifecycleState.AWAITING_CONFIRMATION


def test_repository_rejects_execution_without_persisted_confirmation(tmp_path):
    repository = repository_for(tmp_path / "resolutions.db")
    service = ResolutionService(repository)
    started = service.start_resolution(OWNER_A, INTENT)
    record = repository.get_owned(started["resolution_id"], OWNER_A)
    record.state = LifecycleState.EXECUTING
    record.state_history.append(StateTransition(LifecycleState.EXECUTING, record.updated_at))

    with pytest.raises(InvalidTransitionError, match="explicit confirmation"):
        repository.save_owned(record, expected_version=record.version)

    persisted = repository.get_owned(started["resolution_id"], OWNER_A)
    assert persisted.state is LifecycleState.AWAITING_CONFIRMATION


def test_serverless_environment_without_database_fails_closed(monkeypatch):
    for name in ("CLOSELOOP_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERCEL", "1")

    repository = create_repository_from_environment()
    with pytest.raises(ResolutionStorageUnavailableError, match="required"):
        repository.list_open_owned(OWNER_A, 50)
