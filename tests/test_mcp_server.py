import asyncio
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.auth.settings import AuthSettings

from closeloop.auth import HmacJwtTokenVerifier, REQUIRED_SCOPE, principal_key
from closeloop.http_app import create_app
from closeloop.lifecycle import ResolutionService
from closeloop.mcp_server import create_mcp_server
from closeloop.repository import SqlResolutionRepository
from tests.confirmation_support import trusted_confirmation


EXPECTED_TOOLS = {
    "start_resolution",
    "confirm_resolution_action",
    "get_resolution_status",
    "get_resolution_evidence",
    "list_open_resolutions",
}
FORBIDDEN_TOOLS = {"set_verdict", "mark_success", "force_pass"}
INTENT = "Cancel my subscription and make sure I will not be charged again."
ISSUER = "https://issuer.closeloop.test"
AUDIENCE = "https://closeloop.test/mcp"
SECRET = "closeloop-test-secret-that-is-at-least-thirty-two-bytes-long"
OWNER_A = principal_key(ISSUER, "principal-a")


def make_service(tmp_path):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'resolutions.db'}")
    return ResolutionService(repository)


def make_auth():
    settings = AuthSettings(
        issuer_url=ISSUER,
        resource_server_url=AUDIENCE,
        required_scopes=[REQUIRED_SCOPE],
    )
    return settings, HmacJwtTokenVerifier(SECRET, ISSUER, AUDIENCE)


def bearer_token(subject: str, scope: str = REQUIRED_SCOPE) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": subject,
            "iat": now,
            "exp": now + 300,
            "scope": scope,
            "client_id": "closeloop-tests",
        },
        SECRET,
        algorithm="HS256",
    )


def protocol_headers(
    subject: str | None = None,
    scope: str = REQUIRED_SCOPE,
    protocol_version: str = "2025-11-25",
):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": protocol_version,
    }
    if subject:
        headers["Authorization"] = f"Bearer {bearer_token(subject, scope)}"
    return headers


def call_tool(client, subject, request_id, name, arguments):
    return client.post(
        "/mcp",
        headers=protocol_headers(subject),
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def test_exact_mcp_surface_is_registered_and_callable(tmp_path):
    async def exercise_tools():
        server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: OWNER_A)
        async with Client(server) as client:
            listed = await client.list_tools()
            tools_by_name = {tool.name: tool for tool in listed.tools}
            assert set(tools_by_name) == EXPECTED_TOOLS
            assert set(tools_by_name).isdisjoint(FORBIDDEN_TOOLS)

            start_schema = tools_by_name["start_resolution"].input_schema["properties"]
            confirm_input_schema = tools_by_name["confirm_resolution_action"].input_schema
            assert "principal_id" not in start_schema
            assert "verdict" not in start_schema
            assert set(confirm_input_schema["properties"]) == {
                "resolution_id",
                "confirmed",
                "confirmation_attestation",
            }
            assert set(confirm_input_schema["required"]) == {
                "resolution_id",
                "confirmed",
                "confirmation_attestation",
            }
            assert confirm_input_schema["properties"]["confirmation_attestation"][
                "maxLength"
            ] == 4096
            assert confirm_input_schema["additionalProperties"] is False

            started_result = await client.call_tool(
                "start_resolution", {"intent": INTENT, "provider_mode": "healthy"}
            )
            assert started_result.is_error is False
            resolution_id = started_result.structured_content["resolution_id"]
            assert len(started_result.structured_content["action_digest"]) == 64

            status_result = await client.call_tool(
                "get_resolution_status", {"resolution_id": resolution_id}
            )
            evidence_result = await client.call_tool(
                "get_resolution_evidence", {"resolution_id": resolution_id}
            )
            list_result = await client.call_tool("list_open_resolutions", {})
            assert status_result.structured_content["lifecycle_state"] == "AWAITING_CONFIRMATION"
            assert evidence_result.structured_content["execution_claim"] is None
            assert list_result.structured_content["resolutions"][0]["resolution_id"] == resolution_id

            unconfirmed_result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": False,
                    "confirmation_attestation": trusted_confirmation(
                        started_result.structured_content, OWNER_A
                    ),
                },
            )
            assert unconfirmed_result.is_error is True

            completed_result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": trusted_confirmation(
                        started_result.structured_content, OWNER_A
                    ),
                },
            )
            assert completed_result.structured_content["verdict"] == "PASS"
            assert completed_result.structured_content["consumer_state"] == "Verified"

    asyncio.run(exercise_tools())


