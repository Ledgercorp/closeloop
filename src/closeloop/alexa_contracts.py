from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderMode = Literal["healthy", "false_success", "evidence_outage", "terminal_failure"]
LifecycleStateValue = Literal[
    "REQUESTED",
    "AWAITING_CONFIRMATION",
    "EXECUTING",
    "VERIFYING",
    "VERIFIED",
    "NOT_COMPLETED",
    "AWAITING_PROOF",
]
ResolutionTypeValue = Literal[
    "CANCELLATION", "REFUND", "RETURN", "WARRANTY_CLAIM", "SERVICE_REQUEST", "APPOINTMENT"
]
ExecutionStatus = Literal["not_started", "in_progress", "completed"]
VerificationStatus = Literal["not_started", "in_progress", "PASS", "FAIL", "INCONCLUSIVE"]
VerdictValue = Literal["PASS", "FAIL", "INCONCLUSIVE"]
ConsumerStateValue = Literal["Verified", "Not completed", "Awaiting proof"]


class AlexaContract(BaseModel):
    """Closed output contract used for Alexa+ MCP tool discovery."""

    model_config = ConfigDict(extra="forbid")


class ResolutionStatusOutput(AlexaContract):
    resolution_id: str = Field(description="Opaque identifier for this owner-scoped resolution.")
    task: str = Field(description="The customer's complete requested task.")
    intent: str = Field(description="Backward-compatible alias of the customer's requested task.")
    action: Literal["cancel_subscription"]
    action_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Server-computed digest of the exact consequential action requiring approval.",
    )
    execution_environment: Literal["demo_simulation"]
    provider_mode: ProviderMode
    lifecycle_state: LifecycleStateValue
    resolution_type: ResolutionTypeValue
    is_terminal: bool
    last_checked_at: str | None
    next_check_at: str | None
    check_count: int
    max_checks: int
    resolved_at: str | None
    confirmation_required: bool
    execution_status: ExecutionStatus
    verification_status: VerificationStatus
    consumer_state: ConsumerStateValue | None
    verdict: VerdictValue | None
    evidence_summary: str = Field(
        description="Plain-language summary of the execution and independent verification evidence."
    )
    explanation: str = Field(description="Why the current verification status is justified.")
    recommended_next_step: str = Field(
        description="Safe next step for the conversation; this is data, not scripted speech."
    )
    created_at: str
    updated_at: str
    confirmed_at: str | None
    resolution_reason: str | None
    outcome_contract: dict[str, object] | None = Field(
        default=None, description="Server-interpreted bounded outcome contract."
    )
    open_loop_summary: str = Field(default="", description="Plain-language summary of what CloseLoop is still handling.")
    attention: dict[str, object] = Field(default_factory=dict, description="Deterministic attention class and reason.")
    recovery_proposal: dict[str, object] | None = Field(default=None, description="Bound recovery proposal requiring separate confirmation.")
    recovery_actions: list[dict[str, object]] = Field(default_factory=list)
    outcome_violations: list[dict[str, object]] = Field(default_factory=list)
    resolution_receipt: dict[str, object] | None = Field(default=None)


class ExecutionClaimOutput(AlexaContract):
    evidence_type: Literal["execution_claim"]
    source: str
    request_id: str
    provider_reported_success: bool
    message: str
    observed_at: str
    target_digest: str | None


class IndependentReadBackOutput(AlexaContract):
    evidence_type: Literal["independent_read_back"]
    source: str
    account_readable: bool
    auto_renew: bool | None
    effective_end_date: str | None
    freshness_seconds: int | None
    observed_at: str
    target_digest: str | None
    attempt_id: str | None


class VerificationOutput(AlexaContract):
    verifier: str
    verdict: VerdictValue
    consumer_state: ConsumerStateValue
    reason: str
    evaluated_at: str


class StateTransitionOutput(AlexaContract):
    state: LifecycleStateValue
    occurred_at: str


class HistoricalReadBackOutput(AlexaContract):
    account_readable: bool
    auto_renew: bool | None
    effective_end_date: str | None
    freshness_seconds: int | None
    target_digest: str | None
    attempt_id: str | None


class VerificationAttemptOutput(AlexaContract):
    checked_at: str
    evidence: HistoricalReadBackOutput
    verdict: VerdictValue
    consumer_state: ConsumerStateValue
    reason: str
    attempt_id: str
    check_count: int
    terminal_failure_eligible: bool


class ResourceIdentityOutput(AlexaContract):
    provider: str
    account_subject: str
    resource_id: str
    target_digest: str


class ResolutionEvidenceOutput(AlexaContract):
    resolution_id: str
    task: str = Field(description="The customer's complete requested task.")
    action: Literal["cancel_subscription"]
    action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_environment: Literal["demo_simulation"]
    provider_mode: ProviderMode
    lifecycle_state: LifecycleStateValue
    execution_status: ExecutionStatus
    verification_status: VerificationStatus
    consumer_state: ConsumerStateValue | None
    evidence_summary: str
    recommended_next_step: str
    execution_claim: ExecutionClaimOutput | None
    independent_read_back: IndependentReadBackOutput | None
    verification: VerificationOutput | None
    state_history: list[StateTransitionOutput]
    verification_history: list[VerificationAttemptOutput]
    target_identity: ResourceIdentityOutput
    outcome_contract: dict[str, object] | None = None
    attention_events: list[dict[str, object]] = Field(default_factory=list)
    recovery_actions: list[dict[str, object]] = Field(default_factory=list)
    outcome_violations: list[dict[str, object]] = Field(default_factory=list)


class OpenResolutionsOutput(AlexaContract):
    resolutions: list[ResolutionStatusOutput]


class RecentResolutionsOutput(AlexaContract):
    resolutions: list[ResolutionStatusOutput]
