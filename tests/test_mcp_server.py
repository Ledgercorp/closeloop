import asyncio

from fastapi.testclient import TestClient
from mcp import Client

from closeloop.http_app import create_app
from closeloop.lifecycle import ResolutionService
from closeloop.mcp_server import create_mcp_server


EXPECTED_TOOLS = {
    "start_resolution",
    "confirm_resolution_action",
    "get_resolution_status",
    "get_resolution_evidence",
    "list_open_resolutions",
}
FORBIDDEN_TOOLS = {"set_verdict", "mark_success", "force_pass"}
INTENT = "Cancel my subscription and make sure I will not be charged again."


def test_exact_mcp_surface_is_registered_and_callable():
    async def exercise_tools():
        server = create_mcp_server(ResolutionService())
        async with Client(server) as client:
            listed = await client.list_tools()
            tools_by_name = {tool.name: tool for tool in listed.tools}
            assert set(tools_by_name) == EXPECTED_TOOLS
            assert set(tools_by_name).isdisjoint(FORBIDDEN_TOOLS)

            start_schema = tools_by_name["start_resolution"].input_schema["properties"]
            confirm_input_schema = tools_by_name["confirm_resolution_action"].input_schema
            confirm_schema = confirm_input_schema["properties"]
            assert "verdict" not in start_schema
            assert set(confirm_schema) == {"resolution_id", "confirmed"}
            assert confirm_input_schema["additionalProperties"] is False

            started_result = await client.call_tool(
                "start_resolution",
                {"intent": INTENT, "provider_mode": "healthy"},
            )
            assert started_result.is_error is False
            started = started_result.structured_content
            resolution_id = started["resolution_id"]

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
                {"resolution_id": resolution_id, "confirmed": False},
            )
            assert unconfirmed_result.is_error is True
            unchanged_result = await client.call_tool(
                "get_resolution_status", {"resolution_id": resolution_id}
            )
            assert unchanged_result.structured_content["lifecycle_state"] == (
                "AWAITING_CONFIRMATION"
            )

            completed_result = await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": resolution_id, "confirmed": True},
            )
            assert completed_result.is_error is False
            assert completed_result.structured_content["verdict"] == "PASS"
            assert completed_result.structured_content["consumer_state"] == "Verified"

    asyncio.run(exercise_tools())


def test_mcp_rejects_direct_verdict_override_without_executing():
    async def attempt_override():
        service = ResolutionService()
        server = create_mcp_server(service)
        async with Client(server, raise_exceptions=False) as client:
            started_result = await client.call_tool(
                "start_resolution",
                {"intent": INTENT, "provider_mode": "false_success"},
            )
            resolution_id = started_result.structured_content["resolution_id"]

            override_result = await client.call_tool(
                "confirm_resolution_action",
                {
                    "resolution_id": resolution_id,
                    "confirmed": True,
                    "verdict": "PASS",
                    "success": True,
                    "status": "VERIFIED",
                },
            )
            assert override_result.is_error is True
            assert service.get_resolution_status(resolution_id)["lifecycle_state"] == (
                "AWAITING_CONFIRMATION"
            )

            completed_result = await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": resolution_id, "confirmed": True},
            )
            assert completed_result.structured_content["verdict"] == "FAIL"
            assert completed_result.structured_content["consumer_state"] == "Not completed"

    asyncio.run(attempt_override())


def test_streamable_http_negotiates_required_protocol_and_exposes_tools():
    app = create_app(ResolutionService())
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "closeloop-test", "version": "1.0"},
        },
    }

    with TestClient(app) as client:
        initialize_response = client.post("/mcp", headers=headers, json=initialize)
        assert initialize_response.status_code == 200
        assert initialize_response.json()["result"]["protocolVersion"] == "2025-11-25"

        protocol_headers = {**headers, "MCP-Protocol-Version": "2025-11-25"}
        list_response = client.post(
            "/mcp",
            headers=protocol_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert list_response.status_code == 200
        tool_names = {tool["name"] for tool in list_response.json()["result"]["tools"]}
        assert tool_names == EXPECTED_TOOLS
        assert tool_names.isdisjoint(FORBIDDEN_TOOLS)

        call_response = client.post(
            "/mcp",
            headers=protocol_headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "start_resolution",
                    "arguments": {"intent": INTENT},
                },
            },
        )
        assert call_response.status_code == 200
        result = call_response.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["lifecycle_state"] == "AWAITING_CONFIRMATION"


def test_streamable_http_rejects_untrusted_host_and_origin():
    app = create_app(ResolutionService())
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "closeloop-test", "version": "1.0"},
        },
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    with TestClient(app) as client:
        untrusted_host = client.post(
            "/mcp", headers={**headers, "Host": "attacker.example"}, json=request
        )
        untrusted_origin = client.post(
            "/mcp", headers={**headers, "Origin": "https://attacker.example"}, json=request
        )

    assert untrusted_host.status_code == 421
    assert untrusted_origin.status_code == 403


def test_fastapi_vercel_baseline_remains_valid():
    app = create_app(ResolutionService())

    with TestClient(app) as client:
        root = client.get("/")
        health = client.get("/health")

    assert root.status_code == 200
    assert root.json()["status"] == "ok"
    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
