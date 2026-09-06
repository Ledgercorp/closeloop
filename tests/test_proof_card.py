import asyncio
from pathlib import Path
from runpy import run_path

import pytest
from mcp import Client

from closeloop.lifecycle import (
    LifecycleState,
    ResolutionService,
    TerminalOutcomeImmutableError,
)
from closeloop.mcp_app import (
    PROOF_CARD_HTML,
    PROOF_CARD_OUTCOME_RULES,
    PROOF_CARD_URI,
)
from closeloop.mcp_server import create_mcp_server
from closeloop.repository import SqlResolutionRepository


_host_html = run_path(
    Path(__file__).parent.parent / "scripts" / "build_proof_card_validation.py"
)["_host_html"]


OWNER_A = "owner-a"
OWNER_B = "owner-b"
INTENT = "Cancel my subscription and make sure I will not be charged again."
EXPECTED = {
    "healthy": ("PASS", "Verified", "VERIFIED"),
    "false_success": ("FAIL", "Not completed", "NOT_COMPLETED"),
    "evidence_outage": ("INCONCLUSIVE", "Awaiting proof", "AWAITING_PROOF"),
}


def make_service(tmp_path, name="proof-card.db"):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / name}")
    return ResolutionService(repository)


async def completed_mcp_results(tmp_path, provider_mode):
    server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: OWNER_A)
    async with Client(server, raise_exceptions=False) as client:
        started = await client.call_tool(
            "start_resolution",
            {"intent": INTENT, "provider_mode": provider_mode},
        )
        completed = await client.call_tool(
            "confirm_resolution_action",
            {
                "resolution_id": started.structured_content["resolution_id"],
                "confirmed": True,
            },
        )
        evidence = await client.call_tool(
            "get_resolution_evidence",
            {"resolution_id": started.structured_content["resolution_id"]},
        )
        return started.structured_content, completed.structured_content, evidence.structured_content


@pytest.mark.parametrize("provider_mode", EXPECTED)
def test_terminal_status_shape_matches_only_its_canonical_outcome(tmp_path, provider_mode):
    _, status, _ = asyncio.run(completed_mcp_results(tmp_path, provider_mode))
    verdict, consumer_state, lifecycle_state = EXPECTED[provider_mode]
    rule = PROOF_CARD_OUTCOME_RULES[verdict]

    assert status["verdict"] == verdict
    assert status["consumer_state"] == consumer_state == rule["consumerState"]
    assert status["lifecycle_state"] == lifecycle_state == rule["lifecycleState"]
    assert status["verification_status"] == verdict
    assert status["execution_status"] == "completed"
    assert status["is_terminal"] is True
    for other_verdict, other_rule in PROOF_CARD_OUTCOME_RULES.items():
        if other_verdict != verdict:
            assert status["consumer_state"] != other_rule["consumerState"]


@pytest.mark.parametrize("provider_mode", EXPECTED)
def test_terminal_evidence_shape_preserves_distinct_provenance(tmp_path, provider_mode):
    _, _, evidence = asyncio.run(completed_mcp_results(tmp_path, provider_mode))
    verdict, consumer_state, lifecycle_state = EXPECTED[provider_mode]

    assert evidence["lifecycle_state"] == lifecycle_state
    assert evidence["verification_status"] == verdict
    assert evidence["consumer_state"] == consumer_state
    assert evidence["execution_claim"]["evidence_type"] == "execution_claim"
    assert evidence["execution_claim"]["source"] == "demo_provider.cancel_subscription"
    assert evidence["execution_claim"]["request_id"]
    assert evidence["execution_claim"]["observed_at"]
    assert evidence["independent_read_back"]["evidence_type"] == "independent_read_back"
    assert evidence["independent_read_back"]["source"] == (
        "demo_provider.read_cancellation_evidence"
    )
    assert evidence["independent_read_back"]["observed_at"]
    assert evidence["verification"]["verifier"] == "closeloop.verify_cancellation/v1"
    assert evidence["verification"]["verdict"] == verdict
    assert evidence["verification"]["consumer_state"] == consumer_state
    assert evidence["verification"]["evaluated_at"]


def test_confirmation_required_result_explicitly_precedes_execution(tmp_path):
    async def start_only():
        server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: OWNER_A)
        async with Client(server) as client:
            return (
                await client.call_tool(
                    "start_resolution",
                    {"intent": INTENT, "provider_mode": "healthy"},
                )
            ).structured_content

    started = asyncio.run(start_only())
    assert started["lifecycle_state"] == "AWAITING_CONFIRMATION"
    assert started["confirmation_required"] is True
    assert started["execution_status"] == "not_started"
    assert started["verification_status"] == "not_started"
    assert started["consumer_state"] is None
    assert started["verdict"] is None
    assert "No execution or verification evidence exists" in started["evidence_summary"]
    assert "Confirmation required — no action has run" in PROOF_CARD_HTML


