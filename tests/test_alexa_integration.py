import asyncio
import json

from mcp import Client

from closeloop.mcp_app import PROOF_CARD_HTML, PROOF_CARD_URI
from closeloop.mcp_server import create_mcp_server
from closeloop.lifecycle import ResolutionService
from closeloop.repository import SqlResolutionRepository


EXPECTED_TOOLS = {
    "start_resolution",
    "confirm_resolution_action",
    "get_resolution_status",
    "get_resolution_evidence",
    "list_open_resolutions",
}
UI_TOOLS = EXPECTED_TOOLS - {"list_open_resolutions"}
FORBIDDEN_TOOLS = {"set_verdict", "mark_success", "force_pass"}
EXPECTED_OUTCOMES = {
    "healthy": ("PASS", "Verified"),
    "false_success": ("FAIL", "Not completed"),
    "evidence_outage": ("INCONCLUSIVE", "Awaiting proof"),
}
INTENT = "Cancel my subscription and make sure I will not be charged again."


def make_service(tmp_path):
    repository = SqlResolutionRepository(f"sqlite+pysqlite:///{tmp_path / 'alexa.db'}")
    return ResolutionService(repository)


def result_text(result) -> str:
    return "\n".join(item.text for item in result.content if hasattr(item, "text"))


def test_alexa_tool_discovery_contracts_are_closed_and_conversation_ready(tmp_path):
    async def inspect_contracts():
        server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: "owner")
        async with Client(server) as client:
            listed = await client.list_tools()
            tools = {tool.name: tool for tool in listed.tools}

            assert set(tools) == EXPECTED_TOOLS
            assert set(tools).isdisjoint(FORBIDDEN_TOOLS)
            for name, tool in tools.items():
                assert len(tool.description.strip()) >= 80
                assert tool.input_schema["additionalProperties"] is False
                assert tool.output_schema["additionalProperties"] is False
                for property_schema in tool.input_schema["properties"].values():
                    assert property_schema["description"]
                if name in UI_TOOLS:
                    assert tool.meta["ui"] == {
                        "resourceUri": PROOF_CARD_URI,
                        "visibility": ["model", "app"],
                    }
                else:
                    assert tool.meta is None

            assert tools["start_resolution"].input_schema["properties"]["intent"][
                "minLength"
            ] == 1
            resolution_schema = tools["get_resolution_status"].input_schema["properties"][
                "resolution_id"
            ]
            assert resolution_schema["minLength"] == 1
            limit_schema = tools["list_open_resolutions"].input_schema["properties"]["limit"]
            assert limit_schema["minimum"] == 1
            assert limit_schema["maximum"] == 100

            status_fields = set(
                tools["get_resolution_status"].output_schema["properties"]
            )
            assert {
                "task",
                "execution_status",
                "verification_status",
                "consumer_state",
                "evidence_summary",
                "recommended_next_step",
            } <= status_fields

    asyncio.run(inspect_contracts())


def test_alexa_responses_preserve_all_verdicts_with_structured_and_text_fallbacks(tmp_path):
    async def exercise_outcomes():
        server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: "owner")
        async with Client(server, raise_exceptions=False) as client:
            for provider_mode, (verdict, consumer_state) in EXPECTED_OUTCOMES.items():
                started = await client.call_tool(
                    "start_resolution",
                    {"intent": INTENT, "provider_mode": provider_mode},
                )
                started_data = started.structured_content
                assert started_data["task"] == INTENT
                assert started_data["execution_status"] == "not_started"
                assert started_data["verification_status"] == "not_started"
                assert started_data["consumer_state"] is None
                assert started_data["confirmation_required"] is True
                assert INTENT in result_text(started)

                completed = await client.call_tool(
                    "confirm_resolution_action",
                    {
                        "resolution_id": started_data["resolution_id"],
                        "confirmed": True,
                    },
                )
                data = completed.structured_content
                assert completed.is_error is False
                assert data["verdict"] == verdict
                assert data["verification_status"] == verdict
                assert data["consumer_state"] == consumer_state
                assert data["execution_status"] == "completed"
                assert data["evidence_summary"]
                assert data["recommended_next_step"]
                fallback = result_text(completed)
                assert consumer_state in fallback
                assert data["evidence_summary"] in fallback

    asyncio.run(exercise_outcomes())


def test_alexa_tool_errors_are_rejected_with_useful_nonempty_fallbacks(tmp_path):
    async def exercise_errors():
        server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: "owner")
        async with Client(server, raise_exceptions=False) as client:
            for name, arguments, expected_text in (
                ("list_open_resolutions", {"limit": 0}, "limit"),
                (
                    "get_resolution_status",
                    {"resolution_id": "missing"},
                    "Resolution is unavailable",
                ),
                ("get_resolution_evidence", {"resolution_id": ""}, "resolution_id"),
            ):
                result = await client.call_tool(name, arguments)
                assert result.is_error is True
                assert expected_text in result_text(result)

            started = await client.call_tool("start_resolution", {"intent": INTENT})
            resolution_id = started.structured_content["resolution_id"]
            unconfirmed = await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": resolution_id, "confirmed": False},
            )
            assert unconfirmed.is_error is True
            assert "explicit confirmation is required" in result_text(unconfirmed)

            completed = await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": resolution_id, "confirmed": True},
            )
            assert completed.is_error is False
            repeated = await client.call_tool(
                "confirm_resolution_action",
                {"resolution_id": resolution_id, "confirmed": True},
            )
            assert repeated.is_error is True
            assert "cannot be advanced from its current lifecycle state" in result_text(repeated)

    asyncio.run(exercise_errors())


def test_mcp_apps_proof_card_resource_and_tool_linkage(tmp_path):
    async def inspect_resource():
        server = create_mcp_server(make_service(tmp_path), principal_resolver=lambda: "owner")
        async with Client(server) as client:
            listed = await client.list_resources()
            resources = {str(resource.uri): resource for resource in listed.resources}
            assert set(resources) == {PROOF_CARD_URI}
            card = resources[PROOF_CARD_URI]
            assert card.mime_type == "text/html;profile=mcp-app"
            assert card.meta["ui"]["csp"]["resourceDomains"] == [
                "https://cdn.jsdelivr.net"
            ]

            read = await client.read_resource(PROOF_CARD_URI)
            assert len(read.contents) == 1
            content = read.contents[0]
            assert content.mime_type == "text/html;profile=mcp-app"
            assert content.text == PROOF_CARD_HTML

    asyncio.run(inspect_resource())

    for label in ("Verified", "Not completed", "Awaiting proof"):
        assert label in PROOF_CARD_HTML
    assert "result.structuredContent" in PROOF_CARD_HTML
    assert "@modelcontextprotocol/ext-apps@1.7.5" in PROOF_CARD_HTML
    assert "callTool" not in PROOF_CARD_HTML
    json.dumps({"uri": PROOF_CARD_URI, "html": PROOF_CARD_HTML})
