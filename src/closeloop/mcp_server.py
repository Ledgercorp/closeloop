from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar

from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from mcp.types import ToolAnnotations
from pydantic import Field, StrictBool

from .alexa_contracts import (
    OpenResolutionsOutput,
    ProviderMode,
    ResolutionEvidenceOutput,
    ResolutionStatusOutput,
)
from .auth import PrincipalResolver, principal_from_authenticated_request
from .confirmation import MAX_ATTESTATION_LENGTH
from .lifecycle import (
    ConcurrentResolutionUpdateError,
    InvalidTransitionError,
    MAX_INTENT_LENGTH,
    MAX_RESOLUTION_ID_LENGTH,
    ResolutionError,
    ResolutionNotFoundError,
    ResolutionService,
    ResolutionStorageUnavailableError,
    TerminalOutcomeImmutableError,
)
from .mcp_app import PROOF_CARD_URI, create_proof_card_extension


ResolutionId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_RESOLUTION_ID_LENGTH,
        description="The owner-scoped resolution_id returned by start_resolution.",
    ),
]
ResultT = TypeVar("ResultT")


def _resolution_operation(operation: Callable[[], ResultT]) -> ResultT:
    """Translate expected domain rejections into safe, useful MCP tool errors."""

    try:
        return operation()
    except ResolutionNotFoundError as exc:
        raise ToolError(
            "Resolution is unavailable. Check the resolution_id or start a new resolution."
        ) from exc
    except ConcurrentResolutionUpdateError as exc:
        raise ToolError(
            "The resolution changed before this action could be applied. "
            "Read its latest status before retrying."
        ) from exc
    except (InvalidTransitionError, TerminalOutcomeImmutableError) as exc:
        raise ToolError(
            "This resolution cannot be advanced from its current lifecycle state. "
            "Read its status before deciding whether to start a new resolution."
        ) from exc
    except ResolutionError as exc:
        raise ToolError(f"Resolution request rejected: {exc}") from exc
    except ResolutionStorageUnavailableError as exc:
        raise ToolError(
            "Resolution storage is temporarily unavailable. No completion result was recorded; "
            "check status later before retrying the action."
        ) from exc


def _strict_tool(
    function: Callable[..., object],
    annotations: ToolAnnotations,
    meta: dict[str, object] | None = None,
) -> Tool:
    """Register a tool whose wire schema rejects all undeclared arguments."""

    tool = Tool.from_function(function, annotations=annotations, meta=meta)
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config["extra"] = "forbid"
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)
    return tool


def create_mcp_server(
    service: ResolutionService | None = None,
    principal_resolver: PrincipalResolver = principal_from_authenticated_request,
    auth_settings: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> MCPServer:
    resolution_service = service or ResolutionService()

    def start_resolution(
        intent: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_INTENT_LENGTH,
                description=(
                    "The customer's complete subscription-cancellation request, including the "
                    "outcome they want independently verified."
                ),
            ),
        ],
        provider_mode: Annotated[
            ProviderMode,
            Field(
                description=(
                    "A labeled first-party demo mode: healthy simulates independently observable "
                    "canceled state, false_success simulates a contradictory provider claim, and "
                    "evidence_outage withholds independent proof."
                )
            ),
        ] = "healthy",
    ) -> ResolutionStatusOutput:
        """Start one cancellation resolution and return its confirmation-required status.

        ``provider_mode`` selects a clearly labeled first-party demo simulation.
        Use this when a customer asks to cancel a subscription. This never executes the
        consequential action; pass the returned ``resolution_id`` to
        ``confirm_resolution_action`` only after the customer explicitly confirms.
        """

        result = _resolution_operation(
            lambda: resolution_service.start_resolution(
                principal_resolver(), intent, provider_mode
            )
        )
        return ResolutionStatusOutput.model_validate(result)

    def confirm_resolution_action(
        resolution_id: ResolutionId,
        confirmed: Annotated[
            StrictBool,
            Field(
                description=(
                    "Must be true only after the customer explicitly confirms the consequential "
                    "cancellation in the current conversation."
                )
            ),
        ],
        confirmation_attestation: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_ATTESTATION_LENGTH,
                description=(
                    "A short-lived, single-use attestation minted by the configured trusted "
                    "confirmation authority after the customer approves this exact action."
                ),
            ),
        ],
    ) -> ResolutionStatusOutput:
        """Execute a confirmed cancellation, independently verify it, and return the outcome.

        Use only after explicit customer confirmation. Provider success is evidence, never the
        verdict; the returned PASS, FAIL, or INCONCLUSIVE value comes only from the deterministic
        verifier and maps to Verified, Not completed, or Awaiting proof.
        """

        result = _resolution_operation(
            lambda: resolution_service.confirm_resolution_action(
                principal_resolver(),
                resolution_id,
                confirmed,
                confirmation_attestation,
            )
        )
        return ResolutionStatusOutput.model_validate(result)

    def get_resolution_status(resolution_id: ResolutionId) -> ResolutionStatusOutput:
        """Read one resolution's complete conversation-ready status without changing it.

        Use when the customer asks what is happening or whether the task is complete. The response
        contains execution, verification, evidence-summary, and safe-next-step fields.
        """

        result = _resolution_operation(
            lambda: resolution_service.get_resolution_status(
                principal_resolver(), resolution_id
            )
        )
        return ResolutionStatusOutput.model_validate(result)

    def get_resolution_evidence(resolution_id: ResolutionId) -> ResolutionEvidenceOutput:
        """Read the evidence chain that justifies one resolution's verification state.

        Use when the customer asks why CloseLoop considers the task Verified, Not completed, or
        Awaiting proof. This is read-only and separates the provider claim from independent
        read-back and the deterministic verifier result.
        """

        result = _resolution_operation(
            lambda: resolution_service.get_resolution_evidence(
                principal_resolver(), resolution_id
            )
        )
        return ResolutionEvidenceOutput.model_validate(result)

    def list_open_resolutions(
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description="Maximum number of this customer's open resolutions to return.",
            ),
        ] = 50,
    ) -> OpenResolutionsOutput:
        """List this customer's non-terminal resolutions without advancing any lifecycle.

        Use to resume a pending confirmation or in-progress task. Never use it to infer another
        customer's work; ownership is derived only from the authenticated bearer token.
        """

        resolutions = _resolution_operation(
            lambda: resolution_service.list_open_resolutions(principal_resolver(), limit)
        )
        return OpenResolutionsOutput(resolutions=resolutions)

    proof_card_meta: dict[str, object] = {
        "ui": {"resourceUri": PROOF_CARD_URI, "visibility": ["model", "app"]}
    }

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
            meta=proof_card_meta,
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
            meta=proof_card_meta,
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
            meta=proof_card_meta,
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
            meta=proof_card_meta,
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
    proof_card = create_proof_card_extension()
    return MCPServer(
        "CloseLoop",
        description="Consequential action lifecycle with independent deterministic verification.",
        instructions=(
            "Start a resolution, obtain explicit user confirmation, then confirm the action. "
            "Execution claims are not verdicts; use status and evidence to report the outcome."
        ),
        version="0.7.0",
        tools=tools,
        extensions=[proof_card],
        auth=auth_settings,
        token_verifier=token_verifier,
    )