def test_card_is_semantic_responsive_keyboard_accessible_and_non_color_only():
    assert '<main id="proof-card"' in PROOF_CARD_HTML
    assert 'role="status" aria-live="polite" aria-atomic="true"' in PROOF_CARD_HTML
    assert PROOF_CARD_HTML.count('aria-live="polite"') == 1
    assert "<details" in PROOF_CARD_HTML and "<summary" in PROOF_CARD_HTML
    assert "View evidence and provenance" in PROOF_CARD_HTML
    assert "Independent check" in PROOF_CARD_HTML
    assert "Independently verified</li>" not in PROOF_CARD_HTML
    assert "summary:focus-visible" in PROOF_CARD_HTML
    assert "@media (max-width: 560px)" in PROOF_CARD_HTML
    assert "@media (prefers-color-scheme: dark)" in PROOF_CARD_HTML
    assert "@media (forced-colors: active)" in PROOF_CARD_HTML
    for rule in PROOF_CARD_OUTCOME_RULES.values():
        assert rule["consumerState"] in PROOF_CARD_HTML
        assert rule["symbol"] in PROOF_CARD_HTML


def test_card_has_no_mutation_storage_or_unescaped_render_path():
    forbidden = (
        "callTool",
        "callServerTool",
        "innerHTML",
        "outerHTML",
        "localStorage",
        "sessionStorage",
        "URLSearchParams",
        "XMLHttpRequest",
        "fetch(",
        "<form",
        "<button",
        "<input",
        "contenteditable",
    )
    for value in forbidden:
        assert value not in PROOF_CARD_HTML
    assert "textContent" in PROOF_CARD_HTML
    assert "render(result.structuredContent)" in PROOF_CARD_HTML
    assert "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/ext-apps@1.7.5/+esm" in (
        PROOF_CARD_HTML
    )


def test_presentation_contract_fails_closed_instead_of_trusting_labels_directly():
    required_checks = (
        "consistentValue(data.verdict, nested?.verdict)",
        "consistentValue(data.consumer_state, nested?.consumer_state)",
        "lifecycle !== rule.lifecycleState",
        "consumerState !== rule.consumerState",
        'verification !== verdict',
        'execution !== "completed"',
        "confirmationRequired === true",
        'typeof data.is_terminal !== "boolean"',
        'typeof data.confirmation_required !== "boolean"',
        "isTerminal !== true || confirmationRequired !== false",
        'outcome: "Proof unavailable"',
        'setText("outcome-title", view.outcome)',
    )
    for check in required_checks:
        assert check in PROOF_CARD_HTML
    assert 'setText("outcome-title", payload.consumer_state)' not in PROOF_CARD_HTML
    assert "view.valid ? payload : {}" in PROOF_CARD_HTML


def test_cross_principal_error_cannot_supply_owner_data_to_card(tmp_path):
    async def attempt_cross_owner_read():
        current_owner = {"value": OWNER_A}
        server = create_mcp_server(
            make_service(tmp_path), principal_resolver=lambda: current_owner["value"]
        )
        async with Client(server, raise_exceptions=False) as client:
            started = await client.call_tool("start_resolution", {"intent": INTENT})
            resolution_id = started.structured_content["resolution_id"]
            current_owner["value"] = OWNER_B
            rejected = await client.call_tool(
                "get_resolution_evidence", {"resolution_id": resolution_id}
            )
            return resolution_id, rejected

    resolution_id, rejected = asyncio.run(attempt_cross_owner_read())
    fallback = "\n".join(item.text for item in rejected.content if hasattr(item, "text"))
    assert rejected.is_error is True
    assert "Resolution is unavailable" in fallback
    assert resolution_id not in fallback
    assert INTENT not in fallback
    assert resolution_id not in PROOF_CARD_HTML
    assert INTENT not in PROOF_CARD_HTML


def test_terminal_repository_state_remains_immutable_and_card_remains_read_only(tmp_path):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'immutable.db'}")
    service = ResolutionService(repository)
    started = service.start_resolution(OWNER_A, INTENT)
    service.confirm_resolution_action(OWNER_A, started["resolution_id"], confirmed=True)
    terminal = repository.get_owned(started["resolution_id"], OWNER_A)
    version = terminal.version
    terminal.state = LifecycleState.AWAITING_CONFIRMATION

    with pytest.raises(TerminalOutcomeImmutableError):
        repository.save_owned(terminal, expected_version=version)
    assert repository.get_owned(started["resolution_id"], OWNER_A).version == version
    assert "callTool" not in PROOF_CARD_HTML


def test_failure_and_cancelled_results_render_neutral_copy():
    assert 'app.ontoolcancelled = () => render(null)' in PROOF_CARD_HTML
    assert 'app.onerror = () => render(null)' in PROOF_CARD_HTML
    assert "CloseLoop did not accept this data as a trustworthy completion result." in (
        PROOF_CARD_HTML
    )
    assert "No terminal claim is shown because the result contract is inconsistent." in (
        PROOF_CARD_HTML
    )


def test_mcp_app_resource_identity_and_only_network_domain_remain_stable():
    assert PROOF_CARD_URI == "ui://closeloop/proof-card.html"
    assert PROOF_CARD_HTML.count("https://") == 1


def test_validation_host_script_embedding_cannot_be_terminated_by_card_or_payload():
    host = _host_html(
        "hostile",
        {"intent": '</script><script>globalThis.injected = true</script>'},
    )

    assert host.count("</script>") == 1
    assert "\\u003c/script>" in host
    assert "globalThis.injected" in host
    assert '<script>globalThis.injected = true</script>' not in host
