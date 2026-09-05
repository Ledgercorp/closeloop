from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.tools import Tool
from mcp.types import ToolAnnotations

from .lifecycle import ResolutionService


ProviderMode = Literal["healthy", "false_success", "evidence_outage"]


def _strict_tool(function: Callable[..., object], annotations: ToolAnnotations) -> Tool:
    """Register a tool whose wire schema rejects all undeclared arguments."""

    tool = Tool.from_function(function, annotations=annotations)
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config["extra"] = "forbid"
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)
    return tool


def create_mcp_server(service: ResolutionService | None = None) -> MCPServer:
    resolution_service = service or ResolutionService()

    def start_resolution(
        intent: str,
        provider_mode: ProviderMode = "healthy",
    ) -> dict[str, object]:
        """Create a subscription-cancellation resolution without executing it.

        ``provider_mode`` selects a clearly labeled first-party demo simulation.
        The returned resolution always requires explicit confirmation.
        """

        return resolution_service.start_resolution(intent, provider_mode)

    def confirm_resolution_action(
        resolution_id: str,
        confirmed: bool,
    ) -> dict[str, object]:
        """Execute only after explicit confirmation, then independently verify."""

        return resolution_service.confirm_resolution_action(resolution_id, confirmed)

    def get_resolution_status(resolution_id: str) -> dict[str, object]:
        """Read lifecycle and consumer-facing status without changing it."""

        return resolution_service.get_resolution_status(resolution_id)

    def get_resolution_evidence(resolution_id: str) -> dict[str, object]:
        """Read separate execution, read-back, and verifier evidence records."""

        return resolution_service.get_resolution_evidence(resolution_id)

    def list_open_resolutions(limit: int = 50) -> dict[str, list[dict[str, object]]]:
        """List non-terminal resolutions without advancing their lifecycle."""

        return {"resolutions": resolution_service.list_open_resolutions(limit)}

    tools = [
        _strict_tool(
            start_resolution,
            ToolAnnotations(
                title="Start resolution",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        _strict_tool(
            confirm_resolution_action,
            ToolAnnotations(
                title="Confirm resolution action",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
        ),
        _strict_tool(
            get_resolution_status,
            ToolAnnotations(
                title="Get resolution status",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        _strict_tool(
            get_resolution_evidence,
            ToolAnnotations(
                title="Get resolution evidence",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        _strict_tool(
            list_open_resolutions,
            ToolAnnotations(
                title="List open resolutions",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
    ]
    return MCPServer(
        "CloseLoop",
        description="Consequential action lifecycle with independent deterministic verification.",
        instructions=(
            "Start a resolution, obtain explicit user confirmation, then confirm the action. "
            "Execution claims are not verdicts; use status and evidence to report the outcome."
        ),
        version="0.2.0",
        tools=tools,
    )