def test_mcp_rejects_direct_verdict_override_without_executing(tmp_path):
    async def attempt_override():
        service = make_service(tmp_path)
        server = create_mcp_server(service, principal_resolver=lambda: OWNER_A)
        async with Client(server, raise_exceptions=False) as client:
            started_result = await client.call_tool(
                "start_resolution", {"intent": INTENT, "provider_mode": "false_success"}
            )
            resolution_id = started_result.structured_content["resolution_id"]
            override_result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": trusted_confirmation(
                        started_result.structured_content, OWNER_A
                    ),
                    "verdict": "PASS",
                    "success": True,
                    "status": "VERIFIED",
                },
            )
            assert override_result.is_error is True
            assert service.get_resolution_status(OWNER_A, resolution_id)["lifecycle_state"] == (
                "AWAITING_CONFIRMATION"
            )
            completed_result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": trusted_confirmation(
                        started_result.structured_content, OWNER_A
                    ),
                },
            )
            assert completed_result.structured_content["verdict"] == "FAIL"

    asyncio.run(attempt_override())


@pytest.mark.parametrize("protocol_version", ["2025-11-25", "2025-03-26"])
def test_streamable_http_requires_auth_and_negotiates_protocol(tmp_path, protocol_version):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "closeloop-test", "version": "1.0"},
        },
    }
    with TestClient(app) as client:
        unauthorized = client.post(
            "/mcp",
            headers=protocol_headers(protocol_version=protocol_version),
            json=initialize,
        )
        assert unauthorized.status_code == 401
        assert "www-authenticate" not in unauthorized.headers

        invalid_token = client.post(
            "/mcp",
            headers={
                **protocol_headers(protocol_version=protocol_version),
                "Authorization": "Bearer invalid-token",
            },
            json=initialize,
        )
        assert invalid_token.status_code == 401
        assert "www-authenticate" not in invalid_token.headers

        insufficient_scope = client.post(
            "/mcp",
            headers=protocol_headers(
                "principal-a",
                scope="unrelated:scope",
                protocol_version=protocol_version,
            ),
            json=initialize,
        )
        assert insufficient_scope.status_code == 403
        assert "insufficient_scope" in insufficient_scope.headers["www-authenticate"]

        response = client.post(
            "/mcp",
            headers=protocol_headers("principal-a", protocol_version=protocol_version),
            json=initialize,
        )
        assert response.status_code == 200
        assert response.json()["result"]["protocolVersion"] == protocol_version

        list_response = client.post(
            "/mcp",
            headers=protocol_headers("principal-a", protocol_version=protocol_version),
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        tool_names = {tool["name"] for tool in list_response.json()["result"]["tools"]}
        assert tool_names == EXPECTED_TOOLS
        assert tool_names.isdisjoint(FORBIDDEN_TOOLS)


def test_mcp_authorization_isolates_principals(tmp_path):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    with TestClient(app) as client:
        started_response = call_tool(
            client, "principal-a", 1, "start_resolution", {"intent": INTENT}
        )
        resolution_id = started_response.json()["result"]["structuredContent"]["resolution_id"]
        started_data = started_response.json()["result"]["structuredContent"]
        attestation = trusted_confirmation(started_data, OWNER_A)

        unauthorized_text = None
        for request_id, tool_name, arguments in (
            (2, "get_resolution_status", {"resolution_id": resolution_id}),
            (3, "get_resolution_evidence", {"resolution_id": resolution_id}),
            (
                4,
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "confirmation_attestation": attestation,
                },
            ),
        ):
            rejected = call_tool(client, "principal-b", request_id, tool_name, arguments)
            assert rejected.status_code == 200
            assert rejected.json()["result"]["isError"] is True
            content_text = rejected.json()["result"]["content"][0]["text"]
            assert "Resolution is unavailable" in content_text
            unauthorized_text = unauthorized_text or content_text

        missing = call_tool(
            client,
            "principal-b",
            8,
            "get_resolution_status",
            {"resolution_id": "missing"},
        )
        assert missing.json()["result"]["content"][0]["text"] == unauthorized_text

        other_list = call_tool(client, "principal-b", 5, "list_open_resolutions", {})
        assert other_list.json()["result"]["structuredContent"]["resolutions"] == []

        owner_status = call_tool(
            client, "principal-a", 6, "get_resolution_status", {"resolution_id": resolution_id}
        )
        assert owner_status.json()["result"]["isError"] is False
        owner_confirm = call_tool(
            client,
            "principal-a",
            7,
            "confirm_resolution_action",
            {
                "resolution_id": resolution_id,
                "confirmed": True,
                "confirmation_attestation": attestation,
            },
        )
        assert owner_confirm.json()["result"]["structuredContent"]["verdict"] == "PASS"


def test_streamable_http_rejects_untrusted_host_and_origin(tmp_path):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    with TestClient(app) as client:
        untrusted_host = client.post(
            "/mcp",
            headers={**protocol_headers("principal-a"), "Host": "attacker.example"},
            json=request,
        )
        untrusted_origin = client.post(
            "/mcp",
            headers={
                **protocol_headers("principal-a"),
                "Origin": "https://attacker.example",
            },
            json=request,
        )
    assert untrusted_host.status_code == 421
    assert untrusted_origin.status_code == 403


def test_fastapi_vercel_baseline_remains_valid(tmp_path):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    with TestClient(app) as client:
        root = client.get("/")
        health = client.get("/health")
    assert root.status_code == 200
    assert root.json()["status"] == "ok"
    assert root.json()["demo"] == "/demo/"
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}


def test_public_demo_is_read_only_labeled_and_secret_free(tmp_path):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    with TestClient(app) as client:
        index = client.get("/demo/")
        healthy = client.get("/demo/healthy.html")
        manifest = client.get("/demo/demo-results.json")
        unauthorized_mcp = client.post(
            "/mcp",
            headers=protocol_headers(),
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert index.status_code == 200
    assert "Public deterministic demonstration" in index.text
    assert "local-validation-only-confirmation-secret" not in index.text
    assert healthy.status_code == 200
    assert "CloseLoop proof card" in healthy.text
    assert manifest.status_code == 200
    assert manifest.json()["live_alexa_plus"] is False
    assert manifest.json()["live_aws"] is False
    assert unauthorized_mcp.status_code == 401


def test_alexa_root_and_sdk_protected_resource_metadata_are_available(tmp_path):
    settings, verifier = make_auth()
    app = create_app(make_service(tmp_path), settings, verifier)
    with TestClient(app) as client:
        alexa_metadata = client.get("/.well-known/oauth-protected-resource")
        sdk_metadata = client.get("/.well-known/oauth-protected-resource/mcp")

    assert alexa_metadata.status_code == 200
    assert alexa_metadata.json() == {
        "resource": AUDIENCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [REQUIRED_SCOPE],
        "bearer_methods_supported": ["header"],
    }
    assert sdk_metadata.status_code == 200
    assert sdk_metadata.json()["resource"] == AUDIENCE
    assert sdk_metadata.json()["authorization_servers"] == [ISSUER]
